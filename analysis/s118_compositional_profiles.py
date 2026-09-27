"""Joint 24-hour compositional boosting with grouped softmax objectives.
Unlike independent hourly regression, the objective differentiates through
normalization. Training profiles use only history before each forecast origin.
"""
import json
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.special import softmax
from s67_joint_day_net import Data, ROUTES, ALL_ROUTES
from s106_distributional_noise import covariates, FEATURES
from s112_daily_copula import validation_inputs
from s52_round4_common import ROOT, fold_arrays
from s93_entropy_scores import posterior
from s108_quantile_distribution import CACHE, residual_history, learn, quantile_prior, ipf, balanced_round
OUT=ROOT/'data/compositional_profiles'
TABLE=ROOT/'docs/analysis/tables/compositional_profiles_v25'


def causal_prior(data, day, cutoff):
    days=np.arange(max(0,cutoff-120),cutoff)
    weights=np.exp((days-cutoff)/35)[:,None]*data.good[days]
    same=data.kind[days]==data.kind[day]
    w=weights*same*(1+.5*(data.dow[days]==data.dow[day]))
    absent=w.sum(0)<1e-8;w[:,absent]=weights[:,absent]
    result=np.einsum('dr,drh->rh',w,data.shape[days])+1e-8
    return result/result.sum(1,keepdims=True)


def features(data,cov,days,prior):
    target=pd.DataFrame(dict(day=np.repeat(days,9*24),route=np.tile(np.repeat(ROUTES,24),len(days)),hour=np.tile(np.arange(24),len(days)*9)))
    x=target.merge(cov,on=['day','route','hour'],how='left',validate='many_to_one',sort=False)
    cols=[c for c in FEATURES if c not in ['day','kind','log_level']]
    result=x[cols].astype(float)
    result['kind']=data.kind[np.repeat(days,9),np.tile(np.arange(9),len(days))].repeat(24)
    result['annual_sin']=np.sin(2*np.pi*(target.day-80)/365)
    result['annual_cos']=np.cos(2*np.pi*(target.day-80)/365)
    result['prior_share']=prior.reshape(-1)
    for lag in [-1,1]:result[f'prior_neighbor_{lag}']=np.roll(prior,lag,axis=-1).reshape(-1)
    return result


def objective_arrays(raw,labels,weights,mode):
    p=softmax(np.asarray(raw).reshape(-1,24),axis=1)
    truth=np.asarray(labels).reshape(-1,24);w=np.asarray(weights).reshape(-1,24)
    if mode=='cross_entropy':
        grad=p-truth;hess=2*p*(1-p)
    elif mode=='smooth_l1':
        delta=p-truth;eps=.003;den=np.sqrt(delta*delta+eps*eps)
        derivative=delta/den
        grad=p*(derivative-(p*derivative).sum(1,keepdims=True))
        # Positive diagonal curvature approximation for the coupled objective.
        hess=p*p*eps*eps/(den**3)+.05*p*(1-p)
    else:raise ValueError(mode)
    return (grad*w).reshape(-1),np.maximum(hess*w,1e-7).reshape(-1)


def fit(data,cov,cutoff,target_days,mode,start_day=60):
    days=[];priors=[]
    for horizon in [1,14,42,61]:
        for day in range(start_day,cutoff):
            origin=day-horizon+1
            if origin<20:continue
            days.append(day);priors.append(causal_prior(data,day,origin))
    days=np.array(days);priors=np.array(priors)
    x=features(data,cov,days,priors)
    valid=data.good[days].reshape(-1)
    target=data.shape[days].reshape(-1,24)
    base=priors.reshape(-1,24)
    weight=(data.total[days]/10000*np.exp((days[:,None]-cutoff)/180)).reshape(-1)
    valid_rows=np.repeat(valid,24)
    train=lgb.Dataset(x.loc[valid_rows],label=target[valid].reshape(-1),weight=np.repeat(weight[valid],24),init_score=np.log(np.maximum(base[valid],1e-8)).reshape(-1))
    def objective(raw,ds):return objective_arrays(raw,ds.get_label(),ds.get_weight(),mode)
    model=lgb.train(dict(objective=objective,num_leaves=12,min_data_in_leaf=200,learning_rate=.025,lambda_l2=20,verbosity=-1,num_threads=2,seed=42,deterministic=True,force_col_wise=True),train,num_boost_round=250)
    base_test=np.array([causal_prior(data,day,cutoff) for day in target_days])
    prediction=model.predict(features(data,cov,np.array(target_days),base_test),raw_score=True,num_threads=2).reshape(-1,24)
    shares=softmax(np.log(np.maximum(base_test.reshape(-1,24),1e-8))+prediction,axis=1).reshape(len(target_days),9,24)
    return shares,base_test,model


