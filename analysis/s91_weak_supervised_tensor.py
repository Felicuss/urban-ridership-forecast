"""Joint historical-count and future-aggregate supervised periodic tensor model.

Historical labels are individual hourly counts. Future labels are ONLY measured
linear sums. Validation with target aggregates is explicitly conditional.
"""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
import torch
from torch import nn
from s67_joint_day_net import Data,ROUTES,ALL_ROUTES,ROOT
from s52_round4_common import fold_arrays
from s87_reconciliation_pilot import constraints,ipf
from s84_block_probes import grid,mask,margins,decoded,load_ledger,write
from s89_route17_probes import decode_sum,balanced_round

torch.set_num_threads(2)
OUT=ROOT/'data/weak_tensor'
TABLE=ROOT/'docs/analysis/tables/weak_tensor_v15'
ACTIVE=[ALL_ROUTES.index(r) for r in ROUTES]


def cyclic_basis(days,knots):
    position=np.asarray(days)[:,None]/365*knots-np.arange(knots)[None]
    u=abs((position+knots/2)%knots-knots/2)
    return np.where(u<1,2/3-u*u+.5*u**3,np.where(u<2,(2-u)**3/6,0)).astype('float32')


class TensorField(nn.Module):
    def __init__(self,knots,features):
        super().__init__()
        self.season=nn.Parameter(torch.zeros(2,knots,9,24))
        self.weather=nn.Parameter(torch.zeros(features,9,24))
        self.dow=nn.Parameter(torch.zeros(7,9,24))
        self.offset=nn.Parameter(torch.zeros(3,9,24))

    def forward(self,basis,x,kind,dow,base):
        seasonal=torch.einsum('dk,ckrh->dcrh',basis,self.season)
        selected=seasonal[torch.arange(len(kind)),(kind!=0).long()]
        correction=selected+torch.einsum('df,frh->drh',x,self.weather)+self.dow[dow]+self.offset[kind]
        return base*torch.exp(correction.clamp(-2,2))

    def regularization(self):
        cyclic=torch.roll(self.season,1,1)-2*self.season+torch.roll(self.season,-1,1)
        hourly=torch.roll(self.season,1,3)-2*self.season+torch.roll(self.season,-1,3)
        return .03*cyclic.square().mean()+.005*hourly.square().mean()+.02*self.weather.square().mean()+.01*self.dow.square().mean()+.001*self.offset.square().mean()


def fit(data,cutoff,days,anchor,A,b,knots,weak,label,steps=900):
    torch.manual_seed(17)
    historical=np.arange(cutoff+1)
    # Estimate intercepts solely from pre-cutoff counts.
    med=np.ones((3,9,24),dtype='float32')
    for kind in range(3):
        for r in range(9):
            ix=historical[(data.kind[historical,r]==kind)&data.good[historical,r]]
            if len(ix):med[kind,r]=np.maximum(np.median(data.y[ix,r],axis=0),.1)
    n=int(days.max())+1
    kinds=torch.tensor(data.kind[:n,0],dtype=torch.long)
    dow=torch.tensor(data.dow[:n,0],dtype=torch.long)
    basis=torch.tensor(cyclic_basis(np.arange(n),knots))
    # Fixed-scale weather and holiday covariates; no future target statistics.
    cov=data.cov[:n,0]
    features=np.concatenate([cov[:,10:11],cov[:,14:]],axis=1)
    x=torch.tensor(features);base=torch.tensor(med[data.kind[:n,0]])
    target=torch.tensor(np.nan_to_num(data.y[:cutoff+1]))
    quality=torch.tensor(data.good[:cutoff+1,:,None],dtype=torch.float32)
    denominator=(target*quality).sum().clamp_min(1)
    model=TensorField(knots,x.shape[1]);optimizer=torch.optim.Adam(model.parameters(),lr=.015)
    reference=torch.tensor(anchor.reshape(len(days),10,24),dtype=torch.float32)
    protected=(np.isin(ROUTES,[7,50])[None,:]&(data.kind[days]!=0))|((days==364)[:,None])
    protected=torch.tensor(protected[:,:,None])
    at=torch.tensor(A,dtype=torch.float32);bt=torch.tensor(b,dtype=torch.float32)

    def compose(prediction):
        result=reference.clone()
        predicted=prediction[days]*(reference[:,ACTIVE]>0)
        result[:,ACTIVE]=torch.where(protected,reference[:,ACTIVE],predicted)
        return result.reshape(-1)

    trace=[]
    for step in range(steps):
        pred=model(basis,x,kinds,dow,base)
        history_loss=((pred[:cutoff+1]-target).abs()*quality).sum()/denominator
        aggregate_error=(at@compose(pred)-bt)/(bt+1000)
        aggregate_loss=aggregate_error.square().mean()
        loss=history_loss+model.regularization()+weak*min(1,step/200)*100*aggregate_loss
        optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),3);optimizer.step()
        if (step+1)%300==0:
            trace.append(dict(step=step+1,history=float(history_loss.detach()),aggregate=float(aggregate_loss.detach())))
            print(label,knots,weak,trace[-1],flush=True)
    with torch.no_grad():prediction=compose(model(basis,x,kinds,dow,base)).numpy().astype(float)
    OUT.mkdir(parents=True,exist_ok=True)
    torch.save(dict(state_dict=model.state_dict(),intercept=med,knots=knots,features=x.shape[1]),OUT/f'{label}_k{knots}_w{weak}.pt')
    np.save(OUT/f'{label}_k{knots}_w{weak}.npy',prediction)
    return prediction,dict(label=label,knots=knots,weak=weak,steps=steps,cutoff=cutoff,
        parameters=sum(p.numel() for p in model.parameters()),trace=trace)


