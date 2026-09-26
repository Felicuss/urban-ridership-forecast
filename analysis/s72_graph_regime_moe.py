"""Joint count/shape forecasting with causal regime experts and route attention.

Templates provide absolute 24-hour forecasts. A learned router combines six
templates; route attention shares historical information; bounded level and
shape heads optimize hourly L1 directly. Uses permitted ex-post covariates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from s67_joint_day_net import ROOT, PACK, ROUTES, ALL_ROUTES, Data, norm

OUT=ROOT/'data/graph_moe'
CONTEXT=56
EXPERTS=['median14','median42','median112','city42','same_regime','weather_analog']


class RegimeData(Data):
    def __init__(self):
        super().__init__()
        frame=pd.concat([pd.read_parquet(PACK/'history.parquet'),pd.read_parquet(PACK/'future_covariates.parquet')])
        frame=frame[frame.route.isin(ROUTES)].sort_values(['date','route','hour'])
        daily=frame[frame.hour==0]
        self.regime=daily.network_regime.to_numpy().reshape(365,9)
        self.holiday=daily.holiday.to_numpy().reshape(365,9)
        self.temp=frame.temperature_2m.to_numpy().reshape(365,9,24).mean(-1)
        self.rain=frame.precipitation.to_numpy().reshape(365,9,24).sum(-1)
        self.month=np.asarray(pd.date_range('2025-01-01',periods=365).month)
        # Calendar-normalized city rate: actual public monthly city totals.
        city=daily.city_tram_month_total.to_numpy().reshape(365,9)[:,0]
        self.city=np.zeros(365)
        day_weight=np.where(self.kind[:,0]==0,1.,np.where(self.kind[:,0]==1,.68,.58))
        for month in range(1,13):
            mask=self.month==month
            self.city[mask]=city[mask][0]/day_weight[mask].sum()
        self.city/=np.mean(self.city[:31])
        self.cov=np.concatenate([self.cov,
            np.broadcast_to(self.city[:,None,None],(365,9,1)),
            np.broadcast_to(np.sin(2*np.pi*(np.arange(365)-80)/365)[:,None,None],(365,9,1))],axis=-1).astype('float32')

    def origin_features(self,origin):
        source=np.arange(max(0,origin-111),origin+1)
        scale=[]
        for j in range(9):
            ix=source[self.good[source,j]&(self.kind[source,j]==0)]
            if not len(ix):ix=source[self.good[source,j]]
            scale.append(np.median(self.total[ix,j]) if len(ix) else 10000.)
        scale=np.maximum(scale,100.).astype('float32')
        lo=max(0,origin-CONTEXT+1);ix=np.arange(lo,origin+1)
        counts=np.nan_to_num(self.y[ix])/scale[None,:,None]*24
        counts*=self.good[ix,:,None]
        ctx=np.concatenate([counts,np.eye(3)[self.kind[ix]],self.good[ix,:,None],
                            self.temp[ix,:,None]/20,np.log1p(self.rain[ix,:,None])/3],axis=-1)
        ctx=np.pad(ctx,((CONTEXT-len(ix),0),(0,0),(0,0))).transpose(1,0,2).reshape(9,-1)
        return ctx.astype('float32'),scale

    def experts(self,origin,dates):
        all_history=np.arange(origin+1)
        result=np.zeros((len(dates),9,len(EXPERTS),24),dtype='float32')
        for i,d in enumerate(dates):
            for j in range(9):
                valid=all_history[self.good[:origin+1,j]&(self.kind[:origin+1,j]==self.kind[d,j])]
                if not len(valid):valid=all_history[self.good[:origin+1,j]]
                if not len(valid):continue
                profiles=[]; histories=[]
                for window in [14,42,112]:
                    ix=valid[valid>origin-window]
                    if not len(ix):ix=valid[-4:]
                    profiles.append(np.median(self.y[ix,j],axis=0));histories.append(ix)
                city_ratio=np.clip(self.city[d]/np.mean(self.city[histories[1]]),.65,1.4)
                profiles.append(profiles[1]*city_ratio)
                ix=valid[(valid>origin-168)&(self.regime[valid,j]==self.regime[d,j])]
                if len(ix)<2:ix=histories[1]
                profiles.append(np.median(self.y[ix,j],axis=0))
                # Weather/daylight analogues provide winter-like historical shapes;
                # their daily mass is anchored to the recent calendar profile.
                distance=abs(self.temp[valid,j]-self.temp[d,j])/8
                distance+=abs(np.log1p(self.rain[valid,j])-np.log1p(self.rain[d,j]))*.25
                distance+=abs(np.sin(2*np.pi*(valid-80)/365)-np.sin(2*np.pi*(d-80)/365))*.5
                distance+=(origin-valid)/365*.4
                distance+=(self.regime[valid,j]!=self.regime[d,j])*2
                neighbors=valid[np.argsort(distance)[:min(12,len(valid))]]
                analog=norm(np.median(self.shape[neighbors,j],axis=0))
                profiles.append(analog*profiles[1].sum())
                # Common non-network seasonal adjustment, deliberately bounded.
                for k in [0,1,2,4,5]:profiles[k]=profiles[k]*(city_ratio**.35)
                result[i,j]=np.stack(profiles)
        assert np.isfinite(result).all() and (result>=0).all()
        return result

    def samples(self,cutoff):
        origins=np.arange(34,cutoff,7)
        contexts=[];scales=[];experts=[];indices=[];dates=[]
        for i,o in enumerate(origins):
            c,s=self.origin_features(o);contexts.append(c);scales.append(s)
            ds=np.arange(o+1,min(cutoff+1,o+62))
            experts.append(self.experts(o,ds));indices.extend([i]*len(ds));dates.extend(ds)
        indices=np.asarray(indices);dates=np.asarray(dates)
        assert dates.max()<=cutoff and np.all(origins[indices]<dates)
        count=np.bincount(dates,minlength=365)
        weight=self.good[dates].astype('float32')/count[dates,None]
        weight/=max(weight.mean(),1e-8)
        cov=np.concatenate([self.cov[dates],np.broadcast_to(((dates-origins[indices])/61)[:,None,None],(len(dates),9,1))],-1)
        return dict(context=np.stack(contexts),scale=np.stack(scales),index=indices,
            expert=np.concatenate(experts),cov=cov.astype('float32'),
            target=np.nan_to_num(self.y[dates]),weight=weight.astype('float32'),
            dates=dates,origins=origins)


class RegimeGraphNet(nn.Module):
    def __init__(self,context_dim,cov_dim,width=128,weather=True):
        super().__init__()
        self.encoder=nn.Sequential(nn.Linear(context_dim,width),nn.LayerNorm(width),nn.GELU(),nn.Dropout(.1),nn.Linear(width,width))
        self.attention=nn.MultiheadAttention(width,4,dropout=.05,batch_first=True)
        self.norm=nn.LayerNorm(width)
        self.route=nn.Embedding(9,12)
        self.decoder=nn.Sequential(nn.Linear(width+cov_dim+len(EXPERTS)*2+12,width),nn.GELU(),nn.Dropout(.1),nn.Linear(width,width),nn.GELU())
        self.gate=nn.Linear(width,len(EXPERTS))
        self.shape_head=nn.Linear(width,24)
        self.level_head=nn.Linear(width,1)
        for layer in [self.gate,self.shape_head,self.level_head]:
            nn.init.zeros_(layer.weight);nn.init.zeros_(layer.bias)

    def forward(self,context,cov,expert,scale):
        encoded=self.encoder(context)
        shared,_=self.attention(encoded,encoded,encoded,need_weights=False)
        encoded=self.norm(encoded+shared)
        daily=expert.sum(-1)/scale[:,:,None].clamp_min(100.)
        peak=expert.max(-1).values/scale[:,:,None].clamp_min(100.)*24
        hidden=self.decoder(torch.cat([encoded,cov,daily,peak,self.route.weight[None].expand(len(context),-1,-1)],-1))
        weights=torch.softmax(self.gate(hidden),-1)
        base=(expert*weights[...,None]).sum(-2)
        shape_shift=.5*torch.tanh(self.shape_head(hidden))
        level_shift=.3*torch.tanh(self.level_head(hidden))
        shape=torch.softmax(torch.log(base.clamp_min(.01))+shape_shift,-1)
        output=shape*base.sum(-1,keepdim=True)*torch.exp(level_shift)
        return output,weights,shape_shift,level_shift


def fit(data,cutoff,horizon,key,seed,steps,device):
    path=OUT/f'{key}_seed{seed}_steps{steps}.npz'
    if path.exists():
        z=np.load(path);print('CACHE',path.name,flush=True);return z['prediction']
    torch.manual_seed(seed);rng=np.random.default_rng(seed)
    sample_path=OUT/f'train_cutoff{cutoff}.npz'
    if sample_path.exists():s=dict(np.load(sample_path))
    else:
        s=data.samples(cutoff);np.savez_compressed(sample_path,**s)
    tensors={k:torch.as_tensor(s[k],dtype=torch.float32,device=device) for k in ['context','scale','expert','cov','target','weight']}
    indexes=torch.as_tensor(s['index'],dtype=torch.long,device=device)
    model=RegimeGraphNet(s['context'].shape[-1],s['cov'].shape[-1]).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=2e-4,weight_decay=.03)
    started=time.monotonic();logs=[]
    for step in range(steps):
        ids=torch.as_tensor(rng.integers(0,len(indexes),64),device=device)
        pred,gate,shape,level=model(tensors['context'][indexes[ids]],tensors['cov'][ids],tensors['expert'][ids],tensors['scale'][indexes[ids]])
        loss=((pred-tensors['target'][ids]).abs().sum(-1)/10000*tensors['weight'][ids]).mean()
        loss+=.02*level.square().mean()+.002*shape.square().mean()+.001*(gate-1/len(EXPERTS)).square().mean()
        opt.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);opt.step()
        if step==0 or (step+1)%200==0:
            value=float(loss.detach().cpu());logs.append([step+1,value]);print(key,seed,step+1,'loss',round(value,5),'sec',round(time.monotonic()-started,1),flush=True)
    model.eval();dates=np.arange(cutoff+1,cutoff+1+horizon)
    context,scale=data.origin_features(cutoff)
    experts=data.experts(cutoff,dates)
    cov=np.concatenate([data.cov[dates],np.broadcast_to(((dates-cutoff)/61)[:,None,None],(horizon,9,1))],-1)
    with torch.no_grad():
        pred,gate,shape,level=model(torch.tensor(np.broadcast_to(context,(horizon,)+context.shape).copy(),device=device),
            torch.tensor(cov,dtype=torch.float32,device=device),torch.tensor(experts,device=device),
            torch.tensor(np.broadcast_to(scale,(horizon,9)).copy(),device=device))
        prediction=pred.cpu().numpy();gates=gate.cpu().numpy();levels=level.cpu().numpy()
    assert np.isfinite(prediction).all() and (prediction>=0).all()
    metadata=dict(fold=key,seed=seed,cutoff=int(cutoff),max_training_target=int(s['dates'].max()),steps=steps,
        parameters=sum(p.numel() for p in model.parameters()),seconds=time.monotonic()-started,device=device,loss_trace=logs)
    np.savez_compressed(path,prediction=prediction,gate=gates,level_shift=levels,metadata=json.dumps(metadata))
    if key=='future':
        torch.save(dict(state_dict={k:v.cpu() for k,v in model.state_dict().items()},context_dim=s['context'].shape[-1],cov_dim=s['cov'].shape[-1],metadata=metadata),OUT/f'graph_seed{seed}.pt')
    return prediction


def main():
    p=argparse.ArgumentParser();p.add_argument('--folds',default='R05,R07,B');p.add_argument('--seeds',default='2026')
    p.add_argument('--steps',type=int,default=1200);p.add_argument('--device',default='mps');args=p.parse_args()
    torch.set_num_threads(4);OUT.mkdir(parents=True,exist_ok=True);data=RegimeData()
    folds={x['name']:(pd.Timestamp(x['train_end']).dayofyear-1,x['horizon_days']) for x in json.loads((PACK/'folds.json').read_text())}
    folds['future']=(303,61)
    for key in args.folds.split(','):
        cutoff,horizon=folds[key]
        preds=[fit(data,cutoff,horizon,key,int(seed),args.steps,args.device) for seed in args.seeds.split(',')]
        np.save(OUT/f'ensemble_{key}.npy',np.mean(preds,axis=0))
    (OUT/'configuration.json').write_text(json.dumps(dict(arguments=vars(args),experts=EXPERTS,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':main()
