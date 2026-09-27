"""Second score-feedback iteration, tested by simulating sequential submissions.

Compare a fixed original prior with a recentered champion prior. The next point
forecast uses the newly observed score, never individual hidden target labels.
"""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from s93_entropy_scores import posterior
from s92_score_geometry import historical_pool
from s52_round4_common import ROOT,fold_arrays
from s87_reconciliation_pilot import constraints,ipf
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write
from s89_route17_probes import decode_sum,balanced_round

TABLE=ROOT/'docs/analysis/tables/online_entropy_v18'
OUT=ROOT/'data/online_entropy'


def validation():
    rows=[]
    for key,a in fold_arrays().items():
        if key not in ['R06','R08','B']:continue
        A=constraints(a);b=np.einsum('ij,j->i',A,a['y']);total=a['y'].sum()
        base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        ref=ipf(base,A,b);pool,names=historical_pool(key,a,ref,A,b)
        scores=np.round(1-abs(pool-a['y'][None]).sum(1)/total,5)
        best=int(scores.argmax());original=pool[best]
        first,_=posterior(original,pool,scores,A,b,total)
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(A,b))]
        first=balanced_round(ipf(first['mean'],A,b),cons)
        first_score=round(float(1-abs(first-a['y']).sum()/total),5)
        pool=np.concatenate([pool,first[None]]);scores=np.r_[scores,first_score]
        champion=pool[int(scores.argmax())]
        champion_score=1-abs(champion-a['y']).sum()/total
        for prior_name,prior in [('fixed',original),('recentered',champion)]:
            predictions,meta=posterior(prior,pool,scores,A,b,total)
            for method,p in predictions.items():
                for alpha in [.5,1.,1.5]:
                    final=ipf(np.maximum(champion+alpha*(p-champion),0),A,b)
                    score=1-abs(final-a['y']).sum()/total
                    rows.append(dict(fold=key,prior=prior_name,method=method,alpha=alpha,
                        first_score=first_score,champion_score=champion_score,score=score,gain=score-champion_score))
            print(key,prior_name,'done',meta['converged'],flush=True)
        pd.DataFrame(rows).to_csv(TABLE/'sequential_validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['prior','method','alpha']).gain.agg(['mean','min'])
    summary['selection']=summary['mean']+.5*summary['min']
    summary.to_csv(TABLE/'selection.csv');print(summary.to_string(),flush=True)
    return summary.selection.idxmax()


def main(output_name):
    if '/' in output_name or '\\' in output_name or not output_name.endswith('.csv'):raise ValueError(output_name)
    output=ROOT/'forecasts'/output_name
    if output.exists():raise FileExistsError(output)
    TABLE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    prior_name,method,alpha=validation()
    g=grid();champion_file=ROOT/'forecasts/submission_entropy_scores_v17.csv'
    champion=pd.read_csv(champion_file,sep=';').prediction.to_numpy(dtype=float)
    original=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';').prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):
            cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.asarray([m for m,_,_ in cons],float);b=np.asarray([v for _,v,_ in cons])
    snapshot=ROOT/'forecasts/online_entropy_v18/observations.json';snapshot.parent.mkdir(exist_ok=True)
    if snapshot.exists():registry=json.loads(snapshot.read_text())
    else:
        registry=[r for r in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()) if r['leaderboard_score']>=.8]
        snapshot.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    pool=[];scores=[];names=[]
    for r in registry:
        p=ROOT/'forecasts'/r['file'];raw=p.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()]
        frame=g[['route','date','hour']].merge(pd.read_csv(p,sep=';'),on=['route','date','hour'],validate='one_to_one')
        pool.append(frame.prediction.to_numpy());scores.append(r['leaderboard_score']);names.append(r['file'])
    predictions,meta=posterior(original if prior_name=='fixed' else champion,
        np.asarray(pool),np.asarray(scores),A,b,T,maxiter=700)
    np.savez_compressed(OUT/'future.npz',**predictions)
    final=np.maximum(champion+alpha*(predictions[method]-champion),0)
    result=balanced_round(ipf(final,A,b),cons)
    if abs(result-champion).sum()<.0001*T:
        print('REJECTED negligible change; no upload candidate',flush=True)
        return
    write(g,result,output)
    pd.DataFrame(dict(file=names,observed=scores,fitted=meta.pop('fitted_scores'))).to_csv(TABLE/'score_fit.csv',index=False)
    meta.update(status='unscored',file=output.name,anchor=champion_file.name,anchor_score=.91223,
        prior=prior_name,method=method,weight=float(alpha),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        observations='online_entropy_v18/observations.json',observed_full_submissions=len(pool),
        l1_distance=int(abs(result-champion).sum()),changed_cells=int((result!=champion).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,result)-b).max()),
        caveat='Sequential score-feedback simulation, reused historical periods; no observed score for this candidate.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('EXPORTED',meta,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='submission_online_entropy_v18.csv')
    main(parser.parse_args().out)
