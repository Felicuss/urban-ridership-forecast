"""Package one unscored seasonal-profile candidate, preserving v7 daily totals."""
import hashlib
import json
import numpy as np
import pandas as pd
from s67_joint_day_net import Data, ROUTES, ALL_ROUTES, blend_shape, norm, v7_references
from s52_round4_common import ROOT, FOLDS, future_arrays, DATES, Experiment
from s66_next_iteration import current_core
from s64_package_shape_facts import shares, round_daily, protected_cells, verify_scored_files
from s62_hourly_shape import shape_adjust
from s63_external_level_probe import factors, apply_factor
from s80_seasonal_profiles import OUT, TABLE

MODELS = ['fourier1_weather','fourier2_r40']
WEIGHT = .35
ANCHOR = ROOT/'forecasts/submission_shape50_v7.csv'
OUTPUT = ROOT/'forecasts/submission_seasonal_v10.csv'


def prediction(key):
    return np.mean([np.load(OUT/f'{name}_{key}.npy') for name in MODELS],axis=0)


def main():
    count = verify_scored_files()
    data = Data()
    refs = v7_references()
    rows, daily, route_rows = [], [], []
    for key,date,h in FOLDS:
        a,ref = refs[key]
        dates = np.unique(a['day'])
        truth = a['y'].reshape(ref.shape)
        raw = prediction(key)
        for weight in [.25,WEIGHT,.5]:
            pred = blend_shape(ref,raw,data.kind[dates],weight)
            gain = (abs(ref-truth).sum()-abs(pred-truth).sum())/truth.sum()
            rows.append(dict(fold=key,weight=weight,
                baseline=1-abs(ref-truth).sum()/truth.sum(),
                score=1-abs(pred-truth).sum()/truth.sum(),gain=gain))
            if weight!=WEIGHT: continue
            for d,e,t in zip(dates,(abs(ref-truth)-abs(pred-truth)).sum((1,2)),truth.sum((1,2))):
                daily.append(dict(day=int(d),origin=pd.Timestamp(date).dayofyear-1,error_reduction=e,total=t))
            for i,r in enumerate(ALL_ROUTES):
                route_rows.append(dict(fold=key,route=r,
                    error_reduction=float((abs(ref-truth)-abs(pred-truth))[:,i].sum()),
                    total=float(truth[:,i].sum())))
    validation = pd.DataFrame(rows)
    validation.to_csv(TABLE/'ensemble_forward.csv',index=False)
    pd.DataFrame(route_rows).to_csv(TABLE/'ensemble_by_route.csv',index=False)
    # Deduplicate overlap using the latest forecasting origin before each date.
    unique = pd.DataFrame(daily).sort_values('origin').drop_duplicates('day',keep='last').sort_values('day')
    unique.to_csv(TABLE/'ensemble_unique_days.csv',index=False)
    blocks = unique.assign(week=unique.day//7).groupby('week')[['error_reduction','total']].sum().to_numpy()
    rng = np.random.default_rng(20260926)
    draws = rng.integers(0,len(blocks),(10000,len(blocks)))
    bootstrap = blocks[draws].sum(1)
    gains = bootstrap[:,0]/bootstrap[:,1]
    diagnostics = dict(unique_days=len(unique),weekly_blocks=len(blocks),
        gain=float(unique.error_reduction.sum()/unique.total.sum()),
        weekly_bootstrap_95_interval=np.quantile(gains,[.025,.975]).tolist(),
        caveat='Reused development dates and selected hyperparameters; not a prospective confidence interval for the leaderboard.')
    a = future_arrays()
    current = current_core('future',a)
    ff,_ = factors(Experiment(),303,np.arange(304,365))
    ref = apply_factor(shape_adjust(current,shares('future'),a,.5),a,ff['tram'],.25).reshape(61,10,24)
    proposed = blend_shape(ref,prediction('future'),data.kind[304:],WEIGHT)
    ratio = np.divide(proposed,ref,out=np.ones_like(ref),where=ref>0).reshape(-1)
    anchor = pd.read_csv(ANCHOR,sep=';',parse_dates=['date'])
    grid = pd.DataFrame(dict(date=DATES[a['day']],route=a['route'],hour=np.tile(np.arange(24),610)))
    old = grid.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    total = old.reshape(-1,24).sum(-1)
    shifted = norm((old*ratio).reshape(-1,24))*total[:,None]
    shifted = shifted.reshape(-1)
    shifted[protected_cells(a)] = old[protected_cells(a)]
    result = round_daily(shifted,total)
    np.testing.assert_array_equal(result[old==0],0)
    np.testing.assert_array_equal(result[protected_cells(a)],old[protected_cells(a)])
    np.testing.assert_array_equal(result.reshape(-1,24).sum(-1),total)
    final = anchor.drop(columns='prediction').merge(grid.assign(prediction=result),on=['route','date','hour'],validate='one_to_one')
    assert len(final)==14640 and final[['route','date','hour']].equals(anchor[['route','date','hour']])
    assert (final.prediction>=0).all() and final.prediction.dtype.kind in 'iu'
    assert (final.loc[(final.date==pd.Timestamp('2025-12-31'))&(final.hour>=20),'prediction']==0).all()
    final.date = final.date.dt.strftime('%Y-%m-%d')
    if OUTPUT.exists():
        raise FileExistsError('Candidate is immutable; inspect before replacing')
    final.to_csv(OUTPUT,sep=';',index=False)
    changes = grid.assign(before=old,after=result)
    changes['month'] = changes.date.dt.month
    changes.groupby(['route','month','hour'])[['before','after']].sum().to_csv(TABLE/'future_hourly_changes.csv')
    provenance = [ROOT/'analysis/s80_seasonal_profiles.py',ROOT/'analysis/s81_package_seasonal_v10.py',ROOT/'data/neural_training_pack/history.parquet',ROOT/'data/neural_training_pack/future_covariates.parquet']
    provenance += [OUT/f'{m}_future.npy' for m in MODELS]
    metadata = dict(file=OUTPUT.name,status='unscored',leaderboard_score=None,
        sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        anchor=ANCHOR.name,anchor_score=.90570,anchor_sha256=hashlib.sha256(ANCHOR.read_bytes()).hexdigest(),
        models=MODELS,weight=WEIGHT,
        method='Robust regularized Fourier regression of hourly shares, recent residual calibration; equal one-harmonic weather and two-harmonic ensemble, ratio-transferred onto v7.',
        validation=validation[validation.weight==WEIGHT].to_dict('records'),
        deduplicated_diagnostic=diagnostics,
        changed_rows=int((result!=old).sum()),absolute_difference=int(abs(result-old).sum()),sum_difference=int((result-old).sum()),
        daily_totals_preserved=True,scored_artifacts_verified=count,
        external_information='Previously available actual future weather/calendar/network data. No new exact target counts.',
        provenance_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in provenance},
        caveats=['No leaderboard score is known for this candidate.',
                 'Overlapping historical folds were reused for development and hyperparameter selection.',
                 'The winter backcast uses later-month labels and known daily totals; it is supplemental shape diagnosis, not a forward forecast.',
                 'Historical gains are not a promise of 0.94 or any leaderboard improvement.'])
    OUTPUT.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    assert verify_scored_files()==count
    print(json.dumps(metadata,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
