"""Audit public 2025 parking observations and run a matched residual ablation.

Target-period parking observations are permitted external covariates. Parking
is NOT tram ridership. No evaluation labels enter a fold's model, preprocessing,
sensor selection or PCA. No submission is produced by this research script.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from s67_joint_day_net import v7_references

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/research_094/parking'
OUT = ROOT/'docs/analysis/tables/research_094'
CACHE = ROOT/'data/research_094/parking_experiment'


def load():
    manifest = json.loads((SOURCE/'manifest.json').read_text())
    for entry in manifest['files']:
        assert hashlib.sha256((SOURCE/entry['file']).read_bytes()).hexdigest() == entry['sha256']
    if (CACHE/'hourly_observations.parquet').exists() and (OUT/'parking_coverage.csv').exists():
        return pd.read_parquet(CACHE/'hourly_observations.parquet'), pd.read_parquet(SOURCE/'parking_spots.parquet').set_index('id')
    parts = [pd.read_parquet(p) for p in sorted(SOURCE.glob('occupancy_2025-*.parquet'))]
    rows = pd.concat(parts, ignore_index=True)
    assert not rows.duplicated(['time','parking_id']).any()
    rows['ts'] = rows.time.dt.tz_convert('Europe/Moscow').dt.tz_localize(None).dt.floor('h')
    rows['month'] = rows.ts.to_numpy().astype('datetime64[M]').astype(str)
    rows['valid'] = rows.occupancy_rate.between(0,100)
    audit = rows.groupby('month').agg(rows=('valid','size'), valid_rows=('valid','sum'),
        lots=('parking_id','nunique'), distinct_hours=('ts','nunique'))
    audit.to_csv(OUT/'parking_coverage.csv')
    rows.loc[~rows.valid, 'occupancy_rate'] = np.nan
    index = pd.date_range('2025-01-01', '2025-12-31 23:00', freq='h')
    wide = rows.pivot_table(index='ts', columns='parking_id', values='occupancy_rate', aggfunc='median').reindex(index)/100
    wide.to_parquet(CACHE/'hourly_observations.parquet')
    spots = pd.read_parquet(SOURCE/'parking_spots.parquet').set_index('id')
    return wide, spots


def parking_features(wide, spots, train_dates, calendar, fold):
    observed = (wide.index >= train_dates.min()) & (wide.index < train_dates.max()+pd.Timedelta(days=1))
    sample = wide.loc[observed]
    # Static 2026 feed_silent/last_free_at flags are intentionally unused.
    good = (sample.notna().mean() >= .7) & (sample.std() >= .03) & ((sample > 0) & (sample < 1)).mean().gt(.05)
    cols = good[good].index
    assert len(cols) >= 12
    x = wide[cols]
    kinds = calendar.set_index('date').kind.reindex(x.index.normalize()).to_numpy()
    group = kinds*24+x.index.hour
    expected = x.loc[observed].groupby(group[observed]).median().reindex(group).set_axis(x.index)
    expected = expected.fillna(sample[cols].median()).fillna(.5)
    centered = (x-expected).fillna(0).to_numpy()
    pca = PCA(n_components=12, svd_solver='full')
    pca.fit(centered[observed])
    pc = np.einsum('ij,kj->ik', centered-pca.mean_, pca.components_)
    assert np.isfinite(pc).all()
    result = pd.DataFrame(pc, index=x.index, columns=[f'park_pc_{i}' for i in range(12)])
    result['park_coverage'] = x.notna().mean(axis=1)
    result['park_city_residual'] = (x-expected).median(axis=1)
    result['park_city_occupancy'] = x.median(axis=1)
    result['park_city_change_1h'] = x.diff().median(axis=1)
    result['park_city_change_3h'] = x.diff(3).median(axis=1)
    geo = json.loads((ROOT/'external/osm_tram_routes.geojson').read_text())
    selected = spots.loc[cols]
    nearest = []
    for route in [1,5,7,11,12,17,25,26,28,50]:
        pts = [f['geometry']['coordinates'] for f in geo['features']
               if str(f['properties'].get('route')) == str(route) and f['geometry']['type'] == 'Point']
        if not pts:
            weights = np.ones(len(cols))
        else:
            pts = np.asarray(pts)
            delta_lon = (selected.longitude.to_numpy()[:,None]-pts[:,0])*np.cos(np.deg2rad(55.75))*111.32
            delta_lat = (selected.latitude.to_numpy()[:,None]-pts[:,1])*111.32
            distance = np.sqrt(delta_lon**2+delta_lat**2).min(axis=1)
            weights = np.exp(-distance/2.)
            weights[np.argsort(distance)[8:]] = 0
            nearest.append(dict(fold=fold,route=route,selected_sensors=len(cols),
                nearest_distance_km=float(distance.min()),nearby_3km=int((distance<3).sum())))
        weights /= weights.sum()
        result[f'park_route_{route}_residual'] = np.einsum('ij,j->i',centered,weights)
        result[f'park_route_{route}_occupancy'] = np.einsum('ij,j->i',x.fillna(expected).to_numpy(),weights)
    pd.DataFrame(nearest).to_csv(CACHE/f'{fold}_sensors.csv', index=False)
    (CACHE/f'{fold}_preprocessing.json').write_text(json.dumps(dict(
        sensor_ids=[int(i) for i in cols], fit_start=str(train_dates.min()), fit_end=str(train_dates.max()),
        pca_variance=pca.explained_variance_ratio_.tolist()),indent=2)+'\n')
    return result


def frame_features(frame, covariates, parking):
    features = frame[['date','route','hour','p']].merge(covariates,
        on=['date','route','hour'], validate='one_to_one')
    timestamp = pd.DatetimeIndex(features.date+pd.to_timedelta(features.hour,unit='h'))
    park = parking.reindex(timestamp).reset_index(drop=True)
    result = features[['route','hour','p','kind','dow','holiday','network_regime',
        'temperature_2m','precipitation','cloud_cover','wind_speed_10m']].copy()
    result['route'] = result.route.astype('category')
    result['day_sum'] = features.groupby(['route','date']).p.transform('sum')
    result['day_share'] = features.p/(result.day_sum+1)
    for col in [c for c in park if not c.startswith('park_route_')]:
        result[col] = park[col].to_numpy()
    for name in ['residual','occupancy']:
        result[f'park_near_{name}'] = [park.loc[i,f'park_route_{r}_{name}'] for i,r in enumerate(features.route)]
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    wide,spots = load()
    cov = pd.concat([pd.read_parquet(ROOT/'data/neural_training_pack'/name)
                    for name in ['history.parquet','future_covariates.parquet']],ignore_index=True)
    cov = cov.drop(columns=['boardings'],errors='ignore')
    calendar = cov[['date','kind']].drop_duplicates()
    assert not calendar.date.duplicated().any()
    refs = v7_references();frames=[]
    for fold,(a,p) in refs.items():
        dates=pd.Timestamp('2025-01-01')+pd.to_timedelta(a['day'],unit='D')
        frames.append(pd.DataFrame(dict(date=dates,route=a['route'],hour=np.tile(np.arange(24),len(dates)//24),
            p=p.reshape(-1),y=a['y'],fold=fold,origin=dates.min()-pd.Timedelta(days=1))))
    historical=pd.concat(frames,ignore_index=True).sort_values('origin').drop_duplicates(['date','route','hour'],keep='last')
    records=[];component_records=[]
    for fold in ['R06','R07','R08','B']:
        test=next(f for f in frames if f.fold.iloc[0]==fold).reset_index(drop=True)
        train=historical[historical.date<test.date.min()].reset_index(drop=True)
        assert train.date.max() < test.date.min()
        parking=parking_features(wide,spots,train.date,calendar,fold)
        xtrain=frame_features(train,cov,parking);xtest=frame_features(test,cov,parking)
        active=(train.p>20)&~train.route.eq(5)&~(train.route.isin([7,50])&xtrain.kind.ne(0))
        target=(train.y-train.p)/(train.p+50)
        weight=(train.p+50)
        baseline_error=abs(test.y-test.p).sum();total=test.y.sum()
        for name,use_parking in [('without_parking',False),('with_parking',True)]:
            columns=[c for c in xtrain if use_parking or not c.startswith('park_')]
            model=lgb.LGBMRegressor(objective='regression_l1',n_estimators=250,learning_rate=.035,
                num_leaves=15,min_child_samples=200,colsample_bytree=1.,reg_lambda=10.,
                n_jobs=4,random_state=2026,verbosity=-1,deterministic=True,force_col_wise=True)
            model.fit(xtrain.loc[active,columns],target[active],sample_weight=weight[active])
            correction=np.clip(model.predict(xtest[columns]),-.3,.3)*(test.p+50)
            protected=(test.p<=20)|test.route.eq(5)|(test.route.isin([7,50])&xtest.kind.ne(0))
            correction[protected]=0
            model.booster_.save_model(str(CACHE/f'{fold}_{name}.txt'))
            np.save(CACHE/f'{fold}_{name}_delta.npy',correction)
            for w in [.25,.5,1.]:
                prediction=np.maximum(test.p+w*correction,0)
                gain=(baseline_error-abs(test.y-prediction).sum())/total
                records.append(dict(fold=fold,model=name,weight=w,reference_score=1-baseline_error/total,
                    score=1-abs(test.y-prediction).sum()/total,gain=gain,
                    training_rows=int(active.sum()),parking_features=sum(c.startswith('park_') for c in columns)))
                raw=prediction.to_numpy().reshape(-1,10,24)
                p=test.p.to_numpy().reshape(raw.shape);y=test.y.to_numpy().reshape(raw.shape)
                raw_total=raw.sum(-1,keepdims=True);p_total=p.sum(-1,keepdims=True)
                shape=raw*np.divide(p_total,raw_total,out=np.ones_like(p_total),where=raw_total>0)
                level=p*np.divide(raw_total,p_total,out=np.ones_like(p_total),where=p_total>0)
                for mode,values in [('shape',shape),('level',level)]:
                    component_records.append(dict(fold=fold,model=name,weight=w,mode=mode,
                        gain=(baseline_error-abs(y-values).sum())/total))
        print(fold,'done',flush=True)
    result=pd.DataFrame(records)
    result.to_csv(OUT/'parking_ablation.csv',index=False)
    pd.DataFrame(component_records).to_csv(OUT/'parking_components.csv',index=False)
    print(result.round(6).to_string(index=False))


if __name__=='__main__':main()
