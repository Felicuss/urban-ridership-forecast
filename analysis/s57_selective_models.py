"""Select additions to v2 per route using completed earlier forecast blocks."""
from __future__ import annotations
import numpy as np
from s52_round4_common import *
from s55_daily_level import rescale

NAMES=['v2','catboost_20','daily_optimal_25','daily_sum_25']


def components(key,a):
    return np.asarray([a['v2'],match_protection(.8*a['v2']+.2*np.load(CACHE/f'catboost_{key}.npy'),a),
        rescale(a,np.load(CACHE/f'daily_optimal_{key}.npy'),.25),
        rescale(a,np.load(CACHE/f'daily_sum_{key}.npy'),.25)])


def choose(pools,route):
    if len(pools)<2:return 0
    losses=[];movements=[];sums=[]
    for a,p in pools:
        mask=a['route']==route
        losses.append(abs(p[:,mask]-a['y'][mask]).sum(axis=1))
        movements.append(abs(p[:,mask]-a['v2'][mask]).sum(axis=1))
        sums.append(a['y'][mask].sum())
    losses=np.array(losses);movements=np.array(movements)
    gain=(losses[:,[0]]-losses)/np.maximum(1,np.array(sums)[:,None])
    eligible=(gain>0).sum(axis=0)>=int(np.ceil(len(pools)*2/3))
    eligible&=gain.min(axis=0)>=-.01
    eligible[0]=True
    # Equal fold influence, with a penalty on movement from the champion.
    criterion=((losses+.1*movements)/np.maximum(1,np.array(sums)[:,None])).mean(axis=0)
    criterion[~eligible]=np.inf
    return int(np.argmin(criterion))


def build(a,p,selection):
    out=a['v2'].copy()
    for r,k in selection.items():
        mask=a['route']==int(r)
        out[mask]=p[k,mask]
    return match_protection(out,a)


def main():
    init();arrays=fold_arrays();comps={k:components(k,a) for k,a in arrays.items()};rows=[]
    for fold,a in arrays.items():
        pools=[(v,comps[k]) for k,v in prior_blocks(arrays,a).items()]
        selection={str(r):choose(pools,r) for r in ROUTES}
        pred=build(a,comps[fold],selection)
        np.save(CACHE/f'selective_{fold}.npy',pred)
        rows.append(dict(candidate='selective_models',fold=fold,past_folds=len(pools),score=score(a['y'],pred),
            gain=score(a['y'],pred)-score(a['y'],a['v2'])))
        print(fold,{r:NAMES[k] for r,k in selection.items()},flush=True)
    report(rows,'selective_models')
    pools=[(a,comps[k]) for k,a in arrays.items()];selection={str(r):choose(pools,r) for r in ROUTES}
    a=future_arrays();p=components('future',a);pred=build(a,p,selection)
    np.save(CACHE/'selective_future.npy',pred)
    export('selective_models',core=pred,metadata={'method':'Per-route selection of CatBoost or daily correction, requiring improvement in >=2/3 source folds',
        'selection':{r:NAMES[k] for r,k in selection.items()},'validation':'Source target blocks end before evaluation target blocks begin.'})
    # Bounded combined candidate; assess the exact same mixture out of sample.
    from s53_route_ensemble import select,predict
    rows=[]
    for fold,a0 in arrays.items():
        prior=list(prior_blocks(arrays,a0).values())
        route_pred=predict(a0,select(prior,True),True)
        p0=.5*route_pred+.5*np.load(CACHE/f'selective_{fold}.npy')
        rows.append(dict(candidate='combined_models',fold=fold,score=score(a0['y'],p0),
            gain=score(a0['y'],p0)-score(a0['y'],a0['v2'])))
    report(rows,'combined_models')
    combined=.5*np.load(CACHE/'route_kind_weights_future.npy')+.5*pred
    export('combined_models',core=combined,metadata={'method':'50% route/day-kind ensemble + 50% selectively added models; exact mixture checked on folds'})


if __name__=='__main__':main()
