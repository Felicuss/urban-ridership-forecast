"""Audit permitted actual city/traffic information and small route calibration.

No submission files. Actual target-month external aggregates are intentional;
route target labels are only used inside historical evaluation/selection.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from s52_round4_common import ROOT,CACHE,TABLES,ROUTES,DATES,Experiment,fold_arrays,FOLDS,future_arrays
from s55_daily_level import rescale
from s49_future_city_probe import monthly_indices


def factors(exp,origin,days):
    indices,weights=monthly_indices(exp,origin)
    eq={}
    for year in [2022,2023,2024,2025]:
        cal=pd.read_csv(ROOT/f'external/production_calendar_{year}_isdayoff.csv',parse_dates=['date'])
        dow=cal.date.dt.dayofweek.to_numpy();off=cal.isdayoff_code.isin([1,8]).to_numpy()
        kind=np.where(~off,0,np.where(dow==5,1,2));holiday=off&(dow<5)
        w=np.array(weights)[kind]*np.where(holiday,.95,1.)*np.where((dow==5)&~off,.85,1.)
        eq[year]=pd.Series(w).groupby(cal.date.dt.month).sum()
    traffic=pd.read_csv(ROOT/'external/datamos_62525_monthly_congestion.csv')
    city=pd.read_csv(ROOT/'external/datamos_62521_monthly_ridership.csv')
    city=city[(city.transport=='Трамвай')&city.year.between(2022,2025)].copy()
    city['log_level']=[np.log(row.passengers/eq[row.year][row.month]) for row in city.itertuples()]
    merged=city.merge(traffic,on=['year','month']).sort_values(['year','month'])
    om=DATES[origin].month
    hist=merged[merged.year*100+merged.month<=202500+om]
    gamma={c:float(np.polyfit(hist[c].diff().iloc[1:],hist.log_level.diff().iloc[1:],1)[0])
           for c in ['congestion_score','congestion_pct']}
    now=traffic[traffic.year==2025].set_index('month')
    months=exp.month[days]
    log_traffic=sum(gamma[c]*(now.loc[months,c].to_numpy()-now.loc[om,c]) for c in gamma)/2
    relative=np.exp(log_traffic)/exp.season(origin,days)
    result={'traffic':relative,**{k:v[months-1] for k,v in indices.items()}}
    return result,gamma


def apply_factor(current,a,factor,strength):
    f=np.clip(np.repeat(factor,240)**strength,.97,1.03)
    protected=(a['route']==5)|(np.isin(a['route'],[7,50])&(a['kind']!=0))
    f[protected]=1
    return current*f


def main():
    exp=Experiment();arrays=fold_arrays();rows=[]
    for k,date,h in FOLDS:
        origin=pd.Timestamp(date).dayofyear-1;a=arrays[k]
        current=rescale(a,np.load(CACHE/f'daily_optimal_{k}.npy'),.25)
        ff,gamma=factors(exp,origin,np.arange(origin+1,origin+h+1))
        for source,factor in ff.items():
            for strength in [.1,.25,.5]:
                p=apply_factor(current,a,factor,strength)
                gain=(abs(current-a['y']).sum()-abs(p-a['y']).sum())/a['y'].sum()
                rows.append(dict(fold=k,source=source,strength=strength,gain=gain))
    f=pd.DataFrame(rows);f.to_csv(TABLES/'round6_external_level.csv',index=False)
    summary=f.pivot_table(index=['source','strength'],columns='fold',values='gain')
    summary['mean']=summary.mean(axis=1)
    print(summary.sort_values('mean',ascending=False).round(6).to_string(),flush=True)
    ff,gamma=factors(exp,303,np.arange(304,365))
    meta={'traffic_gamma':gamma,'unshrunk_factors':{k:{'nov':float(v[0]),'dec':float(v[30])} for k,v in ff.items()}}
    (TABLES/'round6_external_factors.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps(meta,indent=2),flush=True)
    # Evaluate isolated +/-1.5% route-level hypotheses locally, without pretending
    # they have been tested against unknown leaderboard labels.
    rows=[]
    for k,a in arrays.items():
        current=rescale(a,np.load(CACHE/f'daily_optimal_{k}.npy'),.25)
        for r in [11,12,17]:
            mask=a['route']==r
            for factor in [.985,1.015]:
                p=current.copy();p[mask]*=factor
                gain=(abs(current-a['y']).sum()-abs(p-a['y']).sum())/a['y'].sum()
                rows.append(dict(fold=k,route=r,factor=factor,gain=gain))
    frame=pd.DataFrame(rows);frame.to_csv(TABLES/'round6_route_calibration.csv',index=False)
    print(frame.pivot_table(index=['route','factor'],columns='fold',values='gain').round(6).to_string(),flush=True)


if __name__=='__main__':main()
