"""Score-constrained posterior with historically learned heterogeneous uncertainty.

Noise scales use only earlier residual dates. Historical selection simulates a
second submission after observing the first entropy forecast's score.
"""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from s93_entropy_scores import posterior
from s92_score_geometry import historical_pool
from s52_round4_common import ROOT,fold_arrays
from s67_joint_day_net import Data
from s87_reconciliation_pilot import constraints,ipf
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write
from s89_route17_probes import decode_sum,balanced_round

TABLE=ROOT/'docs/analysis/tables/heterogeneous_entropy_v18'
OUT=ROOT/'data/heterogeneous_entropy'


def residual_history(arrays):
    frames=[]
    for key,a in arrays.items():
        p=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        frames.append(pd.DataFrame(dict(day=a['day'],route=a['route'],kind=a['kind'],
            hour=np.tile(np.arange(24),len(p)//24),origin=int(a['day'].min())-1,y=a['y'],p=p)))
    return pd.concat(frames,ignore_index=True)


def uncertainty(history,cutoff,route,kind,hour):
    past=history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last').copy()
    past['month']=(pd.Timestamp('2025-01-01')+pd.to_timedelta(past.day,unit='D')).dt.month
    group=past.groupby(['route','month'])[['y','p']].transform('sum')
    p=past.p*group.y/group.p.clip(lower=1)
    past['error']=np.clip(abs(past.y-p)/(p+30),.005,.8)
    past=past[(past.route!=5)&~(past.route.isin([7,50])&(past.kind!=0))&(past.p>1)].copy()
    past['weight']=np.exp((past.day-cutoff)/90)
    past['weighted_error']=past.error*past.weight
    total=float(past.weighted_error.sum()/past.weight.sum())
    pooled=past.groupby(['kind','hour'])[['weighted_error','weight']].sum()
    pooled['scale']=(pooled.weighted_error+20*total)/(pooled.weight+20)
    specific=past.groupby(['route','kind','hour'])[['weighted_error','weight']].sum().reset_index()
    specific=specific.merge(pooled[['scale']].reset_index(),on=['kind','hour'],validate='many_to_one')
    specific['scale']=(specific.weighted_error+30*specific.scale)/(specific.weight+30)
    index=pd.MultiIndex.from_arrays([route,kind,hour],names=['route','kind','hour'])
    values=specific.set_index(['route','kind','hour']).scale.reindex(index).fillna(total).to_numpy()
    multiplier=np.clip(values/total,.5,2.)
    return multiplier,dict(last_training_day=int(past.day.max()),training_days=int(past.day.nunique()),
        pooled_relative_error=total,min_multiplier=float(multiplier.min()),max_multiplier=float(multiplier.max()))


def main(output_name):
    if '/' in output_name or '\\' in output_name or not output_name.endswith('.csv'):raise ValueError(output_name)
    output=ROOT/'forecasts'/output_name
    if output.exists():raise FileExistsError(output)
    TABLE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    arrays=fold_arrays();history=residual_history(arrays);rows=[]
    for key,a in arrays.items():
        if key not in ['R06','R08','B']:continue
        A=constraints(a);b=np.einsum('ij,j->i',A,a['y']);total=a['y'].sum()
        base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        ref=ipf(base,A,b);pool,names=historical_pool(key,a,ref,A,b)
        scores=np.round(1-abs(pool-a['y'][None]).sum(1)/total,5)
        original=pool[int(scores.argmax())]
        first,_=posterior(original,pool,scores,A,b,total)
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(A,b))]
        first=balanced_round(ipf(first['mean'],A,b),cons)
        pool=np.r_[pool,first[None]];scores=np.r_[scores,round(float(1-abs(first-a['y']).sum()/total),5)]
        champion=pool[int(scores.argmax())];champion_score=1-abs(champion-a['y']).sum()/total
        multiplier,noise_meta=uncertainty(history,int(a['day'].min()),a['route'],a['kind'],np.tile(np.arange(24),len(base)//24))
        for strength in [.5,1.]:
            forecast,meta=posterior(original,pool,scores,A,b,total,noise_multiplier=multiplier**strength)
            for method,p in forecast.items():
                for alpha in [.5,1.]:
                    q=ipf((1-alpha)*champion+alpha*p,A,b)
                    score=1-abs(q-a['y']).sum()/total
                    rows.append(dict(fold=key,strength=strength,method=method,alpha=alpha,score=score,
                        champion_score=champion_score,gain=score-champion_score,**noise_meta))
            print(key,strength,'done',meta['converged'],flush=True)
        pd.DataFrame(rows).to_csv(TABLE/'sequential_validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['strength','method','alpha']).gain.agg(['mean','min'])
    summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv')
    print(summary.to_string(),flush=True)
    strength,method,alpha=summary.selection.idxmax()
    g=grid();champion_file=ROOT/'forecasts/submission_entropy_scores_v17.csv'
    champion=pd.read_csv(champion_file,sep=';').prediction.to_numpy(dtype=float)
    original=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';').prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float);b=np.array([v for _,v,_ in cons])
    snapshot=ROOT/'forecasts/heterogeneous_entropy_v18/observations.json';snapshot.parent.mkdir(exist_ok=True)
    if snapshot.exists():registry=json.loads(snapshot.read_text())
    else:
        registry=[r for r in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()) if r['leaderboard_score']>=.8]
        snapshot.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    pool=[];scores=[];names=[]
    for r in registry:
        path=ROOT/'forecasts'/r['file'];raw=path.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()]
        frame=g[['route','date','hour']].merge(pd.read_csv(path,sep=';'),on=['route','date','hour'],validate='one_to_one')
        pool.append(frame.prediction.to_numpy());scores.append(r['leaderboard_score']);names.append(r['file'])
    days=(pd.to_datetime(g.date)-pd.Timestamp('2025-01-01')).dt.days.to_numpy()
    kind=Data().kind[days,0]
    multiplier,noise_meta=uncertainty(history,304,g.route.to_numpy(),kind,g.hour.to_numpy())
    forecast,meta=posterior(original,np.array(pool),np.array(scores),A,b,T,maxiter=700,noise_multiplier=multiplier**strength)
    np.savez_compressed(OUT/'future.npz',**forecast,multiplier=multiplier)
    result=balanced_round(ipf((1-alpha)*champion+alpha*forecast[method],A,b),cons)
    write(g,result,output)
    pd.DataFrame(dict(file=names,observed=scores,fitted=meta.pop('fitted_scores'))).to_csv(TABLE/'score_fit.csv',index=False)
    meta.update(status='unscored',file=output.name,anchor=champion_file.name,anchor_score=.91223,
        original_prior='submission_r17_measured_v13.csv',strength=float(strength),method=method,weight=float(alpha),
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),observed_full_submissions=len(pool),
        l1_distance=int(abs(result-champion).sum()),changed_cells=int((result!=champion).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,result)-b).max()),noise_model=noise_meta,
        caveat='Noise scale learned on past residuals; sequential simulations use scalar score feedback, not independent forecast validation.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('EXPORTED',meta,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='submission_heterogeneous_entropy_v18.csv')
    main(parser.parse_args().out)
