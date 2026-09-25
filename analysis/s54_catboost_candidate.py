"""CatBoost MAE residual model with categorical route/hour/day interactions."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from s52_round4_common import *


def features(frame):
    x=frame.drop(columns=['base','target_day','origin','y']).copy()
    cats=['route','hour','dow','kind']
    for name,left,right,mult in [('route_hour','route','hour',24),('route_kind','route','kind',3),
                                  ('route_dow','route','dow',7),('hour_dow','hour','dow',7)]:
        x[name]=(frame[left]*mult+frame[right]).astype('int64');cats.append(name)
    for c in cats:x[c]=x[c].astype('int64')
    return x,cats


def fit(train,test,model_path):
    corrupt=train.target_day.between(89,95)&train.route.isin([1,7,11,12,17,25,26,28])
    t=train[(train.base>5)&(train.route!=5)&~corrupt]
    scale=t.base+20
    count=t.groupby(['target_day','route','hour']).y.transform('size')
    x,cats=features(t);xt,_=features(test)
    model=CatBoostRegressor(iterations=600,depth=6,learning_rate=.05,loss_function='MAE',
        l2_leaf_reg=20,random_seed=2026,thread_count=4,allow_writing_files=False,verbose=False,
        one_hot_max_size=64)
    model.fit(Pool(x,label=(t.y-t.base)/scale,weight=scale/count,cat_features=cats))
    p=np.maximum(0,test.base.to_numpy()+(test.base.to_numpy()+20)*model.predict(xt))
    p=np.where(test.base>5,p,test.base)
    if model_path:model.save_model(str(model_path))
    return p


def main():
    init();data=frame_data();arrays=fold_arrays();rows=[]
    for fold,date,h in FOLDS:
        o=pd.Timestamp(date).dayofyear-1;path=CACHE/f'catboost_{fold}.npy'
        if path.exists():p=np.load(path)
        else:
            print('CatBoost training',fold,flush=True)
            p=fit(data['train'][data['train'].target_day<=o],data[fold],None);np.save(path,p)
        a=arrays[fold]
        for w in (.2,.4):
            pred=match_protection((1-w)*a['v2']+w*p,a)
            rows.append(dict(candidate=f'catboost_{int(w*100)}',fold=fold,score=score(a['y'],pred),
                gain=score(a['y'],pred)-score(a['y'],a['v2'])))
        print(fold,rows[-2:],flush=True)
    report(rows,'catboost')
    path=CACHE/'catboost_future.npy'
    if path.exists():p=np.load(path)
    else:
        print('CatBoost training final',flush=True)
        p=fit(data['train'],data['future'],OUT/'catboost_residual.cbm');np.save(path,p)
    a=future_arrays()
    for w in (.2,.4):
        pred=match_protection((1-w)*a['v2']+w*p,a)
        export(f'catboost_{int(w*100)}',core=pred,metadata={'method':'CatBoost MAE with categorical interactions',
            'catboost_weight':w,'training_cutoff':'2025-10-31','protected':'route 5 and nonworkdays of 7/50'})


if __name__=='__main__':main()
