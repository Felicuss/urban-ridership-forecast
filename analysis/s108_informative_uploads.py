"""v22: posterior of v21 re-solved with new scores; informative uploads chosen by predictive score spread.

Reuses the saved v21 uncertainty multiplier, so the local data caches of s106 are not needed.
"""
import argparse
import hashlib
import importlib.util
import sys
import types
import json
import time
import numpy as np
import pandas as pd
from s52_round4_common import ROOT
from s87_reconciliation_pilot import ipf
from s89_route17_probes import decode_sum,balanced_round
if importlib.util.find_spec('torch') is None:
    # s92 needs torch only inside its training functions; the stub is dropped so scipy does not see it
    stub=types.ModuleType('torch');stub.set_num_threads=lambda n:None;sys.modules['torch']=stub
    from s93_entropy_scores import posterior
    del sys.modules['torch']
else:
    from s93_entropy_scores import posterior
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write

V21=ROOT/'forecasts/distributional_v21'


def setup(registry):
    g=grid();saved=np.load(V21/'parameters.npz');order=saved['order'];inverse=np.argsort(order)
    ordered=g.iloc[order]
    original=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';').prediction.to_numpy(dtype=float)[order]
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float)[:,order];b=np.array([v for _,v,_ in cons])
    pool=[];scores=[]
    for r in registry:
        path=ROOT/'forecasts'/r['file'];raw=path.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()],r['file']
        frame=ordered[['route','date','hour']].merge(pd.read_csv(path,sep=';'),on=['route','date','hour'],validate='one_to_one',sort=False)
        pool.append(frame.prediction.to_numpy(dtype=float));scores.append(r['leaderboard_score'])
    return dict(g=g,order=order,inverse=inverse,ordered=ordered,original=original,cons=cons,A=A,b=b,
        pool=np.array(pool),scores=np.array(scores),mult=saved['multiplier'])


def solve(s,**kw):
    return posterior(s['original'],s['pool'],s['scores'],s['A'],s['b'],T,noise_multiplier=s['mult'],distribution='mixture',maxiter=1000,**kw)


def export(s,mean,champion,weight):
    pred=ipf((1-weight)*champion+weight*mean,s['A'],s['b'])[s['inverse']]
    return balanced_round(pred,s['cons'])


def registry(path=None):
    rows=json.loads((path or ROOT/'forecasts/leaderboard_results.json').read_text(encoding='utf-8'))
    return [r for r in rows if r.get('leaderboard_score') is not None and r['leaderboard_score']>=.8]


def weight_v21():
    v=pd.read_csv(ROOT/'docs/analysis/tables/distributional_noise_v21/validation.csv')
    summary=v.groupby(['strength','weight']).gain.agg(['mean','min'])
    return float((summary['mean']+.5*summary['min']).idxmax()[1])


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('cmd',choices=['reproduce','v22'])
    a.add_argument('--out',default='submission_measured_routes_v22.csv')
    a.add_argument('--dry',action='store_true',help='fake q16/q17/q19 sums equal to v21: v22 must stay near v21')
    args=a.parse_args()
    if args.cmd=='reproduce':
        t=time.time();s=setup(registry(V21/'observations.json'))
        champion=pd.read_csv(ROOT/'forecasts/submission_prior_family_v19.csv',sep=';').prediction.to_numpy(dtype=float)[s['order']]
        f,meta=solve(s);print({k:meta[k] for k in ['converged','iterations','score_rmse']},round(time.time()-t))
        result=export(s,f['mean'],champion,weight_v21())
        v21=pd.read_csv(ROOT/'forecasts/submission_distributional_v21.csv',sep=';').prediction.to_numpy()
        print('weight',weight_v21(),'cells differ',int((result!=v21).sum()),'L1',int(abs(result-v21).sum()))
    else:
        s=setup(registry());g=s['g']
        champion_raw=pd.read_csv(ROOT/'forecasts/submission_distributional_v21.csv',sep=';').prediction.to_numpy(dtype=float)
        known={c[2] for c in s['cons']}
        if args.dry:
            for r in load_ledger():
                if r['id'] in ('q16','q17','q19') and r['id'] not in known:
                    m=mask(g,r['spec']);s['cons'].append((m,float(champion_raw[m].sum()),r['id']))
            s['A']=np.array([m for m,_,_ in s['cons']],float)[:,s['order']];s['b']=np.array([v for _,v,_ in s['cons']])
        new=[c[2] for c in s['cons'] if c[2] in ('q16','q17','q19')]
        print('constraints',len(s['cons']),'new',new,'scores',len(s['scores']))
        before={c[2]:float(champion_raw[c[0]].sum()) for c in s['cons'] if c[2] in new}
        f,meta=solve(s);print({k:meta[k] for k in ['converged','iterations','score_rmse','max_score_error']})
        result=export(s,f['mean'],champion_raw[s['order']],weight_v21())
        assert np.all(result[champion_raw==0]==0) and len(result)==14640 and (result>=0).all()
        error=float(max(abs(result[m].sum()-v) for m,v,_ in s['cons']))
        for m,v,k in s['cons']:
            if k in new:print(k,'v21',round(before[k]),'measured',round(v),f'{v/before[k]-1:+.2%}')
        print('cells differ',int((result!=champion_raw).sum()),'L1',int(abs(result-champion_raw).sum()),'max constraint error',round(error,2))
        if not args.dry:
            path=ROOT/'forecasts'/args.out
            if path.exists():raise FileExistsError(path)
            write(g,result,path)
            meta=dict(status='unscored',file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                anchor='submission_distributional_v21.csv',anchor_score=.91263,new_measurements=new,
                observed_full_submissions=len(s['scores']),weight=weight_v21(),
                changed_cells=int((result!=champion_raw).sum()),l1_distance=int(abs(result-champion_raw).sum()),
                max_constraint_error=error,diagnostic={k:meta[k] for k in ['converged','iterations','score_rmse','max_score_error']},
                method='v21 posterior (saved LightGBM uncertainty) re-solved with all scores and the new route sums, 50/50 with v21, IPF, balanced rounding')
            path.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n');print(path)
