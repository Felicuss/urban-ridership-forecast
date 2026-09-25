"""Test permitted ex-post monthly city facts against the scored v2 core.

Actual target-month city aggregates are intentional future information, not
withheld route labels. Reused rolling folds are development diagnostics only.
This probe does not automatically export a submission.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from s42_adaptive_profiles import ROOT, TABLES, Experiment, DATES, YEARS, score


FOLDS=[('R04',119,61),('R05',150,61),('R06',180,61),('R07',211,61),('R08',242,61),('B',272,31)]


def combine(a,c):
    model=c['old']*a['old']+c['rich']*a['rich']+c['direct']*a['direct']
    return np.maximum(0,a['base']+np.where(a['horizon']<=30,c['near'],c['far'])*(model-a['base']))


def monthly_indices(exp,origin):
    # Historical day-type weights are estimated before each origin.
    ix=np.arange(max(0,origin-90),origin+1)
    valid=~exp.holiday[ix]
    daily=exp.y[ix].sum(axis=(1,2))
    work=np.median(daily[valid&(exp.kind[ix]==0)])
    weights=[1.]+[float(np.median(daily[valid&(exp.kind[ix]==k)])/work) for k in (1,2)]
    eq={}
    for year in YEARS+[2025]:
        cal=pd.read_csv(ROOT/f'external/production_calendar_{year}_isdayoff.csv',parse_dates=['date'])
        dow=cal.date.dt.dayofweek.to_numpy()
        off=cal.isdayoff_code.isin([1,8]).to_numpy()
        kind=np.where(~off,0,np.where(dow==5,1,2))
        holiday=off&(dow<5)
        w=np.array(weights)[kind]*np.where(holiday,.95,1.)
        w*=np.where((dow==5)&~off,.85,1.)
        eq[year]=pd.Series(w).groupby(cal.date.dt.month).sum()
    city=pd.read_csv(ROOT/'external/datamos_62521_monthly_ridership.csv')
    result={}
    for name,types in {'tram':['Трамвай'],'bus':['Автобус','Электробус'],
                      'metro':['Московский метрополитен'],'mcc':['Московское центральное кольцо']}.items():
        p=city[city.transport.isin(types)].groupby(['year','month']).passengers.sum().unstack()
        normalized=pd.DataFrame({y:p.loc[y]/eq[y] for y in YEARS+[2025]}).T
        om=DATES[origin].month
        actual=normalized.loc[2025]/normalized.loc[2025,om]
        historical=normalized.loc[YEARS].div(normalized.loc[YEARS,om],axis=0).median()
        result[name]=(actual/historical).to_numpy()
    return result,weights


def main():
    exp=Experiment()
    config=json.loads((ROOT/'forecasts/kaggle_round/unified_selection.json').read_text())['configuration']
    rows=[]
    for fold,origin,horizon in FOLDS:
        a=np.load(ROOT/f'data/kaggle_unified/{fold}.npz')
        pred=combine(a,config)
        days=np.arange(origin+1,origin+horizon+1)
        indices,_=monthly_indices(exp,origin)
        for source,ratios in indices.items():
            factor=np.repeat(ratios[exp.month[days]-1],240)
            for strength in (0.,.25,.5,.75,1.):
                p=pred*factor**strength
                rows.append(dict(fold=fold,source=source,strength=strength,
                                 score=score(a['y'],p),gain=score(a['y'],p)-score(a['y'],pred)))
    out=pd.DataFrame(rows)
    out.to_csv(TABLES/'future_city_probe.csv',index=False)
    summary=out.groupby(['source','strength']).agg(mean_score=('score','mean'),
        mean_gain=('gain','mean'),worst_gain=('gain','min'),wins=('gain',lambda x:int((x>0).sum())))
    print(summary.sort_values('mean_gain',ascending=False).round(6).to_string())
    print('\nLatest fold:')
    print(out[out.fold=='B'].round(6).to_string(index=False))
    indices,weights=monthly_indices(exp,303)
    print('\nFuture actual / historical expected city level (before network adjustment):')
    print({k:{'nov':round(v[10],5),'dec':round(v[11],5)} for k,v in indices.items()})
    print('Day weights',weights)
    # Historical analogue for the unvalidated network subtraction: new route 90
    # in September. Public first-month total is deliberately available ex-post.
    dayweight=np.array(weights)[exp.kind]*exp.calendar_factor
    first=(DATES>='2025-09-10')&(DATES<'2025-10-10')
    route90_level=400000/dayweight[first].sum()
    city=pd.read_csv(ROOT/'external/datamos_62521_monthly_ridership.csv')
    city=city[(city.transport=='Трамвай')&(city.year==2025)].set_index('month').passengers
    stress=[]
    for fold,origin,horizon in FOLDS[-2:]:
        a=np.load(ROOT/f'data/kaggle_unified/{fold}.npz')
        pred=combine(a,config)
        ix,w=monthly_indices(exp,origin)
        dw=np.array(w)[exp.kind]*exp.calendar_factor
        addition=np.where(DATES>='2025-09-10',dw*route90_level,0.)
        share={m:addition[exp.month==m].sum()/city[m] for m in (8,9,10)}
        days=np.arange(origin+1,origin+horizon+1)
        months=exp.month[days]
        raw=ix['tram'][months-1]
        adjusted=raw*np.array([(1-share[m])/(1-share[exp.month[origin]]) for m in months])
        stress.append(dict(fold=fold,baseline=score(a['y'],pred),
            gross_city=score(a['y'],pred*np.repeat(raw**.75,240)),
            subtract_new_route90=score(a['y'],pred*np.repeat(adjusted**.75,240))))
    pd.DataFrame(stress).to_csv(TABLES/'future_network_historical_stress.csv',index=False)
    print('\nNetwork-subtraction stress, NOT uniformly beneficial:')
    print(pd.DataFrame(stress).round(6).to_string(index=False))


if __name__=='__main__':
    main()
