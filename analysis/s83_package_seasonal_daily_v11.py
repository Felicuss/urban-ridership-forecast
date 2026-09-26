"""One next candidate: stronger seasonal shape + daily redistribution.

Monthly route/day-kind volumes remain exactly those of scored v10. The daily
regressor redistributes that volume across dates; it does not replace totals.
"""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from s72_graph_regime_moe import RegimeData
from s67_joint_day_net import ALL_ROUTES, blend_shape, norm, v7_references
from s52_round4_common import ROOT, FOLDS, future_arrays, DATES, Experiment
from s81_package_seasonal_v10 import prediction as seasonal_prediction
from s82_daily_seasonal_level import OUT, TABLE, change_level
from s66_next_iteration import current_core
from s64_package_shape_facts import shares, protected_cells, round_daily, verify_scored_files
from s62_hourly_shape import shape_adjust
from s63_external_level_probe import factors, apply_factor

MODELS = ['daily_fourier1','daily_fourier2']
SHAPE_WEIGHT = .5
LEVEL_WEIGHT = .3
ANCHOR = ROOT/'forecasts/submission_seasonal_v10.csv'
OUTPUT = ROOT/'forecasts/submission_seasonal_daily_v11.csv'


def levels(key):
    return np.exp(np.mean([np.log(np.load(OUT/f'{m}_{key}.npy')) for m in MODELS],axis=0))


