"""Replay two quantile submissions and evaluate feedback refresh on historical folds."""
import numpy as np
import pandas as pd
from s112_daily_copula import validation_inputs
from s108_quantile_distribution import ROOT,CACHE,fold_arrays,residual_history,covariates,learn,quantile_prior,ipf,balanced_round
from s93_entropy_scores import posterior
TABLE=ROOT/'docs/analysis/tables/feedback_refresh_v24'


def main():
    TABLE.mkdir(parents=True,exist_ok=True)
    arrays=fold_arrays();history=residual_history(arrays);cov=covariates();rows=[]
    for key in ['R06','R08','B']:
        a,target,cons=validation_inputs(key,arrays);anchor=a['original'];champ=a['champion'];y=a['y'];total=y.sum()
        pool=a['pool'];scores=a['scores'];A=a['A'];b=a['b']
        noise,_,_=learn(history,cov,int(target.day.min()),target)
        q=np.load(CACHE/f'{key}_quantiles.npy');ref=np.argmin(abs(pool-anchor).sum(1));error=(1-scores[ref])*total
        priors={mode:quantile_prior(anchor,error,q-q[:,5,None] if mode=='centered' else q,noise,.5 if mode=='centered' else .25) for mode in ['centered','quantile_risk']}
        additions=[]
        for mode in ['centered','quantile_risk']:
            p,_=posterior(anchor,pool,scores,A,b,total,custom_prior=priors[mode],maxiter=1200)
            weight=.5 if mode=='centered' else 1.
            additions.append(balanced_round(ipf((1-weight)*champ+weight*p['mean'],A,b),cons))
        pool=np.r_[pool,np.array(additions)];scores=np.r_[scores,[round(float(1-abs(p-y).sum()/total),5) for p in additions]]
        incumbent=pool[scores.argmax()]
        for mode in ['original','centered','quantile_risk']:
            kwargs=dict(noise_multiplier=noise,distribution='mixture') if mode=='original' else dict(custom_prior=priors[mode])
            p,meta=posterior(anchor,pool,scores,A,b,total,maxiter=1200,**kwargs)
            for weight in [.5,1.]:
                pred=balanced_round(ipf((1-weight)*incumbent+weight*p['mean'],A,b),cons)
                gain=(abs(incumbent-y).sum()-abs(pred-y).sum())/total
                rows.append(dict(fold=key,mode=mode,weight=weight,gain=gain,score_rmse=meta['score_rmse']))
            print(rows[-2:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    result=pd.DataFrame(rows).groupby(['mode','weight']).gain.agg(['mean','min']);result.to_csv(TABLE/'selection.csv');print(result,flush=True)

if __name__=='__main__':main()
