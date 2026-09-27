"""Refresh priors with confirmed v22/v23 scores; export one consensus-screened candidate."""
import json,hashlib
import numpy as np
import pandas as pd
from s113_two_candidates import prepare, SNAPSHOT
from s108_quantile_distribution import ROOT,quantile_prior,ipf,balanced_round
from s93_entropy_scores import posterior
from s84_block_probes import T,write


def main():
    output=ROOT/'forecasts/submission_feedback_v24.csv'
    if output.exists():raise FileExistsError(output)
    g,order,inverse,anchor,champ,cons,A,b,pool,scores,noise,q,corr=prepare()
    registry=json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    for name in ['submission_centered_quantiles_v22.csv','submission_quantile_shape_v23.csv']:
        r=next(r for r in registry if r['file']==name);raw=(ROOT/'forecasts'/name).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==r['sha256']
        f=pd.read_csv(ROOT/'forecasts'/name,sep=';')
        pd.testing.assert_frame_equal(f[['route','date','hour']],g[['route','date','hour']],check_dtype=False)
        pool=np.r_[pool,f.prediction.to_numpy(dtype=float)[order][None]];scores=np.r_[scores,r['leaderboard_score']]
    dest=ROOT/'forecasts/feedback_v24';dest.mkdir(exist_ok=True)
    (dest/'observations.json').write_text(json.dumps([r for r in registry if r['leaderboard_score']>=.8],ensure_ascii=False,indent=2)+'\n')
    ref=np.argmin(abs(pool-anchor).sum(1));error=(1-scores[ref])*T
    distributions={};candidates={};diagnostics={}
    for mode in ['original','centered','quantile_risk']:
        kwargs=dict(noise_multiplier=noise,distribution='mixture') if mode=='original' else dict(custom_prior=quantile_prior(anchor,error,q-q[:,5,None] if mode=='centered' else q,noise,.5 if mode=='centered' else .25))
        p,meta=posterior(anchor,pool,scores,A,b,T,maxiter=1200,return_distribution=True,**kwargs)
        assert meta['score_rmse']<5e-6
        distributions[mode]=p;diagnostics[mode]=meta
        for weight in [.5,1.]:
            final=balanced_round(ipf((1-weight)*champ+weight*p['mean'],A,b)[inverse],cons)
            candidates[(mode,weight)]=final
    rows=[]
    for (mode,weight),final in candidates.items():
        for evaluator,p in distributions.items():
            gain=np.einsum('nk,nk->',abs(p['support']-champ[:,None])-abs(p['support']-final[order,None]),p['probability'])/T
            rows.append(dict(mode=mode,weight=weight,evaluator=evaluator,expected_gain=float(gain)))
    audit=pd.DataFrame(rows);audit.to_csv(dest/'cross_prior_expectations.csv',index=False)
    val=pd.read_csv(ROOT/'docs/analysis/tables/feedback_refresh_v24/validation.csv')
    stats=val.groupby(['mode','weight']).gain.agg(['mean','min'])
    robust=audit.groupby(['mode','weight']).expected_gain.min()
    eligible=stats[(stats['min']>0)&(robust>0)]
    print('CROSS PRIOR',audit.to_string(index=False),flush=True)
    if len(eligible)==0:raise RuntimeError('No candidate passes historical and cross-prior screen')
    selected=(eligible['mean']+.5*eligible['min']).idxmax();result=candidates[selected]
    assert len(result)==14640 and np.isfinite(result).all() and (result>=0).all()
    assert np.all(result[champ[inverse]==0]==0)
    err=float(abs(np.einsum('gn,n->g',A[:,inverse],result)-b).max());assert err<5
    write(g,result,output)
    meta=dict(status='unscored',file=output.name,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),anchor='submission_distributional_v21.csv',anchor_score=.91263,mode=selected[0],weight=selected[1],observed_full_submissions=len(pool),validation_mean_gain=float(stats.loc[selected,'mean']),validation_min_gain=float(stats.loc[selected,'min']),minimum_model_expected_gain=float(robust.loc[selected]),changed_cells=int((result!=champ[inverse]).sum()),l1_distance=int(abs(result-champ[inverse]).sum()),max_constraint_error=err,diagnostics=diagnostics,caveat='Development and posterior expectations are not independent LB estimates; best confirmed remains v21.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n');print('EXPORTED',meta,flush=True)

if __name__=='__main__':main()
