"""Learned whole-network day retrieval with aggregate-conditioned memory weights.

Stage 1 learns a covariate distance under strictly historical donor masks.
Stage 2 adjusts future donor mixtures against supplied aggregate observations.
Conditional evaluation uses truth aggregates explicitly, not an ordinary forecast.
"""
import json
import time
import hashlib
import argparse
import numpy as np
import pandas as pd
import torch
from torch import nn
from s67_joint_day_net import Data, ROUTES, ALL_ROUTES, ROOT
from s52_round4_common import fold_arrays
from s87_reconciliation_pilot import constraints, ipf
from s84_block_probes import grid, margins, decoded, load_ledger, mask, write
from s89_route17_probes import decode_sum, balanced_round

OUT=ROOT/'data/memory_transport'
TABLE=ROOT/'docs/analysis/tables/memory_transport_v14'
torch.set_num_threads(2)


def joint_values(data):
    """Causal detrending: each day's level uses only earlier calendar peers."""
    ratio=np.ones((365,9),dtype='float32')
    for day in range(304):
        source=np.arange(max(0,day-84),day)
        for route in range(9):
            valid=source[data.good[source,route]&(data.kind[source,route]==data.kind[day,route])]
            if len(valid)>=3:
                trend=np.median(data.total[valid,route])
                ratio[day,route]=np.clip(data.total[day,route]/max(trend,100),.5,1.5)
    return data.shape*ratio[:,:,None]


class MemoryMetric(nn.Module):
    def __init__(self,features):
        super().__init__()
        self.metric=nn.Sequential(nn.Linear(features,24),nn.Tanh(),nn.Linear(24,12))
        self.distance=nn.Parameter(torch.full((features,),-1.5))
        self.age=nn.Parameter(torch.tensor(-.5))

    def forward(self,x,query,origin):
        z=self.metric(x)
        squared=(x[query,None]-x[None])**2
        distance=(squared*torch.nn.functional.softplus(self.distance)).sum(-1)
        distance+=((z[query,None]-z[None])**2).sum(-1)
        ages=(origin[:,None]-torch.arange(len(x))[None]).float()/90
        logits=-distance-torch.nn.functional.softplus(self.age)*ages.clamp_min(0)
        return logits.masked_fill(ages<0,-1e4)


def memory_profile(logits,profiles,quality):
    # One network-day affinity, with route-specific missing/suspended days masked.
    weights=torch.softmax(logits[:,:,None].masked_fill(~quality[None],-1e4),dim=1)
    return torch.einsum('bkr,krh->brh',weights,profiles),weights