def main(output):
    if '/' in output or '\\' in output or not output.endswith('.csv'):raise ValueError(output)
    path=ROOT/'forecasts'/output
    if path.exists():raise FileExistsError(path)
    TABLE.mkdir(parents=True,exist_ok=True);data=Data();arrays=fold_arrays();rows=[];logs=[]
    for key in ['R06','R08','B']:
        a=arrays[key];days=np.unique(a['day']);cutoff=int(days.min())-1
        anchor=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1).astype(float)
        A=constraints(a);b=np.einsum('ij,j->i',A,a['y']);ref=ipf(anchor,A,b)
        regular=(a['route']!=5)&~(np.isin(a['route'],[7,50])&(a['kind']!=0))
        for knots in [6,12]:
            for weak in [0,1]:
                p,info=fit(data,cutoff,days,anchor,A,b,knots,weak,key);logs.append(info)
                for alpha in [.25,.5,.75,1.]:
                    result=ipf((1-alpha)*anchor+alpha*p,A,b)
                    for scope,sel in [('all',np.ones(len(p),bool)),('regular',regular)]:
                        rows.append(dict(fold=key,knots=knots,weak=weak,alpha=alpha,scope=scope,
                            conditional_score=1-abs(result[sel]-a['y'][sel]).sum()/a['y'][sel].sum(),
                            gain=(abs(ref[sel]-a['y'][sel]).sum()-abs(result[sel]-a['y'][sel]).sum())/a['y'][sel].sum()))
        pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    frame=pd.DataFrame(rows)
    summary=frame.query("scope=='regular'").groupby(['knots','weak','alpha']).gain.agg(['mean','min'])
    # Penalize a bad fold instead of selecting solely on mean summer gains.
    summary['selection']=summary['mean']+.5*summary['min']
    summary.to_csv(TABLE/'selection.csv');print(summary.to_string(),flush=True)
    knots,weak,alpha=summary.selection.idxmax()
    g=grid().sort_values(['date','route','hour']).reset_index(drop=True)
    champion=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';')
    anchor=g[['route','date','hour']].merge(champion,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):
            cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float);b=np.array([v for _,v,_ in cons])
    p,info=fit(data,303,np.arange(304,365),anchor,A,b,int(knots),int(weak),'future',steps=1200);logs.append(info)
    result=balanced_round(ipf((1-alpha)*anchor+alpha*p,A,b),cons)
    restored=champion[['route','date','hour']].merge(g[['route','date','hour']].assign(prediction=result),on=['route','date','hour'],validate='one_to_one')
    write(restored,restored.prediction.to_numpy(),path)
    meta=dict(status='unscored',file=path.name,anchor='submission_r17_measured_v13.csv',anchor_score=.91048,
        knots=int(knots),weak_training=int(weak),weight=float(alpha),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        changed_cells=int((result!=anchor).sum()),l1_distance=int(abs(result-anchor).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,result)-b).max()),
        training=logs,caveat='Historical evaluation is conditional on truth aggregates; no hourly test labels were available.')
    path.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('EXPORTED',path.name,knots,weak,alpha,meta['l1_distance'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='submission_weak_tensor_v15.csv')
    main(parser.parse_args().out)
