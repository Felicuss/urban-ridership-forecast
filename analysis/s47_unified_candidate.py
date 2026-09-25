"""Combine locally selected ideas into ONE new submission.

Compare the registered v1_weather core with richer profile statistics, a direct
count model, and two horizon weights. Only an internally selected mixture is
exported for the leaderboard. Historical folds are reused for selection; their
scores are development estimates, not an independent final holdout.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from s42_adaptive_profiles import Experiment, ROOT, TABLES, ROUTES, score, final_predictions
from s44_residual_learner import Features, fit_predict
from s45_incident_adjustment import exposure

CACHE = ROOT / 'data/kaggle_unified'
MODEL_DIR = ROOT / 'forecasts/kaggle_round'
FOLDS = [('R04','2025-04-30',61),('R05','2025-05-31',61),('R06','2025-06-30',61),
         ('R07','2025-07-31',61),('R08','2025-08-31',61),('B','2025-09-30',31)]


def reliability_features(exp, origin, days):
    """Dispersion/coverage comes exclusively from observations at or before origin."""
    all_days = np.arange(origin+1)
    features = {}
    for window in (28,56):
        stats = {name:np.zeros((3,10,24)) for name in ['iqr','tail_width','zero_rate','count']}
        for kind in range(3):
            ix = all_days[(all_days>origin-window) & (exp.kind[all_days]==kind) & ~exp.holiday[all_days]]
            if not len(ix):
                continue
            values = exp.y[ix]
            q10,q25,q50,q75,q90 = np.quantile(values,[.1,.25,.5,.75,.9],axis=0)
            stats['iqr'][kind] = (q75-q25)/(q50+20)
            stats['tail_width'][kind] = (q90-q10)/(q50+20)
            stats['zero_rate'][kind] = (values==0).mean(axis=0)
            stats['count'][kind] = len(ix)
        for name,values in stats.items():
            features[f'{name}_{window}d'] = values[exp.kind[days]].reshape(-1)
    # Known calendar structure: position/length of the contiguous day-off block.
    block_len = np.zeros(365)
    block_pos = np.zeros(365)
    start = 0
    while start<365:
        end=start+1
        while end<365 and exp.off[end]==exp.off[start]:
            end+=1
        if exp.off[start]:
            block_len[start:end] = end-start
            block_pos[start:end] = np.arange(1,end-start+1)
        start=end
    features['off_block_length'] = np.repeat(block_len[days],240)
    features['off_block_position'] = np.repeat(block_pos[days],240)
    return pd.DataFrame(features)


def make_frame(builder, exp, origin, days):
    return pd.concat([builder.frame(origin,days),reliability_features(exp,origin,days)],axis=1)


def fit_direct(train,test,features):
    corrupt = train.target_day.between(89,95) & train.route.isin([1,7,11,12,17,25,26,28])
    train = train[(train.base>5)&~corrupt&(train.route!=5)]
    count=train.groupby(['target_day','route','hour']).y.transform('size')
    ds=lgb.Dataset(train[features],label=train.y,weight=1/count,categorical_feature=['route'])
    params=dict(objective='regression_l1',learning_rate=.04,num_leaves=31,min_data_in_leaf=250,
                feature_fraction=.9,lambda_l2=10,verbosity=-1,seed=2026,num_threads=4,
                deterministic=True,force_col_wise=True)
    model=lgb.train(params,ds,num_boost_round=350)
    p=np.clip(model.predict(test[features]),0,None)
    p=np.where(test.base>5,p,test.base)
    return p,model


def mixtures():
    # Small, declared search: stronger residual; more reliable history; a second model.
    configs=[dict(name='champion_core',old=1.,rich=0.,direct=0.,near=.25,far=.25)]
    for near,far in [(.35,.35),(.5,.5),(.25,.5),(.35,.5)]:
        configs.append(dict(name=f'old_{near}_{far}',old=1.,rich=0.,direct=0.,near=near,far=far))
    for old,rich,direct in [(0.,1.,0.),(.5,.5,0.),(.4,.4,.2),(.25,.5,.25)]:
        for near,far in [(.25,.25),(.35,.35),(.25,.5),(.35,.5)]:
            configs.append(dict(name=f'mix_{old}_{rich}_{direct}_{near}_{far}',
                                old=old,rich=rich,direct=direct,near=near,far=far))
    return configs


def combine(a,c):
    model=c['old']*a['old']+c['rich']*a['rich']+c['direct']*a['direct']
    weight=np.where(a['horizon']<=30,c['near'],c['far'])
    return np.clip(a['base']+weight*(model-a['base']),0,None)


def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    exp=Experiment()
    builder=Features(exp)
    frames=[make_frame(builder,exp,o,np.arange(o+1,min(o+62,304))) for o in range(30,298,7)]
    train_all=pd.concat(frames,ignore_index=True)
    old_features=lgb.Booster(model_file=str(MODEL_DIR/'residual_with_weather.txt')).feature_name()
    rich_features=[c for c in train_all if c not in ['base','target_day','origin','y']]
    models={'old':(fit_predict,old_features),'rich':(fit_predict,rich_features),'direct':(fit_direct,rich_features)}
    forecasts={}
    for fold,date,horizon in FOLDS:
        origin=pd.Timestamp(date).dayofyear-1
        days=np.arange(origin+1,origin+horizon+1)
        test=make_frame(builder,exp,origin,days)
        train=train_all[(train_all.target_day<=origin)&(train_all.origin<origin)]
        assert train.target_day.max()<=origin
        a=dict(y=test.y.to_numpy(),base=test.base.to_numpy(),horizon=test.horizon.to_numpy())
        for name,(fn,feats) in models.items():
            a[name],_=fn(train,test,feats)
        forecasts[fold]=a
        np.savez_compressed(CACHE/f'{fold}.npz',**a)
        print(fold,{n:round(score(a['y'],a['base']+.25*(a[n]-a['base'])),6) for n in models},flush=True)
    rows=[]
    configs=mixtures()
    for c in configs:
        for fold,a in forecasts.items():
            p=combine(a,c)
            for period,mask in [('all',np.ones(len(p),dtype=bool)),('near',a['horizon']<=30),('far',a['horizon']>30)]:
                rows.append(dict(candidate=c['name'],fold=fold,period=period,score=score(a['y'][mask],p[mask])))
    scores=pd.DataFrame(rows)
    scores.to_csv(TABLES/'kaggle_unified_backtest.csv',index=False)
    summary=scores[scores.period=='all'].pivot(index='candidate',columns='fold',values='score')
    gains=summary-summary.loc['champion_core']
    summary['mean']=summary.mean(axis=1)
    summary['min_gain']=gains.min(axis=1)
    summary['wins']=(gains>0).sum(axis=1)
    summary['mean_gain']=gains.mean(axis=1)
    summary['eligible']=(summary.min_gain>=-.0003)&(summary.wins>=5)&(summary.mean_gain>.00015)
    eligible=summary[summary.eligible].sort_values('mean',ascending=False)
    summary.sort_values('mean',ascending=False).to_csv(TABLES/'kaggle_unified_summary.csv')
    print(summary.sort_values('mean',ascending=False).round(6).to_string(),flush=True)
    # Check the regenerated champion core against the first round, before selection.
    prior=pd.read_csv(TABLES/'kaggle_residual_backtest.csv')
    prior=prior[(prior.model=='with_weather')&(prior.blend_weight==.25)].set_index('fold').score
    for fold in forecasts:
        assert abs(summary.loc['champion_core',fold]-prior[fold])<1e-10
    if eligible.empty:
        (MODEL_DIR/'unified_selection.json').write_text(json.dumps(dict(status='no_candidate_passed',
            reason='No mixture improved >=5/6 folds with worst deterioration <=0.0003 and mean gain >0.00015.'),indent=2)+'\n')
        print('No new leaderboard candidate justified; retain 0.90236.',flush=True)
        return
    chosen=next(c for c in configs if c['name']==eligible.index[0])
    test=make_frame(builder,exp,303,np.arange(304,365))
    a=dict(base=test.base.to_numpy(),horizon=test.horizon.to_numpy())
    for name,(fn,feats) in models.items():
        a[name],model=fn(train_all,test,feats)
        model.save_model(str(MODEL_DIR/f'unified_{name}.txt'))
    g,rule_base=final_predictions(exp,'median_windows')
    incident_table=pd.read_csv(ROOT/'external/deptrans_incidents_2025.csv')
    ex,_=exposure(incident_table)
    alpha=json.loads((TABLES/'kaggle_incident_calibration.json').read_text())['deployed_alpha']

    def assemble(c):
        p=combine(a,c)
        ratio=np.divide(p,a['base'],out=np.ones(len(p)),where=a['base']>5)
        protect=(g.route==5)|((g.route.isin([7,50]))&(g.kind!='workday'))
        ratio[protect]=1
        # Preserve v1's rounding order before multiplying by incident exposure.
        return np.rint(np.rint(rule_base*ratio)*(1-alpha*ex[304:].reshape(-1))).astype('int64')

    anchor=pd.read_csv(ROOT/'forecasts/submission_kaggle_v1_weather.csv',sep=';',parse_dates=['date'])
    anchor_grid=g.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    assert np.array_equal(assemble(configs[0]),anchor_grid),'Champion replay failed'
    pred=assemble(chosen)
    fc=g[['route','date','hour']].assign(prediction=pred)
    sub=anchor.drop(columns='prediction').merge(fc,on=['route','date','hour'],validate='one_to_one')
    assert len(sub)==14640 and sub.prediction.notna().all() and (sub.prediction>=0).all()
    assert (sub.loc[(sub.date==pd.Timestamp('2025-12-31'))&(sub.hour>=20),'prediction']==0).all()
    assert sub.loc[sub.route==5,'prediction'].equals(anchor.loc[anchor.route==5,'prediction'])
    sub.date=sub.date.dt.strftime('%Y-%m-%d')
    path=ROOT/'forecasts/submission_kaggle_unified_v2.csv'
    sub.to_csv(path,sep=';',index=False)
    diff=sub.prediction.to_numpy()-anchor.prediction.to_numpy()
    selection=dict(status='one_candidate_ready',configuration=chosen,compared_configurations=len(configs),
                   development_mean=float(eligible.iloc[0]['mean']),
                   development_mean_gain=float(eligible.iloc[0]['mean_gain']),
                   development_min_gain=float(eligible.iloc[0]['min_gain']),
                   development_folds_won=int(eligible.iloc[0]['wins']),
                   selection_rule='At least 5/6 folds improved; each deterioration <=0.0003; mean gain >0.00015; maximize mean among eligible.',
                   caveat='Overlapping, reused development folds; not an independent holdout.',
                   file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   anchor='submission_kaggle_v1_weather.csv',anchor_score=.90236,leaderboard_score=None,
                   changed_rows=int((diff!=0).sum()),sum_difference=int(diff.sum()),absolute_difference=int(np.abs(diff).sum()),
                   route_changes={str(r):int(diff[sub.route.to_numpy()==r].sum()) for r in ROUTES})
    registry=ROOT/'forecasts/leaderboard_results.json'
    if registry.exists():
        for result in json.loads(registry.read_text()):
            if (result['file'],result['sha256'])==(selection['file'],selection['sha256']):
                selection['leaderboard_score']=result['leaderboard_score']
                selection['evidence']=result.get('evidence')
                if result['leaderboard_score'] is not None:
                    selection['status']='scored'
    (MODEL_DIR/'unified_selection.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(selection,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
