"""Estimate restored weekends of 7/50 from matched normal-service history."""
from __future__ import annotations
import numpy as np
from s52_round4_common import *
from s55_daily_level import regimes


def weighted_median_1d(v,w):
    order=np.argsort(v);i=np.searchsorted(np.cumsum(w[order]),w.sum()/2)
    return float(v[order[i]])


def normal_profiles(exp,state,origin):
    profiles={};details={};history=np.arange(origin+1)
    for route in [7,50]:
        j=int(np.where(ROUTES==route)[0][0]);daily=exp.y[:,j].sum(axis=1)
        clean=(state[history,j]==0)&~exp.holiday[history]&~((history>=89)&(history<=95))
        for kind in [1,2]:
            observations=[];dates=[]
            for day in history[clean&(exp.kind[history]==kind)]:
                nearby=history[clean&(exp.kind[history]==0)&(abs(history-day)<=6)]
                if len(nearby)<3:continue
                level=np.median(daily[nearby])
                if level<100:continue
                observations.append(exp.y[day,j]/level);dates.append(day)
            if len(dates)<4:continue
            values=np.array(observations);weights=2.**(-(origin-np.array(dates))/180)
            p=np.array([weighted_median_1d(values[:,h],weights) for h in range(24)])
            ratio=weighted_median_1d(values.sum(axis=1),weights)
            if p.sum()>0:p*=ratio/p.sum()
            profiles[(route,kind)]=p
            details[f'{route}_{kind}']=dict(observations=len(dates),weekend_to_workday=ratio)
    return profiles,details


def patch(exp,state,origin,days,pred,weight=.35):
    profiles,details=normal_profiles(exp,state,origin)
    p=pred.reshape(-1,10,24).copy();result=p.copy();changed=0
    for route in [7,50]:
        j=int(np.where(ROUTES==route)[0][0])
        for i,day in enumerate(days):
            kind=int(exp.kind[day])
            if kind==0 or exp.holiday[day] or state[day,j]!=0 or (route,kind) not in profiles:continue
            mask=(exp.kind[days]==0)&~exp.holiday[days]&(state[days,j]==0)&(abs(days-day)<=10)
            if mask.sum()<2:continue
            level=np.median(p[mask,j].sum(axis=1));proposal=level*profiles[(route,kind)]
            old=p[i,j].sum()
            if old>100 and proposal.sum()>0:
                proposal*=np.clip(proposal.sum()/old,.8,1.2)*old/proposal.sum()
            result[i,j]=(1-weight)*p[i,j]+weight*proposal;changed+=1
    return result.reshape(-1),details,changed


def main():
    init();exp=Experiment();state=regimes(exp);arrays=fold_arrays();rows=[]
    for fold,date,h in FOLDS:
        o=pd.Timestamp(date).dayofyear-1;days=np.arange(o+1,o+h+1);a=arrays[fold]
        p,_,n=patch(exp,state,o,days,a['v2'])
        np.save(CACHE/f'regime_{fold}.npy',p)
        rows.append(dict(candidate='restored_weekends',fold=fold,route_days_changed=n,
            score=score(a['y'],p),gain=score(a['y'],p)-score(a['y'],a['v2'])))
    report(rows,'regime_weekends')
    ctx=assembly_context();g,_,_,_,anchor=ctx
    p,details,n=patch(exp,state,303,np.arange(304,365),anchor)
    # Only the documented restoration date onward, preserving every other cell.
    mask=g.route.isin([7,50])&(g.kind!='workday')&~g.is_holiday&(g.date>='2025-11-15')
    p=np.where(mask,p,anchor)
    export('restored_weekends',grid_prediction=p,metadata={'method':'Matched normal-service weekend/hour ratios; 35% blend; daily level movement capped before blending',
        'historical_profiles':details,'changed_route_days':n,
        'caveat_regime':'Historical test covers normal-service weekends, not an identical November restoration.'})


if __name__=='__main__':main()
