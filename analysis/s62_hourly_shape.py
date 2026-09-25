"""Compare daily-level strength and independently learned hourly shares.

Research arrays and diagnostic tables only; submission assembly is separate.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import lightgbm as lgb
from s52_round4_common import ROOT,CACHE,TABLES,ROUTES,DATES,FOLDS,Experiment,frame_data,fold_arrays,future_arrays
from s55_daily_level import rescale,regimes

SHAPE_CACHE=CACHE/'shape_round6'


def normalize(values):
    p=values.reshape(-1,24)
    total=p.sum(axis=1)
    return np.divide(p,total[:,None],out=np.zeros_like(p,dtype=float),where=total[:,None]>0)


def features(frame):
    cols=[c for c in frame if c not in ['base','origin','target_day','y']]
    x=frame[cols].copy()
    x['base_share']=normalize(frame.base.to_numpy()).reshape(-1)*24
    x['log_daily_base']=np.repeat(np.log1p(frame.base.to_numpy().reshape(-1,24).sum(axis=1)),24)
    # Known astronomical proxy, no fitted future passenger statistics.
    d=frame.target_day.to_numpy()
    x['annual_sin']=np.sin(2*np.pi*(d-80)/365)
    x['annual_cos']=np.cos(2*np.pi*(d-80)/365)
    for name in ['temperature_2m','precipitation']:
        vals=frame[name].to_numpy().reshape(-1,24)
        x[name+'_day_mean']=np.repeat(vals.mean(axis=1),24)
        x[name+'_hour_anomaly']=(vals-vals.mean(axis=1)[:,None]).reshape(-1)
    return x


def fit(train,test,mode):
    total=np.repeat(train.y.to_numpy().reshape(-1,24).sum(axis=1),24)
    actual=normalize(train.y.to_numpy()).reshape(-1)*24
    base=normalize(train.base.to_numpy()).reshape(-1)*24
    corrupt=train.target_day.between(89,95)&train.route.isin([1,7,11,12,17,25,26,28])
    valid=(total>100)&(train.route!=5)&~corrupt
    x=features(train);test_x=features(test)
    count=train.groupby(['target_day','route','hour']).y.transform('size').to_numpy()
    target=actual-base if mode=='residual' else actual
    ds=lgb.Dataset(x.loc[valid],label=target[valid],weight=total[valid]/count[valid]/10000,
        categorical_feature=['route','kind'])
    model=lgb.train(dict(objective='regression_l1',num_leaves=15,min_data_in_leaf=200,
        learning_rate=.035,lambda_l2=10,verbosity=-1,num_threads=3,seed=2026,
        deterministic=True,force_col_wise=True),ds,num_boost_round=400)
    raw=model.predict(test_x,num_threads=3)
    if mode=='residual':raw+=normalize(test.base.to_numpy()).reshape(-1)*24
    return normalize(np.maximum(0,raw)).reshape(-1),model


def shape_adjust(current,share,a,weight):
    p=current.reshape(-1,24);s=share.reshape(-1,24).copy()
    s[p==0]=0
    s=normalize(s)
    daily=p.sum(axis=1)
    blended=(1-weight)*p+weight*s*daily[:,None]
    empty=s.sum(axis=1)==0
    blended[empty]=p[empty]
    protected=(a['route']==5)|(np.isin(a['route'],[7,50])&(a['kind']!=0))
    output=np.where(protected,current,blended.reshape(-1))
    np.testing.assert_allclose(output.reshape(-1,24).sum(axis=1),daily,rtol=1e-12,atol=1e-7)
    return output


def main():
    SHAPE_CACHE.mkdir(exist_ok=True,parents=True)
    data=frame_data();arrays=fold_arrays();rows=[]
    for mode in ['residual','direct']:
        for key,date,h in FOLDS+[('future','2025-10-31',61)]:
            path=SHAPE_CACHE/f'{mode}_{key}.npy'
            if path.exists():share=np.load(path)
            else:
                origin=pd.Timestamp(date).dayofyear-1
                train=data['train'][data['train'].target_day<=origin]
                share,model=fit(train,data[key],mode)
                np.save(path,share)
                if key=='future':model.save_model(str(SHAPE_CACHE/f'{mode}.txt'))
            if key=='future':continue
            a=arrays[key];daily=np.load(CACHE/f'daily_optimal_{key}.npy')
            reference=rescale(a,daily,.25)
            for dw in [.25,.4]:
                current=rescale(a,daily,dw)
                for sw in [0.,.1,.2,.35]:
                    pred=shape_adjust(current,share,a,sw)
                    for route in [0]+[int(r) for r in ROUTES if r!=5]:
                        mask=np.ones(len(pred),bool) if route==0 else a['route']==route
                        total=a['y'][mask].sum()
                        score=1-abs(pred[mask]-a['y'][mask]).sum()/total
                        gain=(abs(reference[mask]-a['y'][mask]).sum()-abs(pred[mask]-a['y'][mask]).sum())/total
                        rows.append(dict(fold=key,route=route,mode=mode,daily_weight=dw,shape_weight=sw,score=score,gain=gain))
            print('SHAPE',mode,key,'done',flush=True)
            pd.DataFrame(rows).to_csv(TABLES/'round6_shape_backtest.csv',index=False)
    f=pd.DataFrame(rows);summary=f[f.route==0].pivot_table(index=['mode','daily_weight','shape_weight'],columns='fold',values='gain')
    summary['mean']=summary.mean(axis=1);summary.to_csv(TABLES/'round6_shape_summary.csv')
    print(summary.sort_values('mean',ascending=False).round(6).to_string(),flush=True)


if __name__=='__main__':main()
