"""Evaluate cached local models and fixed blends on the same v7 reference."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from s67_joint_day_net import ROOT, OUT, Data, v7_references, blend_shape


def main():
    data=Data();rows=[]
    for key,(a,ref) in v7_references().items():
        truth=a['y'].reshape(ref.shape);den=truth.sum()
        start=int(a['day'][0]);kind=data.kind[start:start+len(ref)]
        net=np.load(OUT/f'ensemble_{key}.npy')
        nn35=blend_shape(ref,net,kind,.35)
        options={'joint35':nn35}
        candidates={}
        for steps in [0,100,500]:
            path=ROOT/f'data/chronos_local/{key}_steps{steps}_mps.npz'
            if path.exists():candidates[f'chronos{steps}']=np.load(path)['prediction']
        path=ROOT/f'data/tirex_local/{key}_mps.npz'
        if path.exists():candidates['tirex']=np.load(path)['prediction']
        for name,shape in candidates.items():
            for w in [.1,.2,.35]:
                options[f'{name}_{w}']=blend_shape(ref,shape,kind,w)
                options[f'joint35_then_{name}_{w}']=blend_shape(nn35,shape,kind,w)
        for name,p in options.items():
            rows.append(dict(fold=key,model=name,score=1-abs(p-truth).sum()/den,
                             gain=(abs(ref-truth).sum()-abs(p-truth).sum())/den,
                             gain_vs_joint35=(abs(nn35-truth).sum()-abs(p-truth).sum())/den))
    frame=pd.DataFrame(rows)
    destination=ROOT/'docs/analysis/tables/local_neural_comparison.csv'
    frame.to_csv(destination,index=False)
    pivot=frame.pivot(index='model',columns='fold',values='gain')
    pivot['mean']=pivot.mean(axis=1);pivot['folds']=pivot.drop(columns='mean').notna().sum(axis=1)
    pivot['worst']=pivot.drop(columns=['mean','folds']).min(axis=1)
    pivot.to_csv(destination.with_name('local_neural_summary.csv'))
    print(pivot.sort_values(['folds','mean'],ascending=False).round(6).to_string(),flush=True)


if __name__=='__main__':main()
