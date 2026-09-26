"""Prepare one shape-only candidate, calendar probes and a neural-training pack.

No platform submissions and no training of a new neural architecture here.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import numpy as np
import pandas as pd

from s52_round4_common import ROOT, CACHE, ROUTES, DATES, FOLDS, Experiment, future_arrays, fold_arrays
from s55_daily_level import rescale, regimes
from s62_hourly_shape import shape_adjust, normalize
from s63_external_level_probe import factors, apply_factor
from s64_package_shape_facts import shares, protected_cells, round_daily, verify_scored_files

ANCHOR=ROOT/'forecasts/submission_shape_facts_v6.csv'
ANCHOR_SHA='ae13aca28a9c388f69981fd07d9a118c687fbecbcbfafd9df6faf2180d61ea5c'
PROBE_COMMIT='90516aa8e38db66447e71c3262d6d6e466aab46e'
OUT=ROOT/'forecasts/next_iteration'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def branch_file(path):
    return subprocess.check_output(['git','show',PROBE_COMMIT+':'+path],cwd=ROOT)


def current_core(key,a):
    return rescale(a,np.load(CACHE/f'daily_optimal_{key}.npy'),.25)


def validation_and_pack():
    """Historical outputs are evaluation references, not training inputs."""
    exp=Experiment();frames=[];rows=[]
    arrays=fold_arrays()
    for key,date,h in FOLDS:
        a=arrays[key];o=pd.Timestamp(date).dayofyear-1
        core=current_core(key,a);s=shares(key)
        ff,_=factors(exp,o,np.arange(o+1,o+h+1))
        ref=apply_factor(shape_adjust(core,s,a,.35),a,ff['tram'],.25)
        candidate=apply_factor(shape_adjust(core,s,a,.50),a,ff['tram'],.25)
        rows.append(dict(fold=key,origin=date,horizon=h,
            reference_score=1-abs(ref-a['y']).sum()/a['y'].sum(),
            candidate_score=1-abs(candidate-a['y']).sum()/a['y'].sum(),
            gain=(abs(ref-a['y']).sum()-abs(candidate-a['y']).sum())/a['y'].sum()))
        frames.append(pd.DataFrame(dict(fold=key,origin=date,date=DATES[a['day']],route=a['route'],
            hour=np.tile(np.arange(24),len(ref)//24),boardings=a['y'],v6_core=ref)))
    return pd.DataFrame(rows),pd.concat(frames,ignore_index=True)


def candidate(validation):
    assert digest(ANCHOR)==ANCHOR_SHA
    anchor=pd.read_csv(ANCHOR,sep=';',parse_dates=['date'])
    a=future_arrays();core=current_core('future',a);s=shares('future')
    grid=pd.DataFrame(dict(date=DATES[a['day']],route=a['route'],hour=np.tile(np.arange(24),len(core)//24)))
    p=grid.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    before=shape_adjust(core,s,a,.35)
    after=shape_adjust(core,s,a,.50)
    ratio=np.divide(after,before,out=np.ones_like(after),where=before>0)
    total=p.reshape(-1,24).sum(axis=1)
    moved=normalize(p*ratio)*total[:,None]
    moved=moved.reshape(-1);moved[protected_cells(a)]=p[protected_cells(a)]
    pred=round_daily(moved,total)
    np.testing.assert_array_equal(pred[p==0],0)
    np.testing.assert_array_equal(pred[protected_cells(a)],p[protected_cells(a)])
    frame=grid.assign(prediction=pred)
    final=anchor.drop(columns='prediction').merge(frame,on=['route','date','hour'],validate='one_to_one')
    assert len(final)==14640 and final[['route','date','hour']].equals(anchor[['route','date','hour']])
    np.testing.assert_array_equal(final.groupby(['route','date']).prediction.sum(),anchor.groupby(['route','date']).prediction.sum())
    final.date=final.date.dt.strftime('%Y-%m-%d')
    path=ROOT/'forecasts/submission_shape50_v7.csv'
    final.to_csv(path,sep=';',index=False)
    scored = next((row for row in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
                   if row['file'] == path.name and row['sha256'] == digest(path)), None)
    metadata = dict(file=path.name,sha256=digest(path),status='unscored',
        leaderboard_score=None,anchor=ANCHOR.name,anchor_sha256=ANCHOR_SHA,anchor_score=.90553,
        change='Hourly share weight .35 -> .50, transferred onto v6 and renormalized to its exact daily integer sums',
        changed_rows=int((pred!=p).sum()),absolute_difference=int(abs(pred-p).sum()),sum_difference=int((pred-p).sum()),
        validation=validation.to_dict('records'),
        caveats=['These historical periods were reused for development and selection.',
                 'No neural architecture was trained for this candidate.',
                 'All calendar, event and city-level daily totals remain those of scored v6.'])
    if scored is not None:
        metadata.update(status='scored', leaderboard_score=scored['leaderboard_score'],
                        leaderboard_delta_vs_anchor=round(scored['leaderboard_score']-.90553, 8),
                        evidence=scored['evidence'])
    save_json(path.with_suffix('.json'), metadata)
    print('CANDIDATE',path.name,digest(path),flush=True)


def probes():
    directory=OUT/'diagnostics';directory.mkdir(parents=True,exist_ok=True)
    ledger=json.loads(branch_file('forecasts/probes/level_probes.json'))
    known={x['id']:x for x in ledger}
    base=pd.read_csv(ANCHOR,sep=';')
    calendar=pd.read_csv(ROOT/'artifacts/forecast_components.csv',usecols=['route','date','hour','kind'])
    g=base.merge(calendar,on=['route','date','hour'],validate='one_to_one')
    assert g[['route','date','hour']].equals(base[['route','date','hour']])
    def group(e):
        route,kind,month=e['group']
        return ((g.route==route)&(g.date.str[5:7].astype(int)==month)&
                ((g.kind=='workday') if kind=='wd' else (g.kind!='workday'))).to_numpy()
    plan=[('d02_nov01',g.date=='2025-11-01',['p12']),
          ('d03_r7_50_weekends',g.route.isin([7,50])&(g.kind!='workday')&(g.date>='2025-11-15'),['p11','p12']),
          ('d04_nov03_04',g.date.isin(['2025-11-03','2025-11-04']),['p11','p12']),
          ('d05_dec31_day',(g.date=='2025-12-31')&(g.hour<20),['p11','p12'])]
    existing=directory/'d01_dec29_30.csv'
    existing.write_bytes(branch_file('forecasts/probes/p13_dec29_30.csv'))
    assert digest(existing)==known['p13']['sha256']
    records=[dict(known['p13'],file=existing.name,original_file=known['p13']['file'],already_prepared=True)]
    T=known['p10']['sum_h']/(.90553-known['p10']['score'])
    for name,mask,ids in plan:
        target=(mask&(g.route!=5)).to_numpy();used=np.zeros(len(g),bool)
        pred=np.zeros(len(g),dtype='int64')
        for cid in ids:
            e=known[cid];cm=group(e)
            assert e['score'] is not None and not (used&cm).any() and not (target&cm).any()
            assert int(g.loc[cm,'prediction'].sum())==e['base_sum']
            pred[cm]=np.ceil(e['ceiling'][0]*g.loc[cm,'prediction']+e['ceiling'][1]).astype('int64')
            assert int(pred[cm].sum())==e['sum_h']
            used|=cm
        pred[target]=np.ceil(1.8*g.loc[target,'prediction']+4).astype('int64')
        path=directory/(name+'.csv')
        base.assign(prediction=pred).to_csv(path,sep=';',index=False)
        expected=sum(known[c]['score'] for c in ids)+(2*g.loc[target,'prediction'].sum()-pred[target].sum())/T
        assert expected>0
        records.append(dict(file=path.name,sha256=digest(path),score=None,ceiling=[1.8,4],carriers=ids,
            cells=int(target.sum()),sum_h=int(pred[target].sum()),base_sum=int(g.loc[target,'prediction'].sum()),
            expected_score_if_target_equals_v6=float(expected)))
    save_json(directory/'manifest.json',dict(source_commit=PROBE_COMMIT,anchor_sha256=ANCHOR_SHA,
        carrier_records=[known[x] for x in ['p10','p11','p12']],probes=records,
        warning='Diagnostic files intentionally have low scores. Expected scores are not platform results. d01 is byte-identical to existing p13. Decode as capped target sums unless ceilings bound all true cells.'))
    print('DIAGNOSTICS',len(records),'(one existing, four new)',flush=True)


def training_pack(validation,reference):
    directory=ROOT/'data/neural_training_pack';directory.mkdir(parents=True,exist_ok=True)
    exp=Experiment();state=regimes(exp)
    g=pd.MultiIndex.from_product([DATES,ROUTES,range(24)],names=['date','route','hour']).to_frame(index=False)
    day=g.date.dt.dayofyear.to_numpy()-1;ri=np.searchsorted(ROUTES,g.route.to_numpy())
    g['boardings']=np.nan
    hist=day<304;g.loc[hist,'boardings']=exp.y[day[hist],ri[hist],g.loc[hist,'hour'].to_numpy()]
    g['kind']=exp.kind[day];g['holiday']=exp.holiday[day];g['dow']=exp.dow[day]
    g['network_regime']=state[day,ri]
    city=pd.read_csv(ROOT/'external/datamos_62521_monthly_ridership.csv')
    monthly=city[(city.transport=='Трамвай')&(city.year==2025)].set_index('month').passengers
    g['city_tram_month_total']=g.date.dt.month.map(monthly)
    g['train_quality_ok']=~((day>=89)&(day<=95)&g.route.isin([1,7,11,12,17,25,26,28]).to_numpy())&(g.route!=5).to_numpy()
    g['ts']=g.date+pd.to_timedelta(g.hour,unit='h')
    weather=pd.read_csv(ROOT/'external/weather_moscow_2025_hourly.csv',parse_dates=['ts'])
    g=g.merge(weather,on='ts',validate='many_to_one').sort_values(['date','route','hour']).reset_index(drop=True)
    train=g[g.date<'2025-11-01'].copy();future=g[g.date>='2025-11-01'].drop(columns='boardings').copy()
    assert len(train)==72960 and len(future)==14640 and train.boardings.notna().all()
    train.to_parquet(directory/'history.parquet',index=False)
    future.to_parquet(directory/'future_covariates.parquet',index=False)
    reference.to_parquet(directory/'evaluation_reference.parquet',index=False)
    pd.read_csv(ANCHOR,sep=';').to_parquet(directory/'champion_v6.parquet',index=False)
    validation.to_csv(directory/'shape50_validation.csv',index=False)
    save_json(directory/'folds.json',[dict(name=k,train_end=d,horizon_days=h) for k,d,h in FOLDS])
    for name in ['events_2025.csv','deptrans_incidents_2025.csv','datamos_62521_monthly_ridership.csv']:
        (directory/name).write_bytes((ROOT/'external'/name).read_bytes())
    source=ROOT/'docs/research/neural_architectures_2026-09-26.md'
    if source.exists():(directory/'README.md').write_text(source.read_text())
    paths=[p for p in directory.iterdir() if p.is_file() and p.name!='manifest.json']
    save_json(directory/'manifest.json',dict(anchor_sha256=ANCHOR_SHA,
        files={p.name:digest(p) for p in paths},
        exclusions='Route 5 has no historical target. train_quality_ok flags known corrupt week; it is not the validation scoring mask.',
        target='route/date/hour paid boardings; global WAPE score on 14640 future cells',
        data_boundary='History ends Oct31; future_covariates contains no target. Actual future external weather is intentional and permitted.',
        reference_warning='evaluation_reference contains validation targets and v6-core predictions; never use it for training that same fold. Overlapping folds are not independent. Final v6 is not an OOF training feature.'))
    archive=directory.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.iterdir()):
            if p.is_file():z.write(p,p.name)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print('TRAINING_PACK',archive,'bytes',archive.stat().st_size,flush=True)


def main():
    verify_scored_files();OUT.mkdir(parents=True,exist_ok=True)
    validation,reference=validation_and_pack()
    validation.to_csv(OUT/'shape50_validation.csv',index=False)
    candidate(validation);probes();training_pack(validation,reference)
    verify_scored_files();assert digest(ANCHOR)==ANCHOR_SHA


if __name__=='__main__':main()
