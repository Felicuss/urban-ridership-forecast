"""Separate smooth daily level from hourly shape; evaluate against scored v10.

All passenger labels used in each fit end at its forecast origin. Actual weather
and city totals are allowed ex-post covariates. Development folds are reused.
"""
import json
import numpy as np
import pandas as pd
from s72_graph_regime_moe import RegimeData
from s67_joint_day_net import ALL_ROUTES, ROUTES, blend_shape, v7_references
from s52_round4_common import ROOT, FOLDS
from s81_package_seasonal_v10 import prediction as seasonal_prediction

OUT = ROOT/'data/daily_seasonal_v11'
TABLE = ROOT/'docs/analysis/tables/daily_seasonal_v11'
CONFIGS = {
    'daily_fourier1':dict(harmonics=1,penalty=20,city_prior=0),
    'daily_fourier2':dict(harmonics=2,penalty=40,city_prior=0),
    'daily_fourier_city':dict(harmonics=1,penalty=20,city_prior=.35),
    'daily_weather_city':dict(harmonics=0,penalty=20,city_prior=.35),
}


def daily_design(data,ri,harmonics):
    t = np.arange(365)*2*np.pi/365
    kind = np.eye(3)[data.kind[:,ri]]
    dow = np.eye(7)[data.dow[:,ri]][:,:6]
    temp = data.temp[:,ri]/20
    rain = np.log1p(data.rain[:,ri])/3
    regime = np.column_stack([(data.regime[:,ri]&bit)>0 for bit in [1,2,4]])
    cols = [kind,dow,data.holiday[:,ri,None],regime,
        temp[:,None],np.maximum(-temp-.5,0)[:,None],rain[:,None]]
    if harmonics:
        seasonal = np.column_stack([f(k*t) for k in range(1,harmonics+1) for f in [np.sin,np.cos]])
        cols += [seasonal,seasonal*(data.kind[:,ri]!=0)[:,None]]
    return np.column_stack(cols).astype(float)


def forecast(data,cutoff,dates,harmonics=1,penalty=20,city_prior=0):
    output = np.zeros((len(dates),9))
    for j in range(9):
        ix = np.flatnonzero(data.good[:cutoff+1,j])
        design = daily_design(data,j,harmonics)
        x = design[ix]
        offset = city_prior*np.log(data.city)
        y = np.log(np.maximum(data.total[ix,j],100))-offset[ix]
        importance = np.sqrt(data.total[ix,j]/np.median(data.total[ix,j]))*np.exp((ix-cutoff)/180)
        reg = np.ones(x.shape[1])*penalty
        reg[:3] = .001
        reg[10:13] = 2. # route closures/detours are structural, not ordinary weather
        weight = importance.copy()
        for _ in range(20):
            lhs = np.einsum('ni,n,nj->ij',x,weight,x)+np.diag(reg)
            rhs = np.einsum('ni,n,n->i',x,weight,y)
            beta = np.linalg.solve(lhs,rhs)
            residual = y-np.einsum('ni,i->n',x,beta)
            weight = importance/np.maximum(abs(residual),.025)
        pred = np.einsum('ni,i->n',design[dates],beta)+offset[dates]
        # Estimate level shifts from the most recent matching kind/regime only.
        for k in range(3):
            for regime in np.unique(data.regime[dates,j]):
                local = (ix>cutoff-42)&(data.kind[ix,j]==k)&(data.regime[ix,j]==regime)
                if local.sum()<3: local=(ix>cutoff-42)&(data.kind[ix,j]==k)
                if local.sum()<3: continue
                mask=(data.kind[dates,j]==k)&(data.regime[dates,j]==regime)
                pred[mask] += .75*np.median(residual[local])
        output[:,j] = np.exp(np.clip(pred,0,15))
    assert np.isfinite(output).all()
    return output


