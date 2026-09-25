"""Select conservative route weights and write exactly one ARIMA submission."""
from __future__ import annotations
import hashlib
import json
import numpy as np
import pandas as pd
from s60_arima_experiment import (ROOT, CACHE, TABLES, ROUTES, DATES, ARIMA_CACHE,
    fold_arrays, future_arrays, current_core, apply_level, Experiment, event_states)
from s52_round4_common import assembly_context, assemble

FAMILY='robust_arma_weekly_168'
WEIGHTS=np.array([0.,.1,.2,.3,.4,.5])
COMMON_WEIGHT=.25
SHRINK=.5
ANCHOR=ROOT/'forecasts/submission_daily_route5_v4.csv'
ANCHOR_HASH='718acf30fb2d84e3684902f660b5485370acbc8ce2b039122c410f3b5ae302eb'
OUTPUT=ROOT/'forecasts/submission_arima_v5.csv'


def level(key):
    return np.load(ARIMA_CACHE/f'level_{key}_optimal_{FAMILY}.npy')


def select_weights(arrays, predictions, keys):
    selected={}
    for r in ROUTES:
        if r==5:selected[int(r)]=0.;continue
        if len(keys)<2:
            chosen=.1
        else:
            gains=[]
            for k in keys:
                a=arrays[k];mask=a['route']==r;cur=current_core(k,a)
                gains.append((abs(cur[mask]-a['y'][mask]).sum()-
                    abs(predictions[k][:,mask]-a['y'][mask]).sum(axis=1))/a['y'][mask].sum())
            gains=np.array(gains)
            eligible=(gains[-1]>=-1e-12)&((gains>0).sum(axis=0)>=int(np.ceil(len(keys)*2/3)))
            eligible[0]=True
            criterion=.3*gains.mean(axis=0)+.4*gains[-1]+.3*gains.min(axis=0)
            criterion[~eligible]=-np.inf
            chosen=float(WEIGHTS[np.argmax(criterion)])
        # Half-pool toward one common weight: route selection is noisy on six blocks.
        selected[int(r)]=(1-SHRINK)*COMMON_WEIGHT+SHRINK*chosen
    return selected


def predict(a,current,forecast,weights):
    output=current.copy()
    for r,weight in weights.items():
        p=apply_level(a,current,forecast,weight)
        mask=a['route']==r
        output[mask]=p[mask]
    return output


def evaluate_selection():
    arrays=fold_arrays()
    predictions={k:np.array([apply_level(a,current_core(k,a),level(k),w) for w in WEIGHTS]) for k,a in arrays.items()}
    final_weights=select_weights(arrays,predictions,list(arrays))
    rows=[];selection_log={}
    for k,a in arrays.items():
        source=[kk for kk,aa in arrays.items() if aa['day'].max()<a['day'].min()]
        selected=select_weights(arrays,predictions,source)
        selection_log[k]=dict(source_folds=source,weights=selected)
        current=current_core(k,a)
        for mode,weights in [('common_25',{int(r):COMMON_WEIGHT for r in ROUTES}),
                             ('forward_selection',selected),('fitted_final_weights',final_weights)]:
            pred=predict(a,current,level(k),weights)
            loss=float(abs(a['y']-pred).sum());total=float(a['y'].sum())
            baseline=1-float(abs(a['y']-current).sum())/total
            rows.append(dict(mode=mode,fold=k,source_folds=len(source),score=1-loss/total,
                             anchor_score=baseline,gain=1-loss/total-baseline))
    frame=pd.DataFrame(rows)
    frame.to_csv(TABLES/'arima_final_validation.csv',index=False)
    print(frame.pivot(index='mode',columns='fold',values='gain').round(7).to_string(),flush=True)
    print('Final route weights:',final_weights,flush=True)
    return final_weights,frame,selection_log


