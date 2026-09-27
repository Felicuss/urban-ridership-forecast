"""Conditional uncertainty boosted trees from strictly prior residual dates."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from s98_joint_scenarios import ROOT,OUT,ipf,balanced_round
from s95_heterogeneous_entropy import residual_history
from s52_round4_common import fold_arrays
from s93_entropy_scores import posterior
TABLE=ROOT/'docs/analysis/tables/distributional_noise_v21'
CACHE=ROOT/'data/distributional_noise'
FEATURES=['route','hour','dow','day','kind','log_level','temperature_2m','apparent_temperature','precipitation','snowfall','snow_depth','cloud_cover','wind_speed_10m','network_regime','holiday']


def covariates():
    frames=[pd.read_parquet(ROOT/f'data/neural_training_pack/{name}.parquet') for name in ['history','future_covariates']]
    df=pd.concat(frames,ignore_index=True);df['date']=pd.to_datetime(df.date);df['day']=(df.date-pd.Timestamp('2025-01-01')).dt.days
    return df.drop(columns=['kind','boardings'],errors='ignore')


def design(frame,cov):
    x=frame[['day','route','hour','kind','p']].merge(cov.drop(columns=['date']),on=['day','route','hour'],validate='one_to_one',sort=False)
    x['log_level']=np.log1p(x.p)
    return x[FEATURES].astype(float)


def learn(history,cov,cutoff,target):
    past=history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last').copy()
    past['month']=(pd.Timestamp('2025-01-01')+pd.to_timedelta(past.day,unit='D')).dt.month
    sums=past.groupby(['route','month'])[['y','p']].transform('sum')
    base=past.p*sums.y/sums.p.clip(lower=1)
    past['error']=np.clip(abs(past.y-base)/(base+30),.005,.8)
    past=past[(past.route!=5)&(past.p>1)&~(past.route.isin([7,50])&(past.kind!=0))].copy()
    weights=np.exp((past.day-cutoff)/90)
    model=lgb.LGBMRegressor(objective='regression',n_estimators=180,num_leaves=12,min_child_samples=180,learning_rate=.025,reg_lambda=20,verbosity=-1,n_jobs=2,random_state=42)
    model.fit(design(past,cov),past.error,sample_weight=weights)
    scale=np.clip(model.predict(design(target,cov)),.01,.8)
    typical=float(np.average(past.error,weights=weights))
    multiplier=np.clip(scale/typical,.5,2.)
    multiplier[target.route.to_numpy()==5]=1
    return multiplier,model,dict(training_days=int(past.day.nunique()),last_training_day=int(past.day.max()),relative_mean_error=typical)


def main():
    TABLE.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    arrays=fold_arrays();history=residual_history(arrays);cov=covariates();rows=[]
    for key in ['R06','R08','B']:
        a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum()
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(a['A'],a['b']))]
        markov=balanced_round(ipf(np.load(OUT/f'{key}_markov_0.8.npy'),a['A'],a['b']),cons)
        pool=np.r_[a['pool'],markov[None]];scores=np.r_[a['scores'],round(float(1-abs(markov-y).sum()/total),5)]
        champion=pool[scores.argmax()];score0=1-abs(champion-y).sum()/total
        f=arrays[key];target=pd.DataFrame(dict(day=f['day'],route=f['route'],hour=np.tile(np.arange(24),len(y)//24),kind=f['kind'],p=a['original']))
        mult,model,info=learn(history,cov,int(f['day'].min()),target)
        for strength in [.5,1.]:
            noise=a['mult']**(1-strength)*mult**strength
            pred,meta=posterior(a['original'],pool,scores,a['A'],a['b'],total,noise_multiplier=noise,distribution='mixture',maxiter=700)
            for weight in [.5,1.]:
                p=balanced_round(ipf((1-weight)*champion+weight*pred['mean'],a['A'],a['b']),cons)
                score=1-abs(p-y).sum()/total
                rows.append(dict(fold=key,strength=strength,weight=weight,score=score,gain=score-score0,fit_rmse=meta['score_rmse'],**info))
            np.save(CACHE/f'{key}_{strength}.npy',pred['mean']);print(rows[-2:],flush=True)
            pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['strength','weight']).gain.agg(['mean','min']);summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv');print(summary,flush=True)

if __name__=='__main__':main()
