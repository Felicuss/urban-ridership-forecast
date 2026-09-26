"""Robust smooth seasonal hourly profiles; causal forward evaluation against v7.

Fits daily shares, never validation totals. All folds are reused development
data. Weather is observed ex-post, as permitted by the competition.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from s67_joint_day_net import Data, ROUTES, norm, blend_shape, v7_references
from s52_round4_common import FOLDS, ROOT

OUT = ROOT/'data/seasonal_profiles'
TABLE = ROOT/'docs/analysis/tables/seasonal_profiles'


def design(data, ri, harmonics, weather):
    t = np.arange(365)*2*np.pi/365
    kind = np.eye(3)[data.kind[:,ri]]
    dow = np.eye(7)[data.dow[:,ri]][:,:6]
    seasonal = np.column_stack([f(k*t) for k in range(1,harmonics+1)
                               for f in [np.sin,np.cos]])
    cols = [kind, dow, seasonal]
    if weather:
        # Weather covariates are four 6-hour summaries after 14 calendar columns.
        temp = data.cov[:,ri,14:18].mean(-1)
        rain = data.cov[:,ri,18:22].mean(-1)
        cols += [temp[:,None], np.maximum(-temp,0)[:,None], rain[:,None]]
    cols += [seasonal*(data.kind[:,ri]!=0)[:,None]]
    return np.column_stack(cols)


def smooth(data, cutoff, dates, harmonics=1, penalty=10, weather=False, recency=180):
    out = np.zeros((len(dates),9,24))
    for ri in range(9):
        x = design(data,ri,harmonics,weather)
        ix = np.flatnonzero(data.good[:cutoff+1,ri])
        y = data.shape[ix,ri]*24
        xx = x[ix]
        importance = data.total[ix,ri]/np.median(data.total[ix,ri])
        importance *= np.exp((ix-cutoff)/recency)
        reg = np.ones(x.shape[1])*penalty
        reg[:3] = .001
        reg[3:9] = penalty*2
        weights = np.broadcast_to(importance,(24,len(ix))).copy()
        for _ in range(12):
            lhs = np.einsum('ni,hn,nj->hij',xx,weights,xx)
            lhs += np.diag(reg)[None]
            rhs = np.einsum('ni,hn,nh->hi',xx,weights,y)
            beta = np.linalg.solve(lhs,rhs[...,None])[...,0]
            residual = y-np.einsum('ni,hi->nh',xx,beta)
            weights = importance[None]/np.maximum(np.abs(residual.T),.04)
        pred = np.einsum('ni,hi->nh',x[dates],beta)
        # Recent residual intercept compensates changes of route regime.
        fitted = np.einsum('ni,hi->nh',xx,beta)
        for k in range(3):
            local = (ix>cutoff-42)&(data.kind[ix,ri]==k)
            if local.sum()>=3:
                bias = np.median((y-fitted)[local],axis=0)
                pred[data.kind[dates,ri]==k] += .5*bias
        out[:,ri] = norm(np.maximum(pred,.001))
    assert np.isfinite(out).all()
    return out


def analog(data, cutoff, dates, season_width=60, temperature=False):
    source = np.arange(cutoff+1)
    out = []
    for d in dates:
        distance = np.minimum(abs(source-d),365-abs(source-d))
        seasonal = np.exp(-.5*(distance/season_width)**2)[:,None]
        recent = np.exp((source-cutoff)/42)[:,None]
        w = (.7*seasonal+.3*recent)*data.good[source]
        w *= (data.kind[source]==data.kind[d])
        w *= 1+.3*(data.dow[source]==data.dow[d])
        if temperature:
            temp = data.cov[:,:,14:18].mean(-1)*20
            w *= np.exp(-.5*((temp[source]-temp[d])/8)**2)
        p = np.einsum('dr,drh->rh',w,data.shape[source])
        out.append(norm(p+1e-8))
    return np.asarray(out)


CONFIGS = {
    'fourier1_r10':dict(harmonics=1,penalty=10),
    'fourier1_r40':dict(harmonics=1,penalty=40),
    'fourier2_r40':dict(harmonics=2,penalty=40),
    'fourier1_weather':dict(harmonics=1,penalty=20,weather=True),
    'analog60':dict(season_width=60),
    'analog90':dict(season_width=90),
    'analog60_weather':dict(season_width=60,temperature=True),
}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    TABLE.mkdir(parents=True,exist_ok=True)
    data = Data()
    refs = v7_references()
    rows = []
    for key,date,h in FOLDS+[('future','2025-10-31',61)]:
        cutoff = pd.Timestamp(date).dayofyear-1
        dates = np.arange(cutoff+1,cutoff+h+1)
        for name,config in CONFIGS.items():
            path = OUT/f'{name}_{key}.npy'
            if path.exists():
                pred = np.load(path)
            else:
                fn = analog if name.startswith('analog') else smooth
                pred = fn(data,cutoff,dates,**config)
                np.save(path,pred)
            if key=='future': continue
            a,ref = refs[key]
            truth = a['y'].reshape(ref.shape)
            base_score = 1-abs(ref-truth).sum()/truth.sum()
            for weight in [.25,.5,1.]:
                p = blend_shape(ref,pred,data.kind[dates],weight)
                score = 1-abs(p-truth).sum()/truth.sum()
                rows.append(dict(fold=key,model=name,weight=weight,
                                 baseline=base_score,score=score,gain=score-base_score))
            print(key,name,round(rows[-2]['gain'],6),flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(TABLE/'forward.csv',index=False)
    summary = frame.groupby(['model','weight']).gain.agg(['mean','min',lambda x:(x>0).sum()])
    summary.to_csv(TABLE/'summary.csv')
    print(summary.sort_values('mean',ascending=False).round(6).to_string(),flush=True)
    (OUT/'config.json').write_text(json.dumps(CONFIGS,indent=2)+'\n')
    # Supplemental winter backcast: January/February labels are excluded from
    # training, but later months are used. This is NOT a forward validation fold.
    original_good = data.good.copy()
    data.good[:59] = False
    dates = np.arange(8,59)  # exclude New Year holiday regime from this diagnostic
    baseline = data.baseline(303,dates)
    valid = original_good[dates]
    mass = data.total[dates]
    truth = data.y[dates]
    rows = []
    for name, config in CONFIGS.items():
        fn = analog if name.startswith('analog') else smooth
        pred = fn(data,303,dates,**config)
        for weight in [.25,.5,1.]:
            p = ((1-weight)*baseline+weight*pred)*mass[...,None]
            ref = baseline*mass[...,None]
            err = abs(p-truth)[valid].sum()
            referr = abs(ref-truth)[valid].sum()
            rows.append(dict(model=name,weight=weight,
                gain=(referr-err)/truth[valid].sum(),
                score=1-err/truth[valid].sum(),
                baseline=1-referr/truth[valid].sum()))
    pd.DataFrame(rows).to_csv(TABLE/'winter_backcast_diagnostic.csv',index=False)
    print('WINTER BACKCAST: held-out Jan/Feb, trained Mar/Oct; known daily totals',flush=True)
    print(pd.DataFrame(rows).round(6).to_string(index=False),flush=True)


if __name__=='__main__': main()
