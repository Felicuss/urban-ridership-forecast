"""Learn route/day scale using historical reliability, regimes and actual weather.

Two targets: daily sum and L1-optimal scale of the base hourly shape. The latter
uses only training-day labels, never evaluation targets. Evaluate final hourly
WAPE, because fitting daily totals alone need not improve hourly predictions.
"""
from __future__ import annotations
import lightgbm as lgb
import numpy as np
import pandas as pd
from s52_round4_common import *


def regimes(exp):
    state=np.zeros((365,10),dtype='int64')
    events=pd.read_csv(ROOT/'external/events_2025.csv')
    for row in events.itertuples():
        if row.type not in ['closure','detour','merge']:continue
        mask=(DATES>=row.start)&(DATES<=row.end)
        if row.days=='weekends':mask&=exp.off
        rr=ROUTES if row.routes=='all' else [int(r) for r in row.routes.split(';')]
        code={'closure':1,'detour':2,'merge':4}[row.type]
        for r in rr:
            if r in ROUTES:state[mask,np.where(ROUTES==r)[0][0]]|=code
    return state


def daily_frame(frame,exp,state):
    n=len(frame)//24;assert n*24==len(frame)
    base=frame.base.to_numpy().reshape(n,24);y=frame.y.to_numpy().reshape(n,24)
    total=base.sum(axis=1);weights=np.divide(base,total[:,None],out=np.full_like(base,1/24),where=total[:,None]>0)
    first=frame.iloc[::24].reset_index(drop=True)
    x=first[['route','dow','kind','holiday','horizon','season','origin','target_day']].copy()
    x['log_daily_base']=np.log1p(total)
    for c in frame:
        if c.startswith(('ratio_','iqr_','tail_width_','zero_rate_','count_')):
            x[c]=(frame[c].to_numpy().reshape(n,24)*weights).sum(axis=1)
        elif c.startswith(('off_','holiday_','days_')):
            x[c]=first[c]
        elif c.startswith('event_'):
            x[c]=frame[c].to_numpy().reshape(n,24).max(axis=1)
    for c in ['temperature_2m','wind_speed_10m','temperature_change_6h']:
        values=frame[c].to_numpy().reshape(n,24)
        x[c+'_mean']=values.mean(axis=1);x[c+'_min']=values.min(axis=1);x[c+'_max']=values.max(axis=1)
    for c in ['precipitation','snowfall']:
        values=frame[c].to_numpy().reshape(n,24)
        x[c+'_total']=values.sum(axis=1);x[c+'_hours']=(values>0).sum(axis=1)
    totals=exp.y.sum(axis=2)
    for origin,indices in x.groupby('origin').groups.items():
        for r in ROUTES:
            j=int(np.where(ROUTES==r)[0][0]);idx=x.index[x.index.isin(indices)&(x.route==r)]
            hist=np.arange(int(origin)+1)
            clean=~exp.holiday[hist]&~((hist>=89)&(hist<=95))
            for k in range(3):
                target=idx[x.loc[idx,'kind'].to_numpy()==k]
                if not len(target):continue
                for window in (14,42,112):
                    valid=hist[clean&(exp.kind[hist]==k)&(hist>origin-window)]
                    v=totals[valid,j]
                    denominator=total[target]+100
                    for stat,number in [('median',np.median(v) if len(v) else 0),('mean',np.mean(v) if len(v) else 0),
                                        ('std',np.std(v) if len(v) else 0)]:
                        x.loc[target,f'history_daily_{stat}_{window}']=number/denominator
                for mode in np.unique(state[x.loc[target,'target_day'].astype(int),j]):
                    target_mode=target[state[x.loc[target,'target_day'].astype(int),j]==mode]
                    valid=hist[clean&(exp.kind[hist]==k)&(state[hist,j]==mode)]
                    v=totals[valid,j]
                    median=float(np.median(v)) if len(v) else 0.
                    x.loc[target_mode,'same_regime_count']=len(v)
                    x.loc[target_mode,'same_regime_level']=median/(total[target_mode]+100)
            x.loc[idx,'regime']=state[x.loc[idx,'target_day'].astype(int),j]
    ratio=np.divide(y,base,out=np.zeros_like(base),where=base>0)
    order=np.argsort(ratio,axis=1);sorted_ratio=np.take_along_axis(ratio,order,axis=1)
    sorted_weight=np.take_along_axis(base,order,axis=1)
    position=(np.cumsum(sorted_weight,axis=1)>=total[:,None]/2).argmax(axis=1)
    x['optimal_scale']=sorted_ratio[np.arange(n),position]
    x['daily_sum']=y.sum(axis=1);x['daily_base']=total
    return x