def change_level(reference,levels,data,dates,strength,mode):
    out = reference.copy()
    for ri,r in enumerate(ROUTES):
        j = ALL_ROUTES.index(r)
        totals = reference[:,j].sum(-1)
        ratio = np.divide(levels[:,ri],totals,out=np.ones(len(totals)),where=totals>100)
        log_ratio = np.log(np.clip(ratio,.6,1.4))
        if mode=='within_month':
            for month in np.unique(data.month[dates]):
                for kind in range(3):
                    mask=(data.month[dates]==month)&(data.kind[dates,ri]==kind)
                    if mask.any():
                        log_ratio[mask] -= np.average(log_ratio[mask],weights=totals[mask]+1)
        factor = np.exp(strength*log_ratio)
        if mode=='within_month':
            for month in np.unique(data.month[dates]):
                for kind in range(3):
                    mask=(data.month[dates]==month)&(data.kind[dates,ri]==kind)
                    mass=totals[mask].sum()
                    if mass>0: factor[mask]*=mass/(totals[mask]*factor[mask]).sum()
        if r in [7,50]: factor[data.kind[dates,ri]!=0]=1
        factor[totals<=100]=1
        out[:,j]*=factor[:,None]
    return out


def main():
    OUT.mkdir(parents=True,exist_ok=True); TABLE.mkdir(parents=True,exist_ok=True)
    data=RegimeData(); refs=v7_references(); rows=[]; shape_rows=[]
    for key,date,h in FOLDS+[('future','2025-10-31',61)]:
        cutoff=pd.Timestamp(date).dayofyear-1
        dates=np.arange(cutoff+1,cutoff+h+1)
        levels={}
        for name,config in CONFIGS.items():
            levels[name]=forecast(data,cutoff,dates,**config)
            np.save(OUT/f'{name}_{key}.npy',levels[name])
        if key=='future':continue
        a,v7=refs[key]; truth=a['y'].reshape(v7.shape)
        raw=seasonal_prediction(key)
        v10=blend_shape(v7,raw,data.kind[dates],.35)
        for sw in [.35,.5,.65,.8,1.]:
            ref=blend_shape(v7,raw,data.kind[dates],sw)
            gain=(abs(v10-truth).sum()-abs(ref-truth).sum())/truth.sum()
            shape_rows.append(dict(fold=key,shape_weight=sw,gain_vs_v10=gain,score=1-abs(ref-truth).sum()/truth.sum()))
            if sw not in [.35,.5]:continue
            for name,level in levels.items():
                for mode in ['absolute','within_month']:
                    for w in [.15,.3,.5]:
                        pred=change_level(ref,level,data,dates,w,mode)
                        rows.append(dict(fold=key,shape_weight=sw,model=name,mode=mode,weight=w,
                            gain_vs_v10=(abs(v10-truth).sum()-abs(pred-truth).sum())/truth.sum(),
                            level_gain=(abs(ref-truth).sum()-abs(pred-truth).sum())/truth.sum(),
                            score=1-abs(pred-truth).sum()/truth.sum()))
        print('DONE',key,flush=True)
    frame=pd.DataFrame(rows); frame.to_csv(TABLE/'forward.csv',index=False)
    shape=pd.DataFrame(shape_rows);shape.to_csv(TABLE/'shape_strength.csv',index=False)
    summary=frame.groupby(['shape_weight','model','mode','weight']).agg(mean_gain=('gain_vs_v10','mean'),worst_gain=('gain_vs_v10','min'),wins=('gain_vs_v10',lambda x:(x>0).sum()),mean_level_gain=('level_gain','mean'))
    summary.to_csv(TABLE/'summary.csv')
    print('SHAPE',shape.pivot(index='shape_weight',columns='fold',values='gain_vs_v10').round(6).to_string(),flush=True)
    print(summary.sort_values('mean_gain',ascending=False).head(30).round(6).to_string(),flush=True)
    (OUT/'config.json').write_text(json.dumps(CONFIGS,indent=2)+'\n')


if __name__=='__main__':main()
