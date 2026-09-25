"""Direct multi-horizon L1 correction with multi-scale profiles and external features.

All observed training targets must precede each evaluation origin. Actual future
weather/events are allowed by this competition and supplied explicitly as features.
Run after s42: python analysis/s44_residual_learner.py
"""
from __future__ import annotations

import json
import lightgbm as lgb
import numpy as np
import pandas as pd

from s42_adaptive_profiles import Experiment, ROOT, OUT, TABLES, DATES, ROUTES, score, final_predictions, save_candidate


class Features:
    def __init__(self, exp):
        self.exp = exp
        off = exp.off
        self.cal = pd.DataFrame(index=np.arange(365))
        for delta in [-3,-2,-1,1,2,3]:
            ix = np.clip(np.arange(365)+delta,0,364)
            self.cal[f'off_{delta}'] = off[ix].astype(int)
            self.cal[f'holiday_{delta}'] = exp.holiday[ix].astype(int)
        holiday_idx = np.where(exp.holiday)[0]
        self.cal['days_to_holiday'] = [min([h-d for h in holiday_idx if h>=d]+[60]) for d in range(365)]
        self.cal['days_since_holiday'] = [min([d-h for h in holiday_idx if h<=d]+[60]) for d in range(365)]
        self.cal = self.cal.clip(upper=60)
        weather = pd.read_csv(ROOT/'external/weather_moscow_2025_hourly.csv',parse_dates=['ts']).sort_values('ts')
        weather['d'] = weather.ts.dt.dayofyear-1
        weather['hour'] = weather.ts.dt.hour
        cols = ['temperature_2m','precipitation','snowfall','wind_speed_10m']
        w = weather[cols].copy()
        for col in ['precipitation','snowfall']:
            for window in [3,12,24]:
                w[f'{col}_{window}h'] = w[col].rolling(window,min_periods=1).sum()
        w['temperature_change_6h'] = w.temperature_2m.diff(6).fillna(0)
        self.weather_cols = list(w)
        self.weather = weather[['d','hour']].join(w).set_index(['d','hour'])
        self.events = pd.read_csv(ROOT/'external/events_2025.csv')

    def frame(self, origin, days):
        exp = self.exp
        preds = exp.predict_all(origin, days)
        base = preds['median_windows'].reshape(-1)
        g = exp.grid(days)
        idx = np.repeat(days,240)
        x = pd.DataFrame(dict(route=g.route, hour=g.hour,dow=g.dow,kind=exp.kind[idx],
                              holiday=g.is_holiday.astype(int), horizon=idx-origin,
                              log_base=np.log1p(base)))
        for name in ['median_14d','median_28d','median_56d','ew_median_14d','ew_mean_7d','ew_median_28d','adaptive_dow_25']:
            x['ratio_'+name] = ((preds[name].reshape(-1)+20)/(base+20)).clip(0,5)
        x['season'] = np.repeat(exp.season(origin,days),240)
        for col in self.cal:
            x[col] = self.cal[col].to_numpy()[idx]
        for event_type in ['closure','detour','merge','night_limit','restore','network']:
            x['event_'+event_type] = 0
        x['event_age'] = 90
        for event in self.events.itertuples():
            if event.type not in ['closure','detour','merge','night_limit','restore','network']:
                continue
            routes = ROUTES if event.routes=='all' else [int(r) for r in event.routes.split(';')]
            sel = g.route.isin(routes) & g.date.between(event.start,event.end)
            if event.days=='weekends':
                sel &= exp.off[idx]
            if event.type=='night_limit':
                sel &= g.hour>=22
            x.loc[sel,'event_'+event.type] = 1
            x.loc[sel,'event_age'] = np.minimum(x.loc[sel,'event_age'],(g.loc[sel,'date']-pd.Timestamp(event.start)).dt.days.clip(0,90))
        w = self.weather.reindex(pd.MultiIndex.from_arrays([idx,g.hour])).reset_index(drop=True)
        for col in self.weather_cols:
            x[col] = w[col].fillna(0).to_numpy()
        x['base'] = base
        x['target_day'] = idx
        x['origin'] = origin
        x['y'] = exp.y[days].reshape(-1) if days[-1]<304 else np.nan
        return x


