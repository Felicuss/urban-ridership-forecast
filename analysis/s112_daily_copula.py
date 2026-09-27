"""Daily cross-route Gaussian-copula scenarios conditioned on observed feedback.
This is a finite-scenario approximation, not recovered future hourly labels.
"""
import json
import numpy as np
import pandas as pd
from scipy.special import ndtr, logsumexp
from scipy.optimize import minimize
from s108_quantile_distribution import (ROOT, OUT, CACHE, fold_arrays, residual_history,
    covariates, learn, quantile_prior, ipf, balanced_round)
TABLE = ROOT/'docs/analysis/tables/daily_copula_v23'
SAVE = ROOT/'data/daily_copula'


def validation_inputs(key, arrays):
    a = dict(np.load(OUT/f'validation_{key}.npz'))
    y = a['y']; total = y.sum()
    cons = [(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(a['A'],a['b']))]
    markov = balanced_round(ipf(np.load(OUT/f'{key}_markov_0.8.npy'),a['A'],a['b']),cons)
    pool = np.r_[a['pool'],markov[None]]
    scores = np.r_[a['scores'],round(float(1-abs(markov-y).sum()/total),5)]
    previous = pool[scores.argmax()]
    v21 = balanced_round(ipf(.5*previous+.5*np.load(ROOT/f'data/distributional_noise/{key}_1.0.npy'),a['A'],a['b']),cons)
    a['pool'] = np.r_[pool,v21[None]]
    a['scores'] = np.r_[scores,round(float(1-abs(v21-y).sum()/total),5)]
    a['champion'] = a['pool'][a['scores'].argmax()]
    f = arrays[key]
    target = pd.DataFrame(dict(day=f['day'],route=f['route'],hour=np.tile(np.arange(24),len(y)//24),kind=f['kind'],p=a['original']))
    return a, target, cons


def correlation(history, cutoff, routes):
    past = history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last').copy()
    past['month'] = (pd.Timestamp('2025-01-01')+pd.to_timedelta(past.day,unit='D')).dt.month
    sums = past.groupby(['route','month'])[['y','p']].transform('sum')
    base = past.p*sums.y/sums.p.clip(lower=1)
    past['residual'] = np.clip((past.y-base)/(base+30),-.9,1.)
    past.loc[(past.p<=1)|(past.route==5)|(past.route.isin([7,50])&(past.kind!=0)), 'residual'] = np.nan
    cols = pd.MultiIndex.from_product([routes,range(24)],names=['route','hour'])
    x = past.pivot(index='day',columns=['route','hour'],values='residual').reindex(columns=cols)
    # Rank transform reduces the influence of rare closures and outliers.
    z = x.rank(pct=True).subtract(.5).fillna(0).to_numpy()
    z -= z.mean(axis=0)
    norm = np.sqrt((z*z).sum(axis=0)); z /= np.maximum(norm,1e-8)
    corr = np.einsum('di,dj->ij',z,z)
    np.fill_diagonal(corr,1.)
    return corr, dict(last_training_day=int(past.day.max()),training_days=int(past.day.nunique()),source='past v11 residual ranks, route-month normalized')


def scenario_posterior(anchor,pool,scores,A,b,total,support,prior,corr,strength=.5,samples=512,seed=42):
    ncell = len(corr); ndays = len(anchor)//ncell
    assert len(anchor)==ndays*ncell
    eig, vec = np.linalg.eigh(corr)
    eig = np.maximum(eig,0)
    transform = vec*np.sqrt(eig)[None,:]
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((ndays,samples,ncell))
    correlated = np.einsum('dsi,ji->dsj',z,transform,optimize=False)
    latent = np.sqrt(strength)*correlated+np.sqrt(1-strength)*rng.standard_normal(z.shape)
    u = ndtr(latent)
    mid = prior.cumsum()-prior/2
    grid = support.reshape(ndays,ncell,-1)
    scenarios = np.empty_like(u)
    for d in range(ndays):
        for c in range(ncell):
            scenarios[d,:,c] = np.interp(u[d,:,c],mid,grid[d,c])
    weights = anchor.reshape(ndays,ncell).sum(1)+30*ncell
    weights /= weights.sum()
    p = pool.reshape(len(pool),ndays,ncell)
    reference = np.argmin(abs(pool-anchor).sum(1))
    losses = np.array([abs(scenarios-row[:,None,:]).sum(2) for row in p])
    keep = [i for i in range(len(pool)) if i!=reference]
    costs = np.r_[losses[keep]-losses[reference],losses[reference][None]]
    targets = np.r_[scores[reference]-scores[keep],1-scores[reference],b/total]
    groups = np.einsum('gdc,dsc->gds',A.reshape(len(A),ndays,ncell),scenarios,optimize=False)
    features = np.concatenate([costs,groups])/(total*weights[None,:,None])
    scale = np.maximum(np.sqrt(np.einsum('jd,d->j',features.var(axis=2),weights)),1e-5)
    features /= scale[:,None,None]; targets /= scale
    def objective(theta, full=False):
        logits = -np.einsum('j,jds->ds',theta,features)
        logz = logsumexp(logits,axis=1)
        prob = np.exp(logits-logz[:,None])
        if full:return prob
        expected = np.einsum('jds,ds,d->j',features,prob,weights)
        return np.dot(weights,logz-np.log(samples))+np.dot(theta,targets)+.5e-6*np.dot(theta,theta), targets-expected+1e-6*theta
    fit = minimize(objective,np.zeros(len(targets)),jac=True,method='L-BFGS-B',options=dict(maxiter=900,ftol=1e-12,gtol=1e-7,maxcor=30))
    prob = objective(fit.x,True)
    mean = np.einsum('dsc,ds->dc',scenarios,prob).reshape(-1)
    fitted = 1-np.einsum('jds,ds->j',losses,prob)/total
    ess = 1/(prob*prob).sum(1)
    meta = dict(converged=bool(fit.success),score_rmse=float(np.sqrt(np.mean((fitted-scores)**2))),max_score_error=float(abs(fitted-scores).max()),min_ess=float(ess.min()),median_ess=float(np.median(ess)),samples=samples,strength=strength,seed=seed)
    return mean,meta


def main():
    TABLE.mkdir(parents=True,exist_ok=True);SAVE.mkdir(parents=True,exist_ok=True)
    arrays = fold_arrays(); history = residual_history(arrays); cov = covariates(); rows=[]
    for key in ['R06','R08','B']:
        a,target,cons = validation_inputs(key,arrays)
        y=a['y']; total=y.sum(); anchor=a['original'];champ=a['champion']
        cutoff=int(target.day.min())
        noise,_,_=learn(history,cov,cutoff,target)
        q=np.load(CACHE/f'{key}_quantiles.npy');q-=q[:,5,None]
        ref=np.argmin(abs(a['pool']-anchor).sum(1))
        support,prior=quantile_prior(anchor,(1-a['scores'][ref])*total,q,noise,.5)
        corr,info=correlation(history,cutoff,sorted(target.route.unique()))
        for strength in [0.,.35,.7]:
            mean,meta=scenario_posterior(anchor,a['pool'],a['scores'],a['A'],a['b'],total,support,prior,corr,strength=strength)
            np.save(SAVE/f'{key}_{strength}.npy',mean)
            for weight in [.25,.5]:
                pred=balanced_round(ipf((1-weight)*champ+weight*mean,a['A'],a['b']),cons)
                gain=(abs(champ-y).sum()-abs(pred-y).sum())/total
                rows.append(dict(fold=key,strength=strength,weight=weight,gain=gain,**{k:v for k,v in meta.items() if k!='strength'},**info))
            print(rows[-2:],flush=True)
            pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['strength','weight']).gain.agg(['mean','min']);summary.to_csv(TABLE/'selection.csv');print(summary,flush=True)

if __name__=='__main__':main()
