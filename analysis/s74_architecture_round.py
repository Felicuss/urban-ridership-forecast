"""Compare joint, level-only and shape-only updates on identical scoring cells."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from s67_joint_day_net import ROOT, ROUTES, ALL_ROUTES, Data, norm, v7_references

OUT=ROOT/'data/architecture_round9'


def replacement(reference,raw,kind,mode):
    result=reference.astype(float,copy=True)
    for ri,route in enumerate(ROUTES):
        j=ALL_ROUTES.index(route)
        p=reference[:,j]
        prop=raw[:,ri].copy();prop[p==0]=0
        shape=norm(prop)
        level=p.sum(-1)
        ratio=np.divide(prop.sum(-1),level,out=np.ones_like(level),where=level>0)
        ratio=np.clip(ratio,.6,1.4)
        if mode=='shape': new=shape*level[:,None]
        elif mode=='level': new=p*ratio[:,None]
        else: new=shape*(level*ratio)[:,None]
        new[prop.sum(-1)==0]=p[prop.sum(-1)==0]
        if route in [7,50]:new[kind[:,ri]!=0]=p[kind[:,ri]!=0]
        result[:,j]=new
    assert np.isfinite(result).all() and np.all(result[reference==0]==0)
    return result


def raw_predictions(key):
    paths={'graph':ROOT/f'data/graph_moe/ensemble_{key}.npy',
           'varx':ROOT/f'data/structural_statistical/varx_{key}.npy',
           'stl_ets':ROOT/f'data/structural_statistical/stl_ets_{key}.npy'}
    result={name:np.load(path) for name,path in paths.items() if path.exists()}
    for steps in [0,500]:
        path=ROOT/f'data/chronos_local/{key}_steps{steps}_mps.npz'
        if path.exists():result[f'chronos{steps}']=np.load(path)['prediction']
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True);data=Data();rows=[];oracles=[]
    for key,(a,ref) in v7_references().items():
        y=a['y'].reshape(ref.shape);total=y.sum();start=int(a['day'][0]);kind=data.kind[start:start+len(ref)]
        den=ref.sum(-1,keepdims=True)
        true_day=ref*np.divide(y.sum(-1,keepdims=True),den,out=np.ones_like(den),where=den>0)
        oracles.append(dict(fold=key,reference=1-abs(ref-y).sum()/total,true_daily=1-abs(true_day-y).sum()/total))
        for model,raw in raw_predictions(key).items():
            for mode in ['joint','level','shape']:
                p=replacement(ref,raw,kind,mode)
                np.save(OUT/f'{model}_{mode}_{key}.npy',p)
                for w in [.1,.25,.5,1.]:
                    prediction=ref+w*(p-ref)
                    for route in [0]+ROUTES:
                        mask=np.ones_like(y,dtype=bool)
                        if route:
                            mask[:]=False;mask[:,ALL_ROUTES.index(route)]=True
                        den=y[mask].sum();err=abs(prediction[mask]-y[mask]).sum();base=abs(ref[mask]-y[mask]).sum()
                        rows.append(dict(fold=key,model=model,mode=mode,weight=w,route=route,
                            score=1-err/den,gain=(base-err)/den,bias=prediction[mask].sum()/den-1))
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'validation.csv',index=False)
    pd.DataFrame(oracles).to_csv(OUT/'oracle_diagnostics.csv',index=False)
    pivot=frame[frame.route==0].pivot(index=['model','mode','weight'],columns='fold',values='gain')
    cols=list(pivot.columns);pivot['mean']=pivot[cols].mean(axis=1);pivot['worst']=pivot[cols].min(axis=1);pivot['folds']=pivot[cols].count(axis=1)
    pivot.to_csv(OUT/'summary.csv');print(pivot.sort_values(['folds','mean'],ascending=False).round(6).to_string(),flush=True)


if __name__=='__main__':main()
