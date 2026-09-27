"""Export ordinary forecast candidates; keep v21 and its recorded score unchanged."""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from s108_quantile_distribution import ROOT, fold_arrays, residual_history, covariates, learn, train_quantiles, quantile_prior, ipf, balanced_round
from s112_daily_copula import correlation, scenario_posterior
from s93_entropy_scores import posterior
from s84_block_probes import grid, margins, decoded, load_ledger, mask, T, write
from s89_route17_probes import decode_sum
from s67_joint_day_net import Data

SNAPSHOT = ROOT/'forecasts/quantile_copula_candidates'


def prepare():
    SNAPSHOT.mkdir(exist_ok=True)
    g=grid();order=g.sort_values(['date','route','hour']).index.to_numpy();inverse=np.argsort(order);ordered=g.iloc[order]
    original=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';').prediction.to_numpy(dtype=float)[order]
    champion=pd.read_csv(ROOT/'forecasts/submission_distributional_v21.csv',sep=';').prediction.to_numpy(dtype=float)[order]
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):
            cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float)[:,order];b=np.array([v for _,v,_ in cons])
    snapshot=SNAPSHOT/'observations.json'
    if snapshot.exists():registry=json.loads(snapshot.read_text())
    else:
        registry=[r for r in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()) if r['leaderboard_score']>=.8]
        snapshot.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    pool=[];scores=[]
    for r in registry:
        path=ROOT/'forecasts'/r['file'];raw=path.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()]
        frame=ordered[['route','date','hour']].merge(pd.read_csv(path,sep=';'),on=['route','date','hour'],validate='one_to_one',sort=False)
        assert len(frame)==len(g) and frame.prediction.notna().all()
        pool.append(frame.prediction.to_numpy());scores.append(r['leaderboard_score'])
    history=residual_history(fold_arrays());cov=covariates()
    days=(pd.to_datetime(ordered.date)-pd.Timestamp('2025-01-01')).dt.days.to_numpy()
    target=pd.DataFrame(dict(day=days,route=ordered.route.to_numpy(),hour=ordered.hour.to_numpy(),kind=Data().kind[days,0],p=original))
    cache=SNAPSHOT/'learned_prior.npz'
    if cache.exists():
        saved=np.load(cache);noise=saved['noise'];q=saved['quantiles'];corr=saved['correlation']
        np.testing.assert_array_equal(saved['order'],order)
    else:
        noise,model,info=learn(history,cov,304,target)
        model.booster_.save_model(str(SNAPSHOT/'noise_model.txt'))
        q=train_quantiles(history,cov,304,target)
        corr,corrinfo=correlation(history,304,sorted(target.route.unique()))
        np.savez_compressed(cache,noise=noise,quantiles=q,correlation=corr,order=order)
        (SNAPSHOT/'training.json').write_text(json.dumps(dict(noise=info,correlation=corrinfo,quantile_levels=[.01,.05,.1,.2,.35,.5,.65,.8,.9,.95,.99]),indent=2)+'\n')
    return g,order,inverse,original,champion,cons,A,b,np.array(pool),np.array(scores),noise,q,corr


def main(mode):
    names={'centered':'submission_centered_quantiles_v22.csv','copula':'submission_daily_copula_v23.csv','quantile_risk':'submission_quantile_shape_v23.csv'}
    output=ROOT/'forecasts'/names[mode]
    if output.exists():raise FileExistsError(output)
    g,order,inverse,original,champion,cons,A,b,pool,scores,noise,q,corr=prepare()
    ref=np.argmin(abs(pool-original).sum(1));error=(1-scores[ref])*T
    if mode=='quantile_risk':shrink=.25;weight=1.
    else:q=q-q[:,5,None];shrink=.5;weight=.5
    support,prior=quantile_prior(original,error,q,noise,shrink)
    if mode=='copula':
        val=pd.read_csv(ROOT/'docs/analysis/tables/daily_copula_v23/validation.csv')
        summary=val[val.strength>0].groupby(['strength','weight']).gain.agg(['mean','min'])
        strength,weight=(summary['mean']+.5*summary['min']).idxmax()
        selected=val[(val.strength==strength)&(val.weight==weight)]
        assert selected.gain.mean()>0 and selected.gain.min()>-.0003,summary
        mean,diagnostic=scenario_posterior(original,pool,scores,A,b,T,support,prior,corr,strength=float(strength),samples=1024)
    else:
        predicted,diagnostic=posterior(original,pool,scores,A,b,T,custom_prior=(support,prior),maxiter=1200)
        mean=predicted['mean']
        if mode=='centered':
            val=pd.read_csv(ROOT/'docs/analysis/tables/quantile_distribution_v22/centered.csv')
            selected=val[(val.variant=='centered')&(val.shrink==shrink)&(val.weight==weight)]
        else:
            val=pd.read_csv(ROOT/'docs/analysis/tables/quantile_distribution_v22/validation.csv')
            selected=val[(val.shrink==shrink)&(val.weight==weight)]
    print('DIAGNOSTIC',diagnostic,flush=True)
    assert len(selected)==3
    assert diagnostic['score_rmse']<5e-6,diagnostic
    pred=ipf((1-weight)*champion+weight*mean,A,b)[inverse]
    result=balanced_round(pred,cons);baseline=champion[inverse]
    assert np.all(result[baseline==0]==0)
    assert len(result)==14640 and np.isfinite(result).all() and (result>=0).all()
    assert not g.duplicated(['route','date','hour']).any()
    err=float(abs(np.einsum('gn,n->g',A[:,inverse],result)-b).max())
    assert err<5,err
    assert not np.array_equal(result,baseline)
    write(g,result,output)
    meta=dict(status='unscored',file=output.name,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        anchor='submission_distributional_v21.csv',anchor_score=.91263,mode=mode,
        observed_full_submissions=len(pool),prior_shrink=shrink,blend_weight=float(weight),
        validation_mean_gain=float(selected.gain.mean()),validation_min_gain=float(selected.gain.min()),
        changed_cells=int((result!=baseline).sum()),l1_distance=int(abs(result-baseline).sum()),
        max_constraint_error=err,diagnostic=diagnostic,
        caveat='Reused development simulations with aggregate and leaderboard feedback; future LB unknown.')
    output.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    np.save(SNAPSHOT/f'{mode}_posterior_mean.npy',mean)
    print('EXPORTED',meta,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['centered','copula','quantile_risk']);main(parser.parse_args().mode)
