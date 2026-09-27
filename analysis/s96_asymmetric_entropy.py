"""Third feedback round: historically learned asymmetric residual tails."""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from s95_heterogeneous_entropy import residual_history,uncertainty
from s93_entropy_scores import posterior
from s92_score_geometry import historical_pool
from s52_round4_common import ROOT,fold_arrays
from s67_joint_day_net import Data
from s87_reconciliation_pilot import constraints,ipf
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write
from s89_route17_probes import decode_sum,balanced_round

TABLE=ROOT/'docs/analysis/tables/asymmetric_entropy_v19'
OUT=ROOT/'data/asymmetric_entropy'


def asymmetry(history,cutoff,route,kind,hour):
    past=history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last').copy()
    past['month']=(pd.Timestamp('2025-01-01')+pd.to_timedelta(past.day,unit='D')).dt.month
    totals=past.groupby(['route','month'])[['y','p']].transform('sum')
    adjusted=past.p*totals.y/totals.p.clip(lower=1)
    past['residual']=np.clip((past.y-adjusted)/(adjusted+30),-.8,.8)
    past=past[(past.route!=5)&~(past.route.isin([7,50])&(past.kind!=0))&(past.p>1)].copy()
    past['weight']=np.exp((past.day-cutoff)/90)
    past['positive']=past.weight*np.maximum(past.residual,0)
    past['negative']=past.weight*np.maximum(-past.residual,0)
    pooled=past.groupby(['kind','hour'])[['positive','negative','weight']].sum()
    average=past[['positive','negative']].sum()/past.weight.sum()
    for col in ['positive','negative']:pooled[col]=(pooled[col]+20*average[col])/(pooled.weight+20)
    group=past.groupby(['route','kind','hour'])[['positive','negative','weight']].sum().reset_index()
    group=group.merge(pooled[['positive','negative']].reset_index(),on=['kind','hour'],suffixes=('','_prior'))
    for col in ['positive','negative']:group[col]=(group[col]+30*group[col+'_prior'])/(group.weight+30)
    group['skew']=np.clip(.5*np.log((group.positive+.001)/(group.negative+.001)),-.35,.35)
    index=pd.MultiIndex.from_arrays([route,kind,hour],names=['route','kind','hour'])
    values=group.set_index(['route','kind','hour'])['skew'].reindex(index).fillna(0).to_numpy()
    return values,dict(last_training_day=int(past.day.max()),training_days=int(past.day.nunique()),
        min_skew=float(values.min()),max_skew=float(values.max()))


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
        pool,names=historical_pool(key,a,ipf(base,A,b),A,b)
        scores=np.round(1-abs(pool-a['y'][None]).sum(1)/total,5);original=pool[int(scores.argmax())]
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(A,b))]
        hours=np.tile(np.arange(24),len(base)//24)
        multiplier,_=uncertainty(history,int(a['day'].min()),a['route'],a['kind'],hours)
        skew,info=asymmetry(history,int(a['day'].min()),a['route'],a['kind'],hours)
        for noise in [None,multiplier]:
            forecast,_=posterior(original,pool,scores,A,b,total,noise_multiplier=noise)
            p=balanced_round(ipf(forecast['mean'],A,b),cons)
            pool=np.r_[pool,p[None]];scores=np.r_[scores,round(float(1-abs(p-a['y']).sum()/total),5)]
        champion=pool[int(scores.argmax())];champion_score=1-abs(champion-a['y']).sum()/total
        for strength in [.25,.5,1.]:
            forecast,meta=posterior(original,pool,scores,A,b,total,noise_multiplier=multiplier,skew=skew*strength)
            for alpha in [.5,1.]:
                q=ipf((1-alpha)*champion+alpha*forecast['mean'],A,b)
                score=1-abs(q-a['y']).sum()/total
                rows.append(dict(fold=key,strength=strength,alpha=alpha,score=score,
                    champion_score=champion_score,gain=score-champion_score,**info))
            print(key,strength,'done',meta['converged'],flush=True)
        pd.DataFrame(rows).to_csv(TABLE/'sequential_validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['strength','alpha']).gain.agg(['mean','min'])
    summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv')
    print(summary.to_string(),flush=True);strength,alpha=summary.selection.idxmax()
    if summary['mean'].max()<=0:
        (TABLE/'decision.json').write_text(json.dumps(dict(status='rejected_no_upload',reason='All configurations have negative mean sequential gain.'),indent=2)+'\n')
        return
    g=grid();anchor_file=ROOT/'forecasts/submission_heterogeneous_entropy_v18.csv'
    champion=pd.read_csv(anchor_file,sep=';').prediction.to_numpy(dtype=float)
    original=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';').prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float);b=np.array([v for _,v,_ in cons])
    snapshot=ROOT/'forecasts/asymmetric_entropy_v19/observations.json';snapshot.parent.mkdir(exist_ok=True)
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
    days=(pd.to_datetime(g.date)-pd.Timestamp('2025-01-01')).dt.days.to_numpy();kind=Data().kind[days,0]
    multiplier,_=uncertainty(history,304,g.route.to_numpy(),kind,g.hour.to_numpy())
    skew,noise_meta=asymmetry(history,304,g.route.to_numpy(),kind,g.hour.to_numpy())
    forecast,meta=posterior(original,np.array(pool),np.array(scores),A,b,T,maxiter=700,
        noise_multiplier=multiplier,skew=skew*strength)
    result=balanced_round(ipf((1-alpha)*champion+alpha*forecast['mean'],A,b),cons)
    write(g,result,output)
    np.savez_compressed(snapshot.parent/'prior_parameters.npz',multiplier=multiplier,skew=skew,strength=strength)
    pd.DataFrame(dict(file=names,observed=scores,fitted=meta.pop('fitted_scores'))).to_csv(TABLE/'score_fit.csv',index=False)
    meta.update(status='unscored',file=output.name,anchor=anchor_file.name,anchor_score=.91253,
        original_prior='submission_r17_measured_v13.csv',skew_strength=float(strength),weight=float(alpha),
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),observed_full_submissions=len(pool),
        changed_cells=int((result!=champion).sum()),l1_distance=int(abs(result-champion).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,result)-b).max()),noise_model=noise_meta,
        caveat='Third-round historical score-feedback simulation; no observed LB score for this candidate.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n');print('EXPORTED',meta,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='submission_asymmetric_entropy_v19.csv')
    main(parser.parse_args().out)
