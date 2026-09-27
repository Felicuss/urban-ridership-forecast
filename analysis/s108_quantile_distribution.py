"""Conditional residual quantiles inspired by distributional boosting/M5.
Our residual-quantile implementation; not a reproduction of NGBoost.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
from s106_distributional_noise import covariates,design,learn
from s95_heterogeneous_entropy import residual_history
from s52_round4_common import ROOT,fold_arrays
from s98_joint_scenarios import OUT,ipf,balanced_round
from s93_entropy_scores import posterior,prior_grid
TABLE=ROOT/'docs/analysis/tables/quantile_distribution_v22'
CACHE=ROOT/'data/quantile_distribution'
LEVELS=np.array([.01,.05,.1,.2,.35,.5,.65,.8,.9,.95,.99])


def train_quantiles(history,cov,cutoff,target,variant="plain"):
    past=history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last').copy()
    past['month']=(pd.Timestamp('2025-01-01')+pd.to_timedelta(past.day,unit='D')).dt.month
    sums=past.groupby(['route','month'])[['y','p']].transform('sum');base=past.p*sums.y/sums.p.clip(lower=1)
    past['residual']=np.clip((past.y-base)/(base+30),-.95,2.)
    past=past[(past.route!=5)&(past.p>1)&~(past.route.isin([7,50])&(past.kind!=0))]
    x=design(past,cov);xt=design(target,cov);weights=np.exp((past.day-cutoff)/90)
    if variant=='stationary':
        x=x.drop(columns=['day']);xt=xt.drop(columns=['day'])
    elif variant=='jitter':
        x=x.copy();rng=np.random.default_rng(42)
        x['day']+=rng.normal(0,30,len(x))
        x['log_level']+=rng.normal(0,.05,len(x))
    elif variant!='plain':raise ValueError(variant)
    values=[]
    for q in LEVELS:
        model=lgb.LGBMRegressor(objective='quantile',alpha=q,n_estimators=180,num_leaves=12,min_child_samples=180,learning_rate=.025,reg_lambda=20,verbosity=-1,n_jobs=2,random_state=42)
        model.fit(x,past.residual,sample_weight=weights);values.append(model.predict(xt))
    return np.sort(np.array(values).T,axis=1)


def quantile_prior(anchor,total_error,predicted,noise,shrink):
    support,prior,_=prior_grid(anchor,total_error,noise_multiplier=noise,distribution='mixture')
    probabilities=prior.cumsum()-prior/2;levels=np.r_[.0001,LEVELS,.9999]
    low=predicted[:,0]-2*(predicted[:,1]-predicted[:,0]+.01)
    high=predicted[:,-1]+2*(predicted[:,-1]-predicted[:,-2]+.01)
    values=np.c_[low,predicted,high]
    quantiles=np.array([np.interp(probabilities,levels,row) for row in values])
    old_offset=(support-anchor[:,None])/np.maximum(anchor[:,None]+30,1)
    offset=(1-shrink)*old_offset+shrink*quantiles
    lo,hi=0.,10.
    for _ in range(45):
        alpha=(lo+hi)/2
        proposed=np.maximum(0,anchor[:,None]+alpha*(anchor[:,None]+30)*offset);proposed[anchor==0]=0
        error=np.einsum('nk,k->',abs(proposed-anchor[:,None]),prior)
        if error<total_error:lo=alpha
        else:hi=alpha
    return proposed,prior


def validate():
    CACHE.mkdir(parents=True,exist_ok=True);TABLE.mkdir(parents=True,exist_ok=True)
    arrays=fold_arrays();history=residual_history(arrays);cov=covariates();rows=[]
    for key in ['R06','R08','B']:
        a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum()
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(a['A'],a['b']))]
        markov=balanced_round(ipf(np.load(OUT/f'{key}_markov_0.8.npy'),a['A'],a['b']),cons)
        pool=np.r_[a['pool'],markov[None]];scores=np.r_[a['scores'],round(float(1-abs(markov-y).sum()/total),5)]
        previous=pool[scores.argmax()]
        v21=balanced_round(ipf(.5*previous+.5*np.load(ROOT/f'data/distributional_noise/{key}_1.0.npy'),a['A'],a['b']),cons)
        pool=np.r_[pool,v21[None]];scores=np.r_[scores,round(float(1-abs(v21-y).sum()/total),5)]
        champion=pool[scores.argmax()];score0=1-abs(champion-y).sum()/total
        f=arrays[key];target=pd.DataFrame(dict(day=f['day'],route=f['route'],hour=np.tile(np.arange(24),len(y)//24),kind=f['kind'],p=a['original']))
        noise,_,_=learn(history,cov,int(f['day'].min()),target)
        quantiles=train_quantiles(history,cov,int(f['day'].min()),target);np.save(CACHE/f'{key}_quantiles.npy',quantiles)
        ref=np.argmin(abs(pool-a['original']).sum(1));error=(1-scores[ref])*total
        for shrink in [.25,.5,1.]:
            custom=quantile_prior(a['original'],error,quantiles,noise,shrink)
            p,meta=posterior(a['original'],pool,scores,a['A'],a['b'],total,custom_prior=custom,maxiter=800)
            for weight in [.5,1.]:
                pred=balanced_round(ipf((1-weight)*champion+weight*p['mean'],a['A'],a['b']),cons)
                score=1-abs(pred-y).sum()/total
                rows.append(dict(fold=key,shrink=shrink,weight=weight,score=score,gain=score-score0,fit_rmse=meta['score_rmse']))
            print(rows[-2:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['shrink','weight']).gain.agg(['mean','min']);summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv');print(summary,flush=True)

if __name__=='__main__':validate()
