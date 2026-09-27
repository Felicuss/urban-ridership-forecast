"""Joint day residual copula conditioned on observed scalar scores and margins.

Only residuals strictly before forecast origin train the covariance. Historical
experiments simulate score feedback; they are not independent holdout estimates.
"""
import json
import numpy as np
import pandas as pd
from scipy.special import ndtr, logsumexp
from scipy.optimize import minimize
from s97_prior_family import (ROOT,fold_arrays,residual_history,uncertainty,posterior,
    historical_pool,constraints,ipf,balanced_round)

OUT=ROOT/'data/joint_scenarios'
TABLE=ROOT/'docs/analysis/tables/joint_scenarios_v20'


def residual_factor(history,cutoff,channels):
    p=history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last').copy()
    p['month']=(pd.Timestamp('2025-01-01')+pd.to_timedelta(p.day,unit='D')).dt.month
    sums=p.groupby(['route','month'])[['y','p']].transform('sum')
    baseline=p.p*sums.y/sums.p.clip(lower=1)
    p['residual']=np.clip((p.y-baseline)/(baseline+30),-1,1)
    p.loc[(p.p<=1)|((p.route.isin([7,50]))&(p.kind!=0)),'residual']=np.nan
    matrix=p.pivot(index='day',columns=['route','hour'],values='residual').reindex(columns=pd.MultiIndex.from_tuples(channels)).to_numpy()
    valid=np.isfinite(matrix); count=valid.sum(0)
    center=np.nansum(matrix,axis=0)/np.maximum(count,1)
    matrix=np.where(valid,matrix-center,0)
    std=np.sqrt((matrix**2).sum(0)/np.maximum(count,1))
    matrix/=np.maximum(std,.02)
    # Empirical correlation plus independent noise (shrinkage is applied later).
    factor=matrix.T/np.sqrt(max(len(matrix),1))
    norm=np.sqrt((factor**2).sum(1)); factor/=np.maximum(norm[:,None],1e-8)
    return factor,dict(training_days=len(matrix),last_training_day=int(p.day.max()))