def fit_predict(train, test, features, rounds=250):
    # Known validator misassignment is excluded, not used to learn demand.
    corrupt = train.target_day.between(89,95) & train.route.isin([1,7,11,12,17,25,26,28])
    train = train[(train.base>5) & ~corrupt & (train.route!=5)]
    scale = train.base+20
    # Equal total weight per target cell despite overlapping origins.
    count = train.groupby(['target_day','route','hour']).y.transform('size')
    ds = lgb.Dataset(train[features], label=(train.y-train.base)/scale,
                     weight=scale/count, categorical_feature=['route'])
    params=dict(objective='regression_l1',learning_rate=.035,num_leaves=15,min_data_in_leaf=250,
                feature_fraction=.9,lambda_l2=10,verbosity=-1,seed=2026,num_threads=4,
                deterministic=True,force_col_wise=True)
    model = lgb.train(params,ds,num_boost_round=rounds)
    correction = model.predict(test[features])
    pred = np.clip(test.base.to_numpy()+correction*(test.base.to_numpy()+20),0,None)
    pred = np.where(test.base>5,pred,test.base)
    return pred,model


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    exp = Experiment()
    builder = Features(exp)
    frames=[]
    for o in range(30,298,7):
        frames.append(builder.frame(o,np.arange(o+1,min(o+62,304))))
    train_all=pd.concat(frames,ignore_index=True)
    print('Training examples:',len(train_all),flush=True)
    excluded=['base','target_day','origin','y']
    expanded=[c for c in train_all if c not in excluded+builder.weather_cols]
    feature_sets={
        'calendar_profiles_events':expanded,
        'with_weather':expanded+builder.weather_cols,
    }
    rows=[]
    for fold,date,horizon in [('R04','2025-04-30',61),('R05','2025-05-31',61),('R06','2025-06-30',61),
                              ('R07','2025-07-31',61),('R08','2025-08-31',61),('B','2025-09-30',31)]:
        origin=pd.Timestamp(date).dayofyear-1
        days=np.arange(origin+1,origin+horizon+1)
        test=builder.frame(origin,days)
        train=train_all[(train_all.target_day<=origin)&(train_all.origin<origin)]
        for name,feats in feature_sets.items():
            p,model=fit_predict(train,test,feats)
            for weight in [0.,.25,.5,1.]:
                blend=(1-weight)*test.base.to_numpy()+weight*p
                rows.append(dict(fold=fold,model=name,blend_weight=weight,score=score(test.y.to_numpy(),blend),
                                 bias_pct=100*(blend.sum()/test.y.sum()-1)))
            print(fold,name,'baseline',round(score(test.y.to_numpy(),test.base.to_numpy()),6),
                  'model',round(score(test.y.to_numpy(),p),6),flush=True)
            pd.DataFrame(rows).to_csv(TABLES/'kaggle_residual_backtest.csv',index=False)
    summary=pd.DataFrame(rows).pivot_table(index=['model','blend_weight'],columns='fold',values='score')
    summary['mean']=summary.mean(axis=1)
    summary.to_csv(TABLES/'kaggle_residual_summary.csv')
    print(summary.round(6).to_string(),flush=True)
    # Export experimental blends even if they lose locally; selection is reported separately.
    test=builder.frame(303,np.arange(304,365))
    g,rule_base=final_predictions(exp,'median_windows')
    for name,feats in feature_sets.items():
        p,model=fit_predict(train_all,test,feats)
        model.save_model(str(OUT/f'residual_{name}.txt'))
        pd.DataFrame({'feature':feats,'gain':model.feature_importance(importance_type='gain')}).sort_values('gain',ascending=False).to_csv(TABLES/f'kaggle_importance_{name}.csv',index=False)
        # Restore/free-fare/cold-start rules remain authoritative; avoid undoing them.
        ratio=np.divide(p,test.base.to_numpy(),out=np.ones(len(p)),where=test.base.to_numpy()>5)
        protect=(g.route==5)|((g.route.isin([7,50])) & (g.kind!='workday'))
        ratio[protect]=1
        for weight in [.25,.5]:
            pred=rule_base*((1-weight)+weight*ratio)
            save_candidate(g,pred,f'residual_{name}_{int(100*weight)}',
                           f'Experimental residual {name}, weight={weight}; protected restored weekends and route5. See local scores.')


if __name__=='__main__':
    main()
