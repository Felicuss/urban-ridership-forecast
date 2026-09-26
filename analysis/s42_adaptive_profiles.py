"""Kaggle-inspired multi-window / exponentially weighted profiles.

Uses archived calendars, no raw 10 GB data or foundation-model cache required.
Run: python analysis/s42_adaptive_profiles.py
Writes research metrics and new candidates; never replaces the registered best.
"""
from __future__ import annotations

import dataclasses
import calendar
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / 'docs/analysis/tables'
OUT = ROOT / 'forecasts/kaggle_round'
ROUTES = np.array([1, 5, 7, 11, 12, 17, 25, 26, 28, 50])
DATES = pd.date_range('2025-01-01', '2025-12-31')
YEARS = [2019, 2022, 2023, 2024]


def weighted_median(values, weights):
    """Median across axis 0, independently for each route/hour."""
    order = np.argsort(values, axis=0)
    sorted_values = np.take_along_axis(values, order, axis=0)
    sorted_weights = np.take_along_axis(np.broadcast_to(weights[:, None, None], values.shape), order, axis=0)
    k = (np.cumsum(sorted_weights, axis=0) >= weights.sum() / 2).argmax(axis=0)
    return np.take_along_axis(sorted_values, k[None, :, :], axis=0)[0]


class Experiment:
    def __init__(self):
        labels = pd.concat([pd.read_csv(ROOT / f'dataset/labels/labels_day_{s}.csv', sep=';', parse_dates=['date'])
                            for s in ('train', 'test')], ignore_index=True)
        index = pd.MultiIndex.from_product([DATES[:304], ROUTES, range(24)], names=['date', 'route', 'hour'])
        self.y = labels.set_index(['date', 'route', 'hour']).boardings.reindex(index, fill_value=0).to_numpy(copy=True).reshape(304, 10, 24)
        cal = pd.read_csv(ROOT / 'external/production_calendar_2025_isdayoff.csv', parse_dates=['date']).set_index('date').reindex(DATES)
        self.off = cal.isdayoff_code.isin([1, 8]).to_numpy()
        self.dow = DATES.dayofweek.to_numpy()
        self.holiday = ((cal.isdayoff_code == 8).to_numpy() | (self.off & (self.dow < 5)))
        self.kind = np.where(~self.off, 0, np.where(self.dow == 5, 1, 2))
        self.month = DATES.month.to_numpy()
        city = pd.read_csv(ROOT / 'external/datamos_62521_monthly_ridership.csv')
        # Reconstruct the unrounded rate, as in the independent standard-library audit.
        city['per_day'] = city.passengers / np.array([calendar.monthrange(int(y), int(m))[1]
                                                     for y,m in zip(city.year,city.month)])
        self.city = city[city.transport == 'Трамвай'].pivot(index='year', columns='month', values='per_day').loc[YEARS]
        self.calendar_factor = np.where(self.holiday & (self.dow < 5), .95, 1.)
        self.calendar_factor *= np.where((self.dow == 5) & ~self.off, .85, 1.)

    def season(self, origin, days):
        om = self.month[origin]
        ratios = self.city.div(self.city[om], axis=0).median(axis=0)
        return 1 + .83 * (ratios.reindex(self.month[days]).to_numpy() - 1)

    def profiles(self, origin):
        result = {}
        all_days = np.arange(origin + 1)
        for window in (14, 28, 56):
            p = np.zeros((3, 10, 24))
            for kind in range(3):
                idx = all_days[(all_days > origin-window) & (self.kind[all_days] == kind) & ~self.holiday[all_days]]
                if len(idx):
                    p[kind] = np.median(self.y[idx], axis=0)
            result[f'median_{window}d'] = p
        result['median_windows'] = np.median([result[f'median_{w}d'] for w in (14, 28, 56)], axis=0)
        for half in (7, 14, 28):
            for method in ('median', 'mean'):
                p = np.zeros((3, 10, 24))
                for kind in range(3):
                    idx = all_days[(all_days > origin-112) & (self.kind[all_days] == kind) & ~self.holiday[all_days]]
                    if len(idx):
                        w = 2. ** (-(origin-idx) / half)
                        p[kind] = (weighted_median(self.y[idx], w) if method == 'median'
                                   else np.average(self.y[idx], weights=w, axis=0))
                result[f'ew_{method}_{half}d'] = p
        result['adaptive'] = .5 * result['median_windows'] + .5 * result['ew_median_14d']
        # Day-of-week estimates are shrunk toward the more stable day-kind profile.
        p_dow = np.zeros((7, 10, 24))
        for dow in range(7):
            idx = all_days[(all_days > origin-56) & (self.dow[all_days] == dow) & ~self.holiday[all_days]]
            kind = min(max(dow-4, 0), 2)
            if len(idx):
                w = 2. ** (-(origin-idx) / 14)
                p_dow[dow] = weighted_median(self.y[idx], w)
            else:
                p_dow[dow] = result['adaptive'][kind]
        return result, p_dow

    def predict_all(self, origin, days):
        profiles, by_dow = self.profiles(origin)
        f = self.season(origin, days) * self.calendar_factor[days]
        result = {name: p[self.kind[days]] * f[:, None, None] for name, p in profiles.items()}
        dow_raw = by_dow[self.dow[days]]
        valid = (~self.holiday[days] & ~((self.dow[days] == 5) & ~self.off[days]))[:, None, None]
        dow_raw = np.where(valid, dow_raw, profiles['adaptive'][self.kind[days]]) * f[:, None, None]
        for weight in (.25, .5):
            result[f'adaptive_dow_{int(100*weight)}'] = (1-weight)*result['adaptive'] + weight*dow_raw
        return result

    def grid(self, days):
        g = pd.MultiIndex.from_product([DATES[days], ROUTES, range(24)], names=['date', 'route', 'hour']).to_frame(index=False)
        idx = np.repeat(days, 240)
        g['dow'] = self.dow[idx]
        g['kind'] = np.array(['workday', 'saturday', 'sunday'])[self.kind[idx]]
        g['is_holiday'] = self.holiday[idx]
        g['day_type'] = np.where(self.holiday[idx] & (self.dow[idx] < 5), 'holiday', g.kind)
        g['ts'] = g.date + pd.to_timedelta(g.hour, unit='h')
        return g