def joint_posterior(anchor,pool,scores,A,b,total,multiplier,factor,rho=.5,scenarios=512,seed=2026,maxiter=500,block=None,whiten=False,penalty=1e-6):
    n=len(anchor); c=factor.shape[0]; d=n//c
    assert n==d*c
    if block is None:block=c
    assert scenarios%2==0
    rng=np.random.default_rng(seed)
    independent=rng.standard_normal((d,scenarios//2,c))
    common=np.einsum('dks,cs->dkc',rng.standard_normal((d,scenarios//2,factor.shape[1])),factor)
    normal=np.sqrt(rho)*common+np.sqrt(1-rho)*independent
    normal=np.concatenate([normal,-normal],axis=1)
    u=np.clip(ndtr(normal),1e-8,1-1e-8)
    z=np.where(u<.5,np.log(2*u),-np.log(2*(1-u)))
    if block!=c:
        assert c%block==0
        z=z.reshape(d,scenarios,c//block,block).transpose(0,2,1,3).reshape(-1,scenarios,block)
        d=n//block;c=block
    original=anchor.reshape(d,c); scale=((anchor+30)*(anchor>0)*multiplier).reshape(d,c)
    ref=int(np.argmin(abs(pool-anchor).sum(1)))
    lo,hi=.0001,2.
    for _ in range(35):
        alpha=(lo+hi)/2; support=np.maximum(0,original[:,None]+alpha*scale[:,None]*z)
        error=abs(support-original[:,None]).sum()/scenarios
        if error<(1-scores[ref])*total:lo=alpha
        else:hi=alpha
    weights=(original+30).sum(1); weights/=weights.sum()
    cost0=abs(support-original[:,None]).sum(2)
    keep=[i for i in range(len(pool)) if i!=ref]
    costs=np.stack([abs(support-pool[i].reshape(d,1,c)).sum(2)-cost0 for i in keep]+[cost0])
    group=np.einsum('gdc,dkc->gdk',A.reshape(-1,d,c),support)
    features=np.concatenate([costs,group])/(total*weights[None,:,None])
    targets=np.r_[scores[ref]-scores[keep],1-scores[ref],b/total]
    scaling=np.maximum(np.sqrt(np.einsum('gd,d->g',features.var(2),weights)),1e-5)
    features/=scaling[:,None,None]; targets/=scaling
    transform=np.eye(len(targets))
    if whiten:
        groups=rng.choice(d,size=16384,p=weights)
        choices=rng.integers(scenarios,size=16384)
        sample=features[:,groups,choices]-features.mean(2)[:,groups]
        gram=np.einsum('gi,hi->gh',sample,sample)/sample.shape[1]
        eigen,vectors=np.linalg.eigh(gram)
        transform=(vectors/np.sqrt(np.maximum(eigen,1e-7))[None]).T
    def objective(parameters,prob=False):
        parameters=np.einsum('gh,g->h',transform,parameters)
        logits=-np.einsum('g,gdk->dk',parameters,features)
        normalizer=logsumexp(logits,axis=1)
        q=np.exp(logits-normalizer[:,None])
        if prob:return q
        value=np.dot(weights,normalizer-np.log(scenarios))+np.dot(parameters,targets)+penalty*np.dot(parameters,parameters)/2
        grad=targets-np.einsum('gdk,dk,d->g',features,q,weights)+penalty*parameters
        return value,np.einsum('gh,h->g',transform,grad)
    fit=minimize(objective,np.zeros(len(targets)),jac=True,method='L-BFGS-B',options=dict(maxiter=maxiter,ftol=1e-12,gtol=1e-7,maxcor=30))
    q=objective(fit.x,True)
    mean=np.einsum('dkc,dk->dc',support,q).reshape(-1)
    losses=np.array([np.einsum('dk,dk->',abs(support-p.reshape(d,1,c)).sum(2),q) for p in pool])
    return mean,dict(converged=bool(fit.success),iterations=int(fit.nit),score_rmse=float(np.sqrt(np.mean((1-losses/total-scores)**2))),max_group_error=float(abs(np.einsum("gn,n->g",A,mean)-b).max()),effective_scenarios=float(np.mean(1/(q*q).sum(1))),rho=rho,scenarios=scenarios)


def validate():
    OUT.mkdir(parents=True,exist_ok=True);TABLE.mkdir(parents=True,exist_ok=True)
    arrays=fold_arrays();history=residual_history(arrays);rows=[]
    for key in ['R06','R08','B']:
        a=arrays[key]; y=a['y']; A=constraints(a);b=np.einsum("gn,n->g",A,y);total=y.sum()
        base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        pool,names=historical_pool(key,a,ipf(base,A,b),A,b)
        scores=np.round(1-abs(pool-y).sum(1)/total,5); original=pool[scores.argmax()]
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(A,b))]
        hours=np.tile(np.arange(24),len(base)//24)
        mult,_=uncertainty(history,int(a['day'].min()),a['route'],a['kind'],hours)
        for noise,family in [(None,'laplace'),(mult,'laplace'),(mult,'mixture')]:
            f,_=posterior(original,pool,scores,A,b,total,noise_multiplier=noise,distribution=family)
            p=balanced_round(ipf(f['mean'],A,b),cons)
            pool=np.r_[pool,p[None]];scores=np.r_[scores,round(float(1-abs(p-y).sum()/total),5)]
        champion=pool[scores.argmax()]; champion_score=1-abs(champion-y).sum()/total
        channels=list(zip(a['route'][:240].astype(int),hours[:240]))
        factor,info=residual_factor(history,int(a['day'].min()),channels)
        np.savez_compressed(OUT/f'validation_{key}.npz',original=original,pool=pool,scores=scores,A=A,b=b,y=y,mult=mult,factor=factor,champion=champion)
        for rho in [0.,.35,.7]:
            pred,meta=joint_posterior(original,pool,scores,A,b,total,mult,factor,rho=rho)
            np.save(OUT/f'{key}_rho{rho}.npy',pred)
            for weight in [.5,1.]:
                q=ipf((1-weight)*champion+weight*pred,A,b)
                score=1-abs(q-y).sum()/total
                row=dict(fold=key,weight=weight,score=score,gain=score-champion_score,champion_score=champion_score,**meta,**info)
                rows.append(row);print(row,flush=True)
            pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    print(pd.DataFrame(rows).groupby(['rho','weight']).gain.agg(['mean','min']),flush=True)

if __name__=='__main__':validate()