def evaluate(data):
    refs=v7_references(); rows=[]; days=[]; routes=[]
    for key,date,h in FOLDS:
        a,v7=refs[key]; dates=np.unique(a['day']); truth=a['y'].reshape(v7.shape)
        raw=seasonal_prediction(key)
        v10=blend_shape(v7,raw,data.kind[dates],.35)
        for sw in [.35,.5,.65]:
            shaped=blend_shape(v7,raw,data.kind[dates],sw)
            for lw in [0,.15,.3,.5]:
                pred=change_level(shaped,levels(key),data,dates,lw,'within_month')
                error=abs(v10-truth)-abs(pred-truth)
                rows.append(dict(fold=key,shape_weight=sw,level_weight=lw,
                    baseline=1-abs(v10-truth).sum()/truth.sum(),
                    score=1-abs(pred-truth).sum()/truth.sum(),gain=error.sum()/truth.sum()))
                if sw!=SHAPE_WEIGHT or lw!=LEVEL_WEIGHT:continue
                np.save(OUT/f'v11_{key}.npy',pred)
                for d,e,t in zip(dates,error.sum((1,2)),truth.sum((1,2))):
                    days.append(dict(day=int(d),origin=pd.Timestamp(date).dayofyear-1,error_reduction=float(e),total=float(t)))
                for j,r in enumerate(ALL_ROUTES):
                    routes.append(dict(fold=key,route=r,error_reduction=float(error[:,j].sum()),total=float(truth[:,j].sum())))
    frame=pd.DataFrame(rows); frame.to_csv(TABLE/'ensemble_validation.csv',index=False)
    pd.DataFrame(routes).to_csv(TABLE/'ensemble_route_errors.csv',index=False)
    unique=pd.DataFrame(days).sort_values('origin').drop_duplicates('day',keep='last').sort_values('day')
    unique.to_csv(TABLE/'ensemble_unique_days.csv',index=False)
    weekly=unique.assign(week=unique.day//7).groupby('week')[['error_reduction','total']].sum().to_numpy()
    ix=np.random.default_rng(20260926).integers(0,len(weekly),(10000,len(weekly)))
    boot=weekly[ix].sum(1)
    diag=dict(unique_days=len(unique),gain=float(unique.error_reduction.sum()/unique.total.sum()),
        weekly_bootstrap_95_interval=np.quantile(boot[:,0]/boot[:,1],[.025,.975]).tolist(),
        caveat='Reused development periods and tuned model family; not a prospective LB interval.')
    selected=frame[(frame.shape_weight==SHAPE_WEIGHT)&(frame.level_weight==LEVEL_WEIGHT)]
    print(selected.round(7).to_string(index=False),flush=True)
    print('DEDUPLICATED',diag,flush=True)
    return selected,diag


def constrained_daily_round(old_daily, proposed_daily, groups, protected):
    """Preserve each group's integer volume and all protected day totals."""
    result=old_daily.astype('int64').copy()
    for group in np.unique(groups):
        mask=(groups==group)&~protected
        target=int(old_daily[mask].sum())
        if not mask.any() or target==0:continue
        mass=proposed_daily[mask].sum()
        assert mass>0
        raw=proposed_daily[mask]*target/mass
        rounded=np.floor(raw).astype('int64')
        n=target-int(rounded.sum())
        assert 0<=n<=len(raw)
        rounded[np.argsort(-(raw-rounded),kind='stable')[:n]]+=1
        result[mask]=rounded
        assert result[groups==group].sum()==old_daily[groups==group].sum()
    np.testing.assert_array_equal(result[protected],old_daily[protected])
    return result


def package(data,validation,diag):
    assert (validation.gain>0).all(),'Selected configuration must improve all development folds'
    count=verify_scored_files()
    assert hashlib.sha256(ANCHOR.read_bytes()).hexdigest()=='79f790c81e396b6ddb9cbf9b2261b2890ab2da31d510cdb4eb66857d71fe0ea1'
    a=future_arrays(); core=current_core('future',a)
    ff,_=factors(Experiment(),303,np.arange(304,365))
    v7=apply_factor(shape_adjust(core,shares('future'),a,.5),a,ff['tram'],.25).reshape(61,10,24)
    raw=seasonal_prediction('future'); dates=np.arange(304,365)
    v10=blend_shape(v7,raw,data.kind[dates],.35)
    shaped=blend_shape(v7,raw,data.kind[dates],SHAPE_WEIGHT)
    proposed=change_level(shaped,levels('future'),data,dates,LEVEL_WEIGHT,'within_month')
    shape_ratio=np.divide(shaped,v10,out=np.ones_like(shaped),where=v10>0).reshape(-1)
    level_ratio=np.divide(proposed.sum(-1),shaped.sum(-1),out=np.ones((61,10)),where=shaped.sum(-1)>0).reshape(-1)
    grid=pd.DataFrame(dict(date=DATES[a['day']],route=a['route'],hour=np.tile(np.arange(24),610)))
    anchor=pd.read_csv(ANCHOR,sep=';',parse_dates=['date'])
    old=grid.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    daily=old.reshape(-1,24).sum(-1)
    p=norm((old*shape_ratio).reshape(-1,24))*daily[:,None]
    protected=protected_cells(a).reshape(-1,24)[:,0]
    # Keep the explicit New Year's Eve daily rule as well as its zero fare hours.
    protected|=(grid.date.to_numpy()[::24]==np.datetime64('2025-12-31'))
    protected|=(daily==0)
    group=(grid.date.dt.month.to_numpy()[::24]*10000+a['route'][::24]*10+a['kind'][::24]).astype(int)
    target=constrained_daily_round(daily,daily*level_ratio,group,protected)
    result=round_daily(p.reshape(-1),target)
    result[protected_cells(a)]=old[protected_cells(a)]
    np.testing.assert_array_equal(result[old==0],0)
    np.testing.assert_array_equal(result.reshape(-1,24).sum(-1),target)
    for g in np.unique(group):
        assert target[group==g].sum()==daily[group==g].sum()
    final=anchor.drop(columns='prediction').merge(grid.assign(prediction=result),on=['route','date','hour'],validate='one_to_one')
    assert len(final)==14640 and final[['route','date','hour']].equals(anchor[['route','date','hour']])
    assert final.prediction.dtype.kind in 'iu' and (final.prediction>=0).all()
    assert (final.loc[(final.date==pd.Timestamp('2025-12-31'))&(final.hour>=20),'prediction']==0).all()
    final.date=final.date.dt.strftime('%Y-%m-%d')
    if OUTPUT.exists():raise FileExistsError('Do not overwrite existing candidate')
    final.to_csv(OUTPUT,sep=';',index=False)
    daily_frame=grid.iloc[::24][['date','route']].copy()
    daily_frame['before']=daily;daily_frame['after']=target
    daily_frame['change_pct']=100*(target/np.maximum(daily,1)-1)
    daily_frame.to_csv(TABLE/'future_daily_changes.csv',index=False)
    paths=[ROOT/'analysis/s82_daily_seasonal_level.py',ROOT/'analysis/s83_package_seasonal_daily_v11.py']
    paths+=[OUT/f'{m}_future.npy' for m in MODELS]
    metadata=dict(file=OUTPUT.name,status='unscored',leaderboard_score=None,
        sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        anchor=ANCHOR.name,anchor_sha256=hashlib.sha256(ANCHOR.read_bytes()).hexdigest(),anchor_score=.90731,
        shape_weight=SHAPE_WEIGHT,previous_shape_weight=.35,level_weight=LEVEL_WEIGHT,daily_models=MODELS,
        method='Increase seasonal hourly-profile weight to 50%; redistribute monthly route/day-kind mass across dates using a 30% smooth daily log-level ensemble.',
        preserved_groups='route x month x production-calendar day kind; protected route regimes and Dec31 daily totals',
        validation=validation.to_dict('records'),deduplicated_diagnostic=diag,
        changed_rows=int((result!=old).sum()),absolute_difference=int(abs(result-old).sum()),sum_difference=int((result-old).sum()),
        changed_route_days=int((target!=daily).sum()),daily_change_pct_quantiles=np.quantile(daily_frame.loc[daily>0,'change_pct'],[0,.1,.5,.9,1]).tolist(),
        scored_files_verified=count,
        provenance_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        caveats=['Local development gains are not an observed leaderboard gain.',
            'The monthly constraints preserve v10 predictions, not known exact target totals.',
            'Public future weather is used; no new hidden route labels were obtained.',
            'Dec31 daily protection and transfer onto deployed event rules apply only during future assembly.'])
    OUTPUT.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    assert verify_scored_files()==count
    print(json.dumps(metadata,ensure_ascii=False,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evaluate-only',action='store_true');args=parser.parse_args()
    data=RegimeData();validation,diag=evaluate(data)
    if not args.evaluate_only:package(data,validation,diag)


if __name__=='__main__':main()