def apply_shape(current,share,target,weight):
    p=np.asarray(current,dtype=float).reshape(-1,10,24);s=p.copy()
    for j,route in enumerate(ROUTES):
        index=ALL_ROUTES.index(route)
        q=share[:,j].copy();q[p[:,index]==0]=0
        q/=np.maximum(q.sum(1,keepdims=True),1e-12)
        s[:,index]=q*p[:,index].sum(1,keepdims=True)
    protected=((target.route.isin([7,50]))&(target.kind!=0)).to_numpy().reshape(-1,10,24)
    s[protected]=p[protected]
    return ((1-weight)*p+weight*s).reshape(-1)


def replay_current(a,target,history,cov,key,cons):
    anchor=a['original'];pool=a['pool'];scores=a['scores'];champ=a['champion'];y=a['y'];total=y.sum();A=a['A'];b=a['b']
    noise,_,_=learn(history,cov,int(target.day.min()),target)
    q=np.load(CACHE/f'{key}_quantiles.npy');ref=np.argmin(abs(pool-anchor).sum(1));error=(1-scores[ref])*total
    priors={m:quantile_prior(anchor,error,q-q[:,5,None] if m=='centered' else q,noise,.5 if m=='centered' else .25) for m in ['centered','quantile_risk']}
    extra=[]
    for mode in ['centered','quantile_risk']:
        p,_=posterior(anchor,pool,scores,A,b,total,custom_prior=priors[mode],maxiter=1200)
        w=.5 if mode=='centered' else 1.
        extra.append(balanced_round(ipf((1-w)*champ+w*p['mean'],A,b),cons))
    pool=np.r_[pool,np.array(extra)];scores=np.r_[scores,[round(float(1-abs(p-y).sum()/total),5) for p in extra]]
    p,_=posterior(anchor,pool,scores,A,b,total,custom_prior=priors['quantile_risk'],maxiter=1200)
    extra=balanced_round(ipf(p['mean'],A,b),cons)
    pool=np.r_[pool,extra[None]];scores=np.r_[scores,round(float(1-abs(extra-y).sum()/total),5)]
    return pool[scores.argmax()]


def main():
    OUT.mkdir(parents=True,exist_ok=True);TABLE.mkdir(parents=True,exist_ok=True)
    data=Data();cov=covariates();arrays=fold_arrays();history=residual_history(arrays);rows=[]
    for key in ['R06','R08','B']:
        a,target,cons=validation_inputs(key,arrays);days=np.unique(target.day);cutoff=int(days.min());y=a['y']
        current=replay_current(a,target,history,cov,key,cons);np.save(OUT/f'{key}_incumbent.npy',current)
        for mode in ['cross_entropy','smooth_l1']:
            shares,base,model=fit(data,cov,cutoff,days,mode)
            np.save(OUT/f'{key}_{mode}.npy',shares)
            for variant,s in [(mode,shares),('causal_prior',base)] if mode=='cross_entropy' else [(mode,shares)]:
                for weight in [.1,.25,.5,1.]:
                    pred=balanced_round(ipf(apply_shape(current,s,target,weight),a['A'],a['b']),cons)
                    gain=(abs(current-y).sum()-abs(pred-y).sum())/y.sum()
                    rows.append(dict(fold=key,mode=variant,weight=weight,gain=gain,score=float(1-abs(pred-y).sum()/y.sum())))
            print(key,mode,rows[-4:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['mode','weight']).gain.agg(['mean','min']);summary.to_csv(TABLE/'selection.csv');print(summary.to_string(),flush=True)

if __name__=='__main__':main()