def train(data,cutoff,label,steps=600,seed=2026):
    torch.manual_seed(seed);rng=np.random.default_rng(seed)
    # Covariates already have fixed physical scales; no future target statistics.
    x=torch.tensor(data.cov[:,0],dtype=torch.float32)
    profiles=torch.tensor(data.values[:cutoff+1]);quality=torch.tensor(data.good[:cutoff+1])
    model=MemoryMetric(x.shape[1]);opt=torch.optim.AdamW(model.parameters(),lr=.003,weight_decay=.02)
    targets=torch.tensor(data.values);totals=torch.tensor(data.total);good=torch.tensor(data.good)
    start=time.monotonic();trace=[]
    for step in range(steps):
        dates=rng.integers(45,cutoff+1,32)
        horizon=rng.integers(1,62,32);origins=np.maximum(20,dates-horizon)
        q=torch.tensor(dates);o=torch.tensor(origins)
        logits=model(x,q,o)[:,:cutoff+1]
        pred,_=memory_profile(logits,profiles,quality)
        weights=totals[q]*good[q]
        loss=((pred-targets[q]).abs()*weights[:,:,None]).sum()/weights.sum().clamp_min(1)
        loss+=.0003*sum(p.square().mean() for p in model.parameters())
        opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1);opt.step()
        if (step+1)%200==0:
            trace.append([step+1,float(loss.detach())]);print(label,step+1,round(float(loss.detach()),5),round(time.monotonic()-start,1),flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    torch.save(model.state_dict(),OUT/f'{label}.pt')
    return model,dict(cutoff=cutoff,steps=steps,seed=seed,seconds=time.monotonic()-start,
        parameters=sum(p.numel() for p in model.parameters()),loss_trace=trace)


def reconstruct(data,model,cutoff,days,base,A,b,label,steps=350):
    d=len(days);base3=base.reshape(d,10,24)
    indices=[ALL_ROUTES.index(r) for r in ROUTES]
    x=torch.tensor(data.cov[:,0]);profiles=torch.tensor(data.values[:cutoff+1]);quality=torch.tensor(data.good[:cutoff+1])
    with torch.no_grad():
        logits=model(x,torch.tensor(days),torch.full((d,),cutoff))[:,:cutoff+1].detach()
        initial,_=memory_profile(logits,profiles,quality)
    base_tensor=torch.tensor(base3,dtype=torch.float32)
    daily=base_tensor[:,indices].sum(-1,keepdim=True)
    support=base_tensor[:,indices]>0
    protected=np.isin(ROUTES,[7,50])[None,:]&(data.kind[days]!=0)
    # Dec 31 special free travel and daily profile remain with the scored model.
    protected|=(days==364)[:,None]
    protected=torch.tensor(protected)
    month=(pd.Timestamp('2025-01-01')+pd.to_timedelta(days,unit='D')).month.to_numpy()
    group_masks=[]
    for m in np.unique(month):
        for kind in [0,1,2]:
            group_masks.append(torch.tensor((month[:,None]==m)&(data.kind[days]==kind))&~protected)

    def compose(shape):
        amplitude=shape.sum(-1).clamp(.5,1.5)
        # Learn within-month redistribution, not an unconstrained new level.
        normalization=torch.ones_like(amplitude)
        for group in group_masks:
            mass=daily[:,:,0]*group
            average=(amplitude*mass).sum(0)/mass.sum(0).clamp_min(1)
            normalization=torch.where(group,average[None].clamp_min(.1),normalization)
        level=daily*(amplitude/normalization)[:,:,None]
        shape=shape*support
        shape=shape/shape.sum(-1,keepdim=True).clamp_min(1e-8)
        prediction=base_tensor.clone()
        replacement=level*shape
        prediction[:,indices]=torch.where(protected[:,:,None],base_tensor[:,indices],replacement)
        return prediction.reshape(-1)

    raw=compose(initial).detach().numpy().astype(float)
    delta=nn.Parameter(torch.zeros_like(logits));opt=torch.optim.Adam([delta],lr=.04)
    at=torch.tensor(A,dtype=torch.float32);bt=torch.tensor(b,dtype=torch.float32)
    reference=torch.softmax(logits,dim=1).detach()
    start=time.monotonic()
    for step in range(steps):
        shaped,_=memory_profile(logits+delta,profiles,quality)
        prediction=compose(shaped)
        relative=(at@prediction-bt)/(bt+1000)
        weights=torch.softmax(logits+delta,dim=1)
        kl=(weights*(torch.log(weights.clamp_min(1e-12))-torch.log(reference.clamp_min(1e-12)))).sum(-1).mean()
        loss=100*relative.square().mean()+.015*kl+.0002*delta.square().mean()
        opt.zero_grad();loss.backward();opt.step()
    with torch.no_grad():
        shaped,_=memory_profile(logits+delta,profiles,quality)
        adjusted=compose(shaped).numpy().astype(float)
    print(label,'transport',round(time.monotonic()-start,1),'sec',flush=True)
    np.savez_compressed(OUT/f'{label}_predictions.npz',raw=raw,conditioned=adjusted,days=days)
    return raw,adjusted


def main(output='submission_memory_transport_v14.csv'):
    TABLE.mkdir(parents=True,exist_ok=True);data=Data();data.values=joint_values(data);arrays=fold_arrays();rows=[];training=[]
    for key in ['R06','R08','B']:
        a=arrays[key];days=np.unique(a['day']);cutoff=int(days.min())-1
        model,meta=train(data,cutoff,key);training.append(dict(label=key,**meta))
        base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1).astype(float)
        A=constraints(a);b=np.einsum('ij,j->i',A,a['y']);ref=ipf(base,A,b)
        raw,conditioned=reconstruct(data,model,cutoff,days,base,A,b,key)
        for name,p in [('raw',raw),('transport',conditioned)]:
            for alpha in [.5,.8,1.]:
                q=(1-alpha)*base+alpha*p
                calibrated=ipf(q,A,b)
                regular=(a['route']!=5)&~(np.isin(a['route'],[7,50])&(a['kind']!=0))
                for scope,sel in [('all',np.ones(len(q),bool)),('regular',regular)]:
                    rows.append(dict(fold=key,method=name,alpha=alpha,scope=scope,
                        forecast_score=(1-abs(q[sel]-a['y'][sel]).sum()/a['y'][sel].sum()) if name=='raw' else None,
                        conditional_score=1-abs(calibrated[sel]-a['y'][sel]).sum()/a['y'][sel].sum(),
                        conditional_gain=(abs(ref[sel]-a['y'][sel]).sum()-abs(calibrated[sel]-a['y'][sel]).sum())/a['y'][sel].sum()))
        pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    f=pd.DataFrame(rows);summary=f.query("scope=='regular'").groupby(['method','alpha']).conditional_gain.agg(['mean','min'])
    print(summary.to_string(),flush=True);summary.to_csv(TABLE/'selection.csv')
    # User explicitly requests a risk-taking architectural candidate. Selection
    # remains on reused development folds and may still be worse than champion.
    method,alpha=summary['mean'].idxmax()
    model,meta=train(data,303,'future',steps=800);training.append(dict(label='future',**meta))
    g=grid().sort_values(['date','route','hour']).reset_index(drop=True)
    champion=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';')
    base=g[['route','date','hour']].merge(champion,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):
            cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float);b=np.array([v for _,v,_ in cons])
    raw,adjusted=reconstruct(data,model,303,np.arange(304,365),base,A,b,'future',steps=500)
    selected=raw if method=='raw' else adjusted
    final=ipf((1-alpha)*base+alpha*selected,A,b)
    pred=balanced_round(final,cons)
    frame=g[['route','date','hour']].assign(prediction=pred)
    restored=champion[['route','date','hour']].merge(frame,on=['route','date','hour'],validate='one_to_one')
    if '/' in output or '\\' in output or not output.endswith('.csv'):
        raise ValueError('Output must be a CSV filename inside forecasts/')
    path=ROOT/'forecasts'/output
    assert not path.exists(),'Never overwrite a released submission'
    write(restored,restored.prediction.to_numpy(),path)
    metadata=dict(status='unscored',file=path.name,anchor='submission_r17_measured_v13.csv',anchor_score=.91048,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),method=method,weight=float(alpha),
        changed_cells=int((pred!=base).sum()),l1_distance_from_anchor=int(abs(pred-base).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,pred)-b).max()),training=training,
        architecture='Learned network-day memory retrieval of joint level and hourly shape; conditional donor reweighting ablation',
        caveat='Risk-taking new architecture; conditional development evaluations use truth aggregates. No new LB score.')
    path.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (TABLE/'training.json').write_text(json.dumps(training,indent=2)+'\n')
    print('EXPORTED',metadata,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default='submission_memory_transport_v14.csv')
    main(parser.parse_args().out)
