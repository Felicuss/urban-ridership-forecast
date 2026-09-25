"""Daily regression + ARIMA and SARIMAX; research arrays only, no submissions.

Known future calendar/weather are allowed by the competition. Target history is
strictly sliced at each origin. Evaluate hourly WAPE against the deployed daily
model analogue, with cold-start/event protections kept in every candidate.
"""
from __future__ import annotations
import argparse
import json
import warnings
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from s52_round4_common import ROOT, CACHE, TABLES, ROUTES, DATES, Experiment, FOLDS, fold_arrays, future_arrays
from s55_daily_level import regimes, rescale

ARIMA_CACHE = CACHE / 'arima'
CONFIGS = {
    'robust_ar1_168': dict(order=(1,0,0), seasonal=(0,0,0,0), window=168, joint=False),
    'robust_arma_weekly_168': dict(order=(1,0,1), seasonal=(1,0,0,7), window=168, joint=False),
    'robust_integrated_168': dict(order=(0,1,1), seasonal=(0,0,1,7), window=168, joint=False),
    'joint_ar1_168': dict(order=(1,0,0), seasonal=(0,0,0,0), window=168, joint=True),
    'robust_arma_weekly_84': dict(order=(1,0,1), seasonal=(1,0,0,7), window=84, joint=False),
}


def exogenous(exp):
    x = pd.DataFrame(index=np.arange(365))
    x['intercept'] = 1.
    for k in (1,2): x[f'kind_{k}'] = (exp.kind == k).astype(float)
    for d in (1,2,3,4): x[f'work_dow_{d}'] = ((exp.kind == 0) & (exp.dow == d)).astype(float)
    x['holiday'] = exp.holiday.astype(float)
    x['working_saturday'] = ((exp.dow == 5) & ~exp.off).astype(float)
    w = pd.read_csv(ROOT/'external/weather_moscow_2025_hourly.csv', parse_dates=['ts'])
    w['day'] = w.ts.dt.dayofyear-1
    daily = w.groupby('day').agg(temperature=('temperature_2m','mean'), rain=('precipitation','sum'))
    x['heat'] = np.maximum(daily.temperature-20,0)/10
    x['cold'] = np.maximum(5-daily.temperature,0)/10
    x['rain'] = np.log1p(daily.rain)/3
    return x


def optimal_mass(y, shape):
    total = shape.sum(axis=1)
    fraction = np.divide(shape,total[:,None],out=np.zeros_like(shape),where=total[:,None]>0)
    ratio = np.divide(y,fraction,out=np.zeros_like(fraction),where=fraction>0)
    order = np.argsort(ratio,axis=1)
    weights = np.take_along_axis(fraction,order,axis=1)
    pos = (np.cumsum(weights,axis=1)>=.5).argmax(axis=1)
    result = np.take_along_axis(ratio,order,axis=1)[np.arange(len(y)),pos]
    return np.where(total>0,result,y.sum(axis=1))


def prepare(exp, x, state, origin, horizon, route, target, window):
    j = int(np.where(ROUTES == route)[0][0])
    train_days = np.arange(max(0,origin-window+1),origin+1)
    days = np.arange(origin+1,origin+horizon+1)
    y = exp.y[train_days,j].copy()
    if target == 'optimal':
        profiles = exp.profiles(origin)[0]['median_windows']
        mass = optimal_mass(y,profiles[exp.kind[train_days],j])
    else: mass = y.sum(axis=1)
    # Historical monthly seasonal shape, never actual future city ridership.
    season = exp.season(origin,np.r_[train_days,days])
    z = np.log(np.maximum(mass,1)) - np.log(season[:len(train_days)])
    valid = (state[train_days,j] == 0) & (mass>100)
    if route in [1,7,11,12,17,25,26,28]: valid &= ~((train_days>=89)&(train_days<=95))
    xx = x.iloc[np.r_[train_days,days]].to_numpy().copy()
    # Do not extrapolate winter response beyond weather seen in the training block.
    for col in range(xx.shape[1]-3,xx.shape[1]):
        low,high = np.quantile(xx[:len(train_days)][valid,col],[.01,.99])
        xx[:,col] = np.clip(xx[:,col],low,high)
    keep = np.r_[True,np.std(xx[:len(train_days)][valid,1:],axis=0)>1e-8]
    xx = xx[:,keep]
    return z,xx[:len(train_days)],xx[len(train_days):],valid,season[len(train_days):],list(x.columns[keep])


def robust_regression(z,x,valid):
    penalty = np.eye(x.shape[1])*.75
    penalty[0,0] = 1e-7
    w = valid.astype(float)
    for _ in range(12):
        beta = np.linalg.solve(x.T@(w[:,None]*x)+penalty,x.T@(w*z))
        residual = z-x@beta
        scale = max(.035,1.4826*np.median(abs(residual[valid]-np.median(residual[valid]))))
        w = valid*np.minimum(1.,1.5*scale/np.maximum(abs(residual),1e-9))
    return beta,scale


