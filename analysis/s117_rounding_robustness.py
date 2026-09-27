"""Audit remaining feedback directions across priors and rounded score intervals.
No submission is automatically exported by this research script.
"""
import json,hashlib
import numpy as np
import pandas as pd
from s113_two_candidates import prepare
from s108_quantile_distribution import ROOT,quantile_prior,ipf,balanced_round
from s93_entropy_scores import posterior
from s84_block_probes import T
OUT=ROOT/'docs/analysis/tables/rounding_robustness_v25'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    g,order,inverse,anchor,champ,cons,A,b,pool,scores,noise,q,corr=prepare()
    registry=json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    for name in ['submission_centered_quantiles_v22.csv','submission_quantile_shape_v23.csv','submission_feedback_v24.csv']:
        r=next(r for r in registry if r['file']==name);p=ROOT/'forecasts'/name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
        frame=pd.read_csv(p,sep=';');pd.testing.assert_frame_equal(frame[['route','date','hour']],g[['route','date','hour']],check_dtype=False)
        pool=np.r_[pool,frame.prediction.to_numpy(dtype=float)[order][None]];scores=np.r_[scores,r['leaderboard_score']]
    (OUT/'observations.json').write_text(json.dumps([r for r in registry if r['leaderboard_score']>=.8],ensure_ascii=False,indent=2)+'\n')
    ref=np.argmin(abs(pool-anchor).sum(1));distributions={};means={};diagnostics=[]
    rng=np.random.default_rng(20260927);jitter=rng.uniform(-4.9e-6,4.9e-6,len(scores))
    for mode in ['original','centered','quantile_risk']:
        for scenario,shift in [('reported',np.zeros_like(scores)),('jitter_plus',jitter),('jitter_minus',-jitter)]:
            observed=scores+shift
            kwargs=dict(noise_multiplier=noise,distribution='mixture') if mode=='original' else dict(custom_prior=quantile_prior(anchor,(1-observed[ref])*T,q-q[:,5,None] if mode=='centered' else q,noise,.5 if mode=='centered' else .25))
            dist,meta=posterior(anchor,pool,observed,A,b,T,maxiter=1400,return_distribution=True,**kwargs)
            assert meta['score_rmse']<5e-6,meta
            distributions[(mode,scenario)]=dist
            if scenario=='reported':means[mode]=dist['mean']
            diagnostics.append(dict(mode=mode,scenario=scenario,**meta));print(mode,scenario,meta['score_rmse'],flush=True)
    means['mean_of_priors']=np.mean(list(means.values()),axis=0)
    rows=[];candidate_meta=[]
    for mode,mean in means.items():
        for weight in [.5,1.]:
            final=balanced_round(ipf((1-weight)*champ+weight*mean,A,b)[inverse],cons)[order]
            candidate_meta.append(dict(candidate=mode,weight=weight,l1_distance=float(abs(final-champ).sum()),changed_cells=int((final!=champ).sum())))
            for (evaluator,scenario),p in distributions.items():
                gain=np.einsum('nk,nk->',abs(p['support']-champ[:,None])-abs(p['support']-final[:,None]),p['probability'])/T
                rows.append(dict(candidate=mode,weight=weight,evaluator=evaluator,scenario=scenario,expected_gain=float(gain)))
    result=pd.DataFrame(rows);result.to_csv(OUT/'expectations.csv',index=False)
    summary=result.groupby(['candidate','weight']).expected_gain.agg(['mean','min','max']);summary.to_csv(OUT/'summary.csv')
    pd.DataFrame(candidate_meta).to_csv(OUT/'candidate_distances.csv',index=False)
    (OUT/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
    print(summary.to_string(),flush=True)

if __name__=='__main__':main()