def fit(train,test,target):
    t=train[(train.daily_base>100)&(train.route!=5)&~train.target_day.between(89,95)].copy()
    count=t.groupby(['target_day','route']).daily_sum.transform('size')
    if target=='sum':label=(t.daily_sum-t.daily_base)/(t.daily_base+100)
    else:label=t.optimal_scale-1
    feats=[c for c in t if c not in ['origin','target_day','optimal_scale','daily_sum','daily_base']]
    ds=lgb.Dataset(t[feats],label=label,weight=(t.daily_base+100)/count,categorical_feature=['route','kind','regime'])
    model=lgb.train(dict(objective='regression_l1',num_leaves=11,min_data_in_leaf=70,learning_rate=.04,
        lambda_l2=20,verbosity=-1,num_threads=2,seed=2026,deterministic=True,force_col_wise=True),ds,num_boost_round=350)
    raw=model.predict(test[feats],num_threads=2)
    level=np.maximum(0,test.daily_base+raw*(test.daily_base+100 if target=='sum' else test.daily_base))
    return level.to_numpy(),model


def rescale(a,level,weight):
    p=a['v2'].reshape(-1,24);day=p.sum(axis=1)
    ratio=np.divide(level,day,out=np.ones_like(day),where=day>100)
    # Bounded daily correction, no city-wide future-level assumption.
    ratio=np.clip(ratio,.6,1.4)
    return match_protection((p*(1+weight*(ratio-1))[:,None]).reshape(-1),a)


def main():
    init();cache=CACHE/'daily_frames.pkl'
    if cache.exists():data=pd.read_pickle(cache)
    else:
        full=frame_data();exp=Experiment();state=regimes(exp);data={}
        for k,frame in full.items():
            print('Daily features',k,flush=True);data[k]=daily_frame(frame,exp,state)
        pd.to_pickle(data,cache)
    arrays=fold_arrays();rows=[]
    for target in ['sum','optimal']:
        for fold,date,h in FOLDS:
            o=pd.Timestamp(date).dayofyear-1
            level,_=fit(data['train'][data['train'].target_day<=o],data[fold],target)
            np.save(CACHE/f'daily_{target}_{fold}.npy',level)
            a=arrays[fold]
            for weight in [.25,.5]:
                p=rescale(a,level,weight)
                rows.append(dict(candidate=f'daily_{target}_{int(weight*100)}',fold=fold,
                    score=score(a['y'],p),gain=score(a['y'],p)-score(a['y'],a['v2'])))
            print(target,fold,rows[-2:],flush=True)
        level,model=fit(data['train'],data['future'],target)
        np.save(CACHE/f'daily_{target}_future.npy',level);model.save_model(str(OUT/f'daily_{target}.txt'))
        a=future_arrays()
        for weight in [.25,.5]:
            p=rescale(a,level,weight)
            export(f'daily_{target}_{int(weight*100)}',core=p,metadata={'method':'Learned daily route-level correction',
                'daily_target':target,'weight':weight,'raw_ratio_clip':[.6,1.4]})
    report(rows,'daily_level')


if __name__=='__main__':main()