def fit_forecast(z,x,xf,valid,season,config):
    beta,scale = robust_regression(z,x,valid)
    residual = z-x@beta
    cleaned = np.clip(residual,-4*scale,4*scale)
    cleaned[~valid] = np.nan
    endog = cleaned + x@beta if config['joint'] else cleaned
    model = SARIMAX(endog,exog=x if config['joint'] else None,
        order=config['order'],seasonal_order=config['seasonal'],trend='n',
        enforce_stationarity=True,enforce_invertibility=True)
    attempts=[]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        fit = model.fit(disp=False,maxiter=120,cov_type='none')
        attempts.append(bool(fit.mle_retvals.get('converged',False)))
        if not attempts[-1]:
            fit = model.fit(start_params=fit.params,method='powell',disp=False,maxiter=80,cov_type='none')
            attempts.append(bool(fit.mle_retvals.get('converged',False)))
        prediction = np.asarray(fit.forecast(len(xf),exog=xf if config['joint'] else None))
    if not config['joint']: prediction += xf@beta
    assert np.isfinite(prediction).all()
    level = np.exp(np.clip(prediction,0,15))*season
    meta = dict(converged=attempts[-1],attempts=attempts,aic=float(fit.aic),scale=float(scale),
                params=dict(zip(fit.param_names,map(float,fit.params))),regression=beta.tolist(),
                valid_days=int(valid.sum()),masked_days=int((~valid).sum()))
    return level,meta


def worker(job):
    key,origin,horizon,route,target,name=job
    path=ARIMA_CACHE/f'{key}_{route}_{target}_{name}.npz'
    if path.exists():
        data=np.load(path)
        return job,data['level'],json.loads(str(data['metadata']))
    exp=Experiment();config=CONFIGS[name]
    z,x,xf,valid,season,columns=prepare(exp,exogenous(exp),regimes(exp),origin,horizon,route,target,config['window'])
    level,meta=fit_forecast(z,x,xf,valid,season,config)
    meta.update(columns=columns,origin=origin,route=int(route),target=target,config=config)
    np.savez_compressed(path,level=level,metadata=json.dumps(meta))
    return job,level,meta


def current_core(key,a):
    return rescale(a,np.load(CACHE/f'daily_optimal_{key}.npy'),.25)


@lru_cache(maxsize=1)
def event_states():
    return regimes(Experiment())


def apply_level(a,current,level,weight):
    p=current.reshape(-1,24)
    daily=p.sum(axis=1)
    ratio=np.divide(level.reshape(-1),daily,out=np.ones_like(daily),where=daily>100)
    multiplier=1+weight*(np.clip(ratio,.7,1.3)-1)
    pred=(p*multiplier[:,None]).reshape(-1)
    protected=(a['route']==5)|(np.isin(a['route'],[7,50])&(a['kind']!=0))
    if 'day' in a:
        route_index=np.searchsorted(ROUTES,a['route'])
        protected |= event_states()[a['day'],route_index]!=0
    return np.where(protected,current,pred)


def run(keys):
    ARIMA_CACHE.mkdir(parents=True,exist_ok=True)
    definitions={k:(pd.Timestamp(d).dayofyear-1,h) for k,d,h in FOLDS}
    definitions['future']=(303,61)
    jobs=[(k,*definitions[k],int(r),target,name) for k in keys for r in ROUTES if r!=5
          for target in ['sum','optimal'] for name in CONFIGS]
    diagnostics=[]
    levels={(k,t,n):np.zeros((definitions[k][1],10)) for k in keys for t in ['sum','optimal'] for n in CONFIGS}
    with ProcessPoolExecutor(max_workers=3) as pool:
        pending=[pool.submit(worker,job) for job in jobs]
        for i,task in enumerate(as_completed(pending),1):
            job,level,meta=task.result();k,_,_,r,t,n=job
            levels[k,t,n][:,np.where(ROUTES==r)[0][0]]=level
            diagnostics.append(dict(fold=k,variant=n,**meta))
            if i%18==0:print('ARIMA fits',i,'/',len(jobs),'latest',k,r,t,n,flush=True)
    for (k,t,n),level in levels.items():np.save(ARIMA_CACHE/f'level_{k}_{t}_{n}.npy',level)
    (ARIMA_CACHE/'fit_diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
    print('Fits complete; unconverged:',sum(not d['converged'] for d in diagnostics),flush=True)
    evaluate(keys)


def evaluate(keys):
    arrays=fold_arrays();rows=[]
    for k in keys:
        if k=='future':continue
        a=arrays[k];current=current_core(k,a)
        for target in ['sum','optimal']:
            for name in CONFIGS:
                level=np.load(ARIMA_CACHE/f'level_{k}_{target}_{name}.npy')
                for weight in [.15,.3,.5,1.]:
                    p=apply_level(a,current,level,weight)
                    for r in [0]+[int(r) for r in ROUTES if r!=5]:
                        mask=np.ones(len(p),dtype=bool) if r==0 else a['route']==r
                        loss=float(abs(p[mask]-a['y'][mask]).sum());den=float(a['y'][mask].sum())
                        anchor_loss=float(abs(current[mask]-a['y'][mask]).sum())
                        rows.append(dict(fold=k,route=r,target=target,variant=name,weight=weight,
                            score=1-loss/den,gain=(anchor_loss-loss)/den,absolute_error=loss,
                            target_sum=den,anchor_error=anchor_loss))
    f=pd.DataFrame(rows)
    if len(f):
        f.to_csv(TABLES/'arima_backtest.csv',index=False)
        summary=f[f.route==0].pivot_table(index=['target','variant','weight'],columns='fold',values='gain')
        summary['mean']=summary.mean(axis=1)
        summary.to_csv(TABLES/'arima_summary.csv')
        print(summary.sort_values('mean',ascending=False).head(20).round(6).to_string(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--keys',nargs='+',default=[k for k,_,_ in FOLDS]+['future'])
    args=p.parse_args();run(args.keys)