def score(y, p):
    return 1 - np.abs(y-p).sum() / y.sum()


def evaluate(exp):
    rows, route_rows, cache = [], [], {}
    folds = [(f'R{m:02}', (pd.Timestamp(2025, m+1, 1)-pd.Timedelta(days=1)).dayofyear-1, 61) for m in range(1,9)]
    folds.append(('B', pd.Timestamp('2025-09-30').dayofyear-1, 31))
    for fold, origin, horizon in folds:
        days = np.arange(origin+1, origin+1+horizon)
        y = exp.y[days]
        candidates = exp.predict_all(origin, days)
        cache[fold] = candidates
        for name, pred in candidates.items():
            rows.append(dict(fold=fold, origin=str(DATES[origin].date()), days=horizon, variant=name,
                             score=score(y,pred), bias_pct=100*(pred.sum()/y.sum()-1),
                             score_after_day31=score(y[31:],pred[31:]) if horizon>31 else np.nan))
            for j,r in enumerate(ROUTES):
                route_rows.append(dict(fold=fold, variant=name, route=r, absolute_error=np.abs(y[:,j]-pred[:,j]).sum(),
                                       target_sum=y[:,j].sum()))
        print(f'{fold}: baseline={score(y,candidates["median_14d"]):.6f} adaptive={score(y,candidates["adaptive"]):.6f}', flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(TABLES / 'kaggle_profile_backtest.csv', index=False)
    pd.DataFrame(route_rows).to_csv(TABLES / 'kaggle_profile_route_errors.csv', index=False)
    pivot = frame.pivot(index='variant', columns='fold', values='score')
    pivot['rolling61_mean'] = pivot[[f'R{m:02}' for m in range(1,9)]].mean(axis=1)
    pivot['late_mean'] = pivot[['R06','R07','R08','B']].mean(axis=1)
    pivot['wins_vs_2w'] = (pivot[[f'R{m:02}' for m in range(1,9)]].sub(pivot.loc['median_14d', [f'R{m:02}' for m in range(1,9)]]).gt(0)).sum(axis=1)
    pivot.to_csv(TABLES / 'kaggle_profile_summary.csv')
    print(pivot.sort_values('rolling61_mean', ascending=False).round(6).to_string(), flush=True)
    # Independent implementation must match the previously checked standard-library audit.
    audit = pd.read_csv(TABLES / 'audit_ml_backtest.csv')
    for ours, old in [('median_14d', 's30_raw_2w'), ('median_windows','s30_raw_median_2_4_8w')]:
        expected = audit[(audit.group=='rolling61') & (audit.variant==old)].set_index('fold').wape_score
        actual = frame[frame.variant==ours].set_index('fold').score.reindex(expected.index)
        assert np.max(np.abs(actual-expected)) < 1e-10
    return pivot


def final_predictions(exp, name):
    """Apply the same s32 event/calendar rules to the chosen raw profile."""
    import s10_forecast as s10
    from s30_ex_ante import coefficients
    days = np.arange(304, 365)
    g = exp.grid(days)
    hist = exp.grid(np.arange(304))
    hist['boardings'] = exp.y.reshape(-1)
    predictions = exp.predict_all(303, days)
    f = exp.season(303, days) * exp.calendar_factor[days]
    raw = (predictions[name] / f[:,None,None]).reshape(-1)
    c = dataclasses.replace(coefficients(), route5_on=True)
    return g, s10.apply_rules(hist, g, raw, c)


def save_candidate(grid, pred, name, explanation):
    template = pd.read_csv(ROOT / 'dataset/test_submission.csv', sep=';', parse_dates=['date'])
    anchor = pd.read_csv(ROOT / 'forecasts/submission_ex_ante_route5.csv', sep=';')
    fc = grid[['route','date','hour']].assign(prediction=np.rint(np.clip(pred,0,None)).astype('int64'))
    sub = template.drop(columns='prediction').merge(fc, on=['route','date','hour'], how='left', validate='one_to_one')
    assert len(sub)==14640 and sub.prediction.notna().all()
    assert np.isfinite(sub.prediction).all() and (sub.prediction>=0).all()
    sub.date = sub.date.dt.strftime('%Y-%m-%d')
    assert sub[['route','date','hour']].equals(anchor[['route','date','hour']])
    free = (sub.date=='2025-12-31') & (sub.hour>=20)
    assert (sub.loc[free,'prediction']==0).all()
    path = OUT / f'{name}.csv'
    sub.to_csv(path, sep=';', index=False)
    diff = sub.prediction-anchor.prediction
    meta = dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),description=explanation,
                anchor='submission_ex_ante_route5.csv', anchor_leaderboard_score=.89950,
                leaderboard_score=None,changed_rows=int((diff!=0).sum()),sum_prediction=int(sub.prediction.sum()),
                difference_from_anchor=int(diff.sum()),absolute_difference=int(diff.abs().sum()),
                route_changes={str(k):int(v) for k,v in diff.groupby(sub.route).sum().items()})
    path.with_suffix('.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
    print(name, meta['changed_rows'], meta['difference_from_anchor'], flush=True)
    return sub, meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    exp = Experiment()
    evaluate(exp)
    g, reproduction = final_predictions(exp, 'median_14d')
    anchor = pd.read_csv(ROOT / 'forecasts/submission_ex_ante_route5.csv', sep=';', parse_dates=['date'])
    anchor_p = g.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    assert np.array_equal(np.rint(reproduction),anchor_p), 'Anchor reproduction failed'
    print('PASS: exact reproduction of all 14,640 registered-best predictions', flush=True)
    for name in ['median_windows', 'adaptive', 'adaptive_dow_25', 'ew_median_7d', 'ew_median_14d']:
        g,p = final_predictions(exp,name)
        save_candidate(g,p,'profile_'+name,'Only profile changed: '+name+'; same s32 seasonal/calendar/network rules.')


if __name__ == '__main__':
    main()
