"""Route-specific ensemble selection using only completed earlier target blocks."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from s52_round4_common import *


def alternatives(a):
    ps=[a['v2']];names=['v2']
    for mix_name,w in [('old',(1,0,0)),('rich',(0,1,0)),('direct',(0,0,1)),
                       ('rich_direct',(0,.5,.5)),('v2_mix',(.25,.5,.25))]:
        m=sum(v*a[k] for v,k in zip(w,['old','rich','direct']))
        for factor in (.6,1.,1.4):
            weight=np.where(a['horizon']<=30,CONFIG['near'],CONFIG['far'])*factor
            p=np.maximum(0,a['base']+weight*(m-a['base']))
            ps.append(match_protection(p,a));names.append(f'{mix_name}_weightx{factor}')
    return np.asarray(ps),names


def groups(a,kind):
    return a['route']*10+(a['kind'] if kind else 0)


def select(pools,kind):
    if not pools:return {}
    a={k:np.concatenate([x[k] for x in pools]) for k in ['y','base','v2','old','rich','direct','horizon','route','kind','day']}
    p,names=alternatives(a);group=groups(a,kind)
    cell=pd.DataFrame({'day':a['day'],'route':a['route'],'hour':np.tile(np.arange(24),len(a['y'])//24)})
    count=cell.groupby(['day','route','hour']).day.transform('size').to_numpy()
    weight=1/count
    result={}
    for g in np.unique(group):
        mask=group==g
        if len(np.unique(a['day'][mask]))<12 or a['y'][mask].sum()==0:continue
        losses=(np.abs(p[:,mask]-a['y'][mask])*weight[mask]).sum(axis=1)
        # Penalize forecast movement as well as fitting error; then shrink 50%
        # to the established champion. No new per-route level multiplier.
        penalty=.15*(np.abs(p[:,mask]-a['v2'][mask])*weight[mask]).sum(axis=1)
        best=int(np.argmin(losses+penalty))
        result[str(int(g))]=dict(index=best,name=names[best],relative_gain=float((losses[0]-losses[best])/a['y'][mask].sum()))
    return result


def predict(a,selection,kind):
    p,_=alternatives(a);out=a['v2'].copy();group=groups(a,kind)
    for g,config in selection.items():
        mask=group==int(g)
        out[mask]=.5*a['v2'][mask]+.5*p[config['index'],mask]
    return match_protection(out,a)


def main():
    init();arrays=fold_arrays();rows=[];selections={}
    for kind in (False,True):
        name='route_kind_weights' if kind else 'route_weights'
        for fold,a in arrays.items():
            pools=list(prior_blocks(arrays,a).values())
            assert all(v['day'].max()<a['day'].min() for v in pools)
            chosen=select(pools,kind);pred=predict(a,chosen,kind)
            rows.append(dict(candidate=name,fold=fold,completed_source_folds=len(pools),score=score(a['y'],pred),
                gain=score(a['y'],pred)-score(a['y'],a['v2'])))
        chosen=select(list(arrays.values()),kind);selections[name]=chosen
        future=future_arrays();pred=predict(future,chosen,kind)
        np.save(CACHE/f'{name}_future.npy',pred)
        export(name,core=pred,metadata={'method':'Forward selected route ensemble, 50% shrink to v2, movement penalty .15',
            'selection':chosen,'validation':'Only source folds whose last target date precedes current first target date.'})
    report(rows,'route_weights')
    (OUT/'route_weight_selections.json').write_text(json.dumps(selections,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