def main():
    assert hashlib.sha256(ANCHOR.read_bytes()).hexdigest()==ANCHOR_HASH
    registry=json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    assert any(r['sha256']==ANCHOR_HASH and r['leaderboard_score']==.90418 for r in registry)
    weights,validation,selection_log=evaluate_selection()
    a=future_arrays();current=current_core('future',a);pred=predict(a,current,level('future'),weights)
    ctx=assembly_context();g=ctx[0]
    anchor=pd.read_csv(ANCHOR,sep=';',parse_dates=['date'])
    anchor_grid=g.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    # Reconstruct the deployed daily model, except route 5's separately scored fact patch.
    np.testing.assert_array_equal(assemble(current,a,ctx)[g.route!=5],anchor_grid[g.route!=5])
    ratio=np.divide(pred,current,out=np.ones_like(pred),where=current>0)
    result=np.rint(anchor_grid*ratio).astype('int64')
    protected=(a['route']==5)|(np.isin(a['route'],[7,50])&(a['kind']!=0))
    protected |= event_states()[a['day'],np.searchsorted(ROUTES,a['route'])]!=0
    np.testing.assert_array_equal(result[protected],anchor_grid[protected])
    np.testing.assert_array_equal(result[anchor_grid==0],0)
    frame=g[['route','date','hour']].assign(prediction=result)
    sub=anchor.drop(columns='prediction').merge(frame,on=['route','date','hour'],validate='one_to_one')
    assert len(sub)==14640 and not sub.duplicated(['route','date','hour']).any()
    assert sub[['route','date','hour']].equals(anchor[['route','date','hour']])
    assert sub.prediction.dtype.kind in 'iu' and (sub.prediction>=0).all()
    assert (sub.loc[(sub.date==pd.Timestamp('2025-12-31'))&(sub.hour>=20),'prediction']==0).all()
    sub.date=sub.date.dt.strftime('%Y-%m-%d')
    sub.to_csv(OUTPUT,sep=';',index=False)
    diff=result-anchor_grid
    summaries={}
    for mode,part in validation.groupby('mode'):
        summaries[mode]=dict(mean_gain=float(part.gain.mean()),worst_gain=float(part.gain.min()),
            wins=int((part.gain>0).sum()),folds=len(part),october_gain=float(part.loc[part.fold=='B','gain'].iloc[0]))
    metadata=dict(file=OUTPUT.name,status='unscored',leaderboard_score=None,
        sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),anchor=ANCHOR.name,anchor_sha256=ANCHOR_HASH,
        anchor_score=.90418,method='Robust exogenous regression plus SARIMA(1,0,1)(1,0,0)[7] on log daily L1-optimal mass',
        history_days=168,route_weights=weights,raw_daily_ratio_clip=[.7,1.3],
        common_weight=COMMON_WEIGHT,route_weight_shrinkage=SHRINK,
        selection_objective='0.3 mean + 0.4 latest + 0.3 worst route WAPE gain; require latest nonnegative and wins >= 2/3; shrink 50% toward 25%.',
        validation=summaries,forward_selection=selection_log,changed_rows=int((diff!=0).sum()),
        absolute_difference=int(abs(diff).sum()),sum_difference=int(diff.sum()),
        route_sum_difference={str(r):int(diff[g.route==r].sum()) for r in ROUTES},
        caveats=['Model family and policy were developed using these periods; forward selection is not an untouched holdout.',
                 'fitted_final_weights is an in-sample selection diagnostic, not an unbiased quality estimate.',
                 'Historical reference is the v4 daily-model analogue; future-only network/fare rules cannot be fully reproduced on all historical folds.',
                 'Future calendar and actual weather are allowed external covariates; no future validation labels used.',
                 'Local improvements do not determine the new leaderboard score.'])
    for r in registry:
        if r['sha256']==metadata['sha256'] and r.get('leaderboard_score') is not None:
            metadata.update(status='scored_rejected' if r['leaderboard_score']<metadata['anchor_score'] else 'scored',
                leaderboard_score=r['leaderboard_score'],evidence=r.get('evidence'),
                leaderboard_delta=round(r['leaderboard_score']-metadata['anchor_score'],8))
    OUTPUT.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    changes=g[['route','date']].copy();changes['before']=anchor_grid;changes['after']=result
    changes['month']=changes.date.dt.month
    grouped=changes.groupby(['route','month'])[['before','after']].sum()
    grouped['change_pct']=100*(grouped.after/grouped.before.replace(0,np.nan)-1)
    grouped.to_csv(TABLES/'arima_future_changes.csv')
    assert hashlib.sha256(ANCHOR.read_bytes()).hexdigest()==ANCHOR_HASH
    print(json.dumps({k:metadata[k] for k in ['file','sha256','changed_rows','sum_difference','route_sum_difference','validation']},indent=2),flush=True)


if __name__=='__main__':main()
