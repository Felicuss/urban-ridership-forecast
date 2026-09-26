"""Regularized VARX and robust STL + damped ETS with known network regimes.

Only daily latent levels are forecast recursively; future calendar/weather/
network regimes and public city totals reconstruct hourly forecasts. All fitted
coefficients and cleaning thresholds are restricted to each fold's history.
"""
from __future__ import annotations
import json
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.stattools import acf

from s67_joint_day_net import ROOT, PACK, ROUTES
from s72_graph_regime_moe import RegimeData

OUT=ROOT/'data/structural_statistical'


def forecast(data,cutoff,horizon):
    dates=np.arange(cutoff+1+horizon)
    histories=np.arange(cutoff+1)
    template=np.zeros((len(dates),9,24))
    for j in range(9):
        for kind in range(3):
            for regime in np.unique(data.regime[dates,j]):
                ix=histories[data.good[histories,j]&(data.kind[histories,j]==kind)&(data.regime[histories,j]==regime)]
                recent=ix[ix>cutoff-112]
                if len(recent)>=3:ix=recent
                if len(ix)<3:ix=histories[data.good[histories,j]&(data.kind[histories,j]==kind)&(histories>cutoff-112)]
                if not len(ix):ix=histories[data.good[histories,j]]
                if not len(ix):continue
                profile=np.median(data.y[ix,j],axis=0)
                mask=(data.kind[dates,j]==kind)&(data.regime[dates,j]==regime)
                ratio=np.clip(data.city[dates[mask]]/data.city[ix].mean(),.65,1.4)**.35
                template[mask,j]=profile*ratio[:,None]
    daily=template.sum(-1)
    z=np.log(np.maximum(data.total[:cutoff+1],50)/np.maximum(daily[:cutoff+1],50))
    # Invalid history is missing, not a closure to learn. Interpolation is only
    # inside the known prefix and never consults validation/future targets.
    z=np.where(data.good[:cutoff+1],z,np.nan)
    z=pd.DataFrame(z).interpolate(limit_direction='both').fillna(0).to_numpy()
    median=np.median(z,axis=0);mad=np.median(abs(z-median),axis=0)
    bound=np.maximum(4*mad,.12)
    z=np.clip(z,median-bound,median+bound)
    z-=median
    x=np.column_stack([data.temp[dates,0]/20,np.log1p(data.rain[dates,0])/3,
        data.holiday[dates,0],np.eye(3)[data.kind[dates,0]],
        np.sin(2*np.pi*(dates-80)/365),np.cos(2*np.pi*(dates-80)/365)])
    # Remove predictable weather/calendar effects before regularized vector AR.
    exog=Ridge(alpha=10.).fit(x[:cutoff+1],z)
    residual=z-exog.predict(x[:cutoff+1])
    rows=np.arange(7,len(residual));lo=max(7,len(residual)-168);rows=rows[rows>=lo]
    features=np.concatenate([residual[rows-1],residual[rows-7],np.mean([residual[rows-k] for k in range(1,8)],axis=0)],axis=1)
    var=Ridge(alpha=2.).fit(features,residual[rows])
    state=list(residual)
    for _ in range(horizon):
        feat=np.r_[state[-1],state[-7],np.mean(state[-7:],axis=0)]
        next_value=np.clip(var.predict(feat[None])[0],-.3,.3)
        state.append(next_value)
    var_forecast=np.stack(state[-horizon:])+exog.predict(x[cutoff+1:])+median
    ets=[];diagnostics=[]
    for j,route in enumerate(ROUTES):
        series=residual[:,j]
        stl=STL(series,period=7,seasonal=13,robust=True).fit()
        adjusted=series-stl.seasonal
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            fitted=ExponentialSmoothing(adjusted,trend='add',damped_trend=True,
                initialization_method='estimated').fit(optimized=True)
        values=np.asarray(fitted.forecast(horizon))+np.resize(stl.seasonal[-7:],horizon)
        ets.append(values)
        diagnostics.append(dict(route=route,residual_acf1=float(acf(series,nlags=7,fft=False)[1]),
             residual_acf7=float(acf(series,nlags=7,fft=False)[7]),daily_log_mad=float(mad[j])))
    ets_forecast=np.stack(ets,axis=1)+exog.predict(x[cutoff+1:])+median
    outputs={}
    for name,latent in [('varx',var_forecast),('stl_ets',ets_forecast)]:
        pred=template[cutoff+1:]*np.exp(np.clip(latent,-.4,.4))[...,None]
        assert np.isfinite(pred).all() and (pred>=0).all()
        outputs[name]=pred
    return outputs,diagnostics


def main():
    OUT.mkdir(parents=True,exist_ok=True);data=RegimeData();rows=[]
    folds=json.loads((PACK/'folds.json').read_text())+[dict(name='future',train_end='2025-10-31',horizon_days=61)]
    for fold in folds:
        cutoff=pd.Timestamp(fold['train_end']).dayofyear-1
        result,diag=forecast(data,cutoff,fold['horizon_days'])
        for name,pred in result.items():np.save(OUT/f'{name}_{fold["name"]}.npy',pred)
        rows.extend([dict(fold=fold['name'],**d) for d in diag])
        print('STATISTICAL',fold['name'],'complete',flush=True)
    pd.DataFrame(rows).to_csv(OUT/'residual_diagnostics.csv',index=False)


if __name__=='__main__':main()
