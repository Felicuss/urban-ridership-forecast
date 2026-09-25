"""Shared, cached data and exact v2 replay for the post-v3 experiment round."""
from __future__ import annotations
import hashlib
import json
import lightgbm as lgb
import numpy as np
import pandas as pd
from s42_adaptive_profiles import ROOT, TABLES, ROUTES, DATES, Experiment, final_predictions, score
from s44_residual_learner import Features
from s47_unified_candidate import FOLDS, make_frame, combine
from s45_incident_adjustment import exposure

CACHE=ROOT/'data/round4'
OUT=ROOT/'forecasts/round4'
ANCHOR=ROOT/'forecasts/submission_kaggle_unified_v2.csv'
ANCHOR_SHA='dcf149b828e1272a2b7004705e239abaf7d1291c4a645480c16f53d616eb334b'
CONFIG=json.loads((ROOT/'forecasts/kaggle_round/unified_selection.json').read_text())['configuration']


def init():
    CACHE.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    assert hashlib.sha256(ANCHOR.read_bytes()).hexdigest()==ANCHOR_SHA


def frame_data():
    init()
    path=CACHE/'frames.pkl'
    if path.exists():
        return pd.read_pickle(path)
    exp=Experiment();builder=Features(exp)
    frames=[]
    for i,o in enumerate(range(30,298,7)):
        frames.append(make_frame(builder,exp,o,np.arange(o+1,min(o+62,304))))
        if i%10==0:print('Feature origins',i+1,flush=True)
    data={'train':pd.concat(frames,ignore_index=True)}
    for fold,date,h in FOLDS:
        o=pd.Timestamp(date).dayofyear-1
        data[fold]=make_frame(builder,exp,o,np.arange(o+1,o+h+1))
    data['future']=make_frame(builder,exp,303,np.arange(304,365))
    pd.to_pickle(data,path)
    print('Cached',len(data['train']),'training cells',flush=True)
    return data


def fold_arrays():
    result={}
    exp=Experiment()
    for fold,date,h in FOLDS:
        a=dict(np.load(ROOT/f'data/kaggle_unified/{fold}.npz'))
        o=pd.Timestamp(date).dayofyear-1
        day=np.repeat(np.arange(o+1,o+h+1),240)
        a.update(day=day,route=np.tile(np.repeat(ROUTES,24),h),kind=exp.kind[day])
        a['v2']=combine(a,CONFIG)
        result[fold]=a
    return result


def future_arrays(test=None):
    init()
    path=CACHE/'future_v2.npz'
    if path.exists():return dict(np.load(path))
    if test is None:test=frame_data()['future']
    a={'base':test.base.to_numpy(),'horizon':test.horizon.to_numpy()}
    for name in ['old','rich','direct']:
        model=lgb.Booster(model_file=str(ROOT/f'forecasts/kaggle_round/unified_{name}.txt'))
        raw=model.predict(test[model.feature_name()],num_threads=4)
        p=np.maximum(0,raw if name=='direct' else a['base']+(a['base']+20)*raw)
        a[name]=np.where(a['base']>5,p,a['base'])
    a['v2']=combine(a,CONFIG)
    a['day']=test.target_day.to_numpy();a['route']=test.route.to_numpy();a['kind']=test.kind.to_numpy()
    np.savez_compressed(path,**a)
    return a


def assembly_context():
    exp=Experiment();g,base=final_predictions(exp,'median_windows')
    ex,_=exposure(pd.read_csv(ROOT/'external/deptrans_incidents_2025.csv'))
    alpha=json.loads((TABLES/'kaggle_incident_calibration.json').read_text())['deployed_alpha']
    anchor=pd.read_csv(ANCHOR,sep=';',parse_dates=['date'])
    anchor_grid=g.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    return g,base,1-alpha*ex[304:].reshape(-1),anchor,anchor_grid


def assemble(core,a,ctx):
    g,rule_base,incident,_,_=ctx
    ratio=np.divide(core,a['base'],out=np.ones(len(core)),where=a['base']>5)
    protected=(g.route==5)|((g.route.isin([7,50]))&(g.kind!='workday'))
    ratio[protected]=1
    return np.rint(np.rint(rule_base*ratio)*incident).astype('int64')


def match_protection(pred,a):
    protected=(a['route']==5)|(np.isin(a['route'],[7,50])&(a['kind']!=0))
    return np.where(protected,a['v2'],pred)


def prior_blocks(arrays,current):
    """Exclude even partial target-date overlaps, not just identical fold names."""
    return {k:a for k,a in arrays.items() if a['day'].max()<current['day'].min()}


def export(name,core=None,metadata=None,grid_prediction=None):
    init();a=future_arrays();ctx=assembly_context();g,_,_,anchor,anchor_grid=ctx
    assert np.array_equal(assemble(a['v2'],a,ctx),anchor_grid),'Exact v2 replay failed'
    pred=assemble(core,a,ctx) if grid_prediction is None else grid_prediction
    pred=np.rint(pred).astype('int64')
    forecast=g[['route','date','hour']].assign(prediction=pred)
    sub=anchor.drop(columns='prediction').merge(forecast,on=['route','date','hour'],validate='one_to_one')
    assert len(sub)==14640 and not sub.duplicated(['route','date','hour']).any()
    assert sub[['route','date','hour']].equals(anchor[['route','date','hour']])
    assert np.isfinite(sub.prediction).all() and (sub.prediction>=0).all()
    assert (sub.loc[(sub.date==pd.Timestamp('2025-12-31'))&(sub.hour>=20),'prediction']==0).all()
    assert (sub.loc[(sub.route==5)&(sub.date<pd.Timestamp('2025-12-16')),'prediction']==0).all()
    diff=sub.prediction.to_numpy()-anchor.prediction.to_numpy()
    sub.date=sub.date.dt.strftime('%Y-%m-%d')
    path=OUT/f'{name}.csv';sub.to_csv(path,sep=';',index=False)
    meta=dict(file=path.name,status='unscored',anchor=ANCHOR.name,anchor_score=.90358,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),changed_rows=int((diff!=0).sum()),
        absolute_difference=int(abs(diff).sum()),sum_difference=int(diff.sum()),
        route_changes={str(r):int(diff[sub.route==r].sum()) for r in ROUTES},
        caveat='Reused development periods; local scores are not leaderboard results.',**(metadata or {}))
    registry=ROOT/'forecasts/leaderboard_results.json'
    if registry.exists():
        for result in json.loads(registry.read_text()):
            if result['sha256']==meta['sha256'] and result.get('leaderboard_score') is not None:
                meta.update(status='scored',leaderboard_score=result['leaderboard_score'],evidence=result.get('evidence'))
    path.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    print('EXPORTED',name,'changed',meta['changed_rows'],'delta',meta['sum_difference'],flush=True)
    return meta


def report(rows,name):
    frame=pd.DataFrame(rows);frame.to_csv(TABLES/f'round4_{name}.csv',index=False)
    print(frame.round(6).to_string(index=False),flush=True)
    return frame


if __name__=='__main__':
    d=frame_data();a=future_arrays(d['future']);ctx=assembly_context()
    assert np.array_equal(assemble(a['v2'],a,ctx),ctx[-1])
    print('PASS exact champion replay for 14640 cells',flush=True)
