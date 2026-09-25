"""Build one v6 candidate: hourly shares + mild actual city tram anomaly.

The scored v4 CSV is immutable. All target-month city statistics are explicitly
ex-post external information; hidden route labels are neither available nor used.
"""
from __future__ import annotations

import hashlib
import json
import numpy as np
import pandas as pd
from s52_round4_common import (ROOT, CACHE, TABLES, ROUTES, FOLDS, Experiment,
    fold_arrays, future_arrays, assembly_context, assemble)
from s55_daily_level import rescale
from s62_hourly_shape import SHAPE_CACHE, shape_adjust, normalize
from s63_external_level_probe import factors, apply_factor

ANCHOR = ROOT/'forecasts/submission_daily_route5_v4.csv'
ANCHOR_HASH = '718acf30fb2d84e3684902f660b5485370acbc8ce2b039122c410f3b5ae302eb'
OUTPUT = ROOT/'forecasts/submission_shape_facts_v6.csv'
DAILY_WEIGHT = .25
SHAPE_WEIGHT = .35
CITY_WEIGHT = .25


def protected_cells(a):
    return (a['route'] == 5) | (np.isin(a['route'], [7, 50]) & (a['kind'] != 0))


def shares(key):
    return (np.load(SHAPE_CACHE/f'direct_{key}.npy') +
            np.load(SHAPE_CACHE/f'residual_{key}.npy')) / 2


def transfer_shape(anchor, current, share, a, weight=SHAPE_WEIGHT):
    """Transfer model changes onto deployed calendar/incident rules, holding mass.

    Renormalization is essential: the deployed profile differs from the research
    core on incident days and on Dec 31. Multiplying ratios alone changes totals.
    """
    shaped = shape_adjust(current, share, a, weight)
    ratio = np.divide(shaped, current, out=np.ones_like(shaped), where=current > 0)
    total = anchor.reshape(-1, 24).sum(axis=1)
    proposed = normalize(anchor * ratio) * total[:, None]
    out = proposed.reshape(-1)
    out[protected_cells(a)] = anchor[protected_cells(a)]
    np.testing.assert_allclose(out.reshape(-1, 24).sum(axis=1), total, rtol=1e-12, atol=1e-7)
    np.testing.assert_array_equal(out[anchor == 0], 0)
    return out


def round_daily(values, totals):
    """Largest remainder rounding: exact integer daily sums, no new positive hours."""
    p = values.reshape(-1, 24)
    if not np.isfinite(p).all() or (p < 0).any():
        raise ValueError('Hourly predictions must be finite and nonnegative')
    totals = np.asarray(totals, dtype=np.int64)
    if (totals < 0).any() or ((p.sum(axis=1) == 0) & (totals > 0)).any():
        raise ValueError('Daily targets require nonnegative totals and positive support')
    raw = normalize(p) * totals[:, None]
    out = np.floor(raw).astype('int64')
    remainder = totals - out.sum(axis=1)
    for i, n in enumerate(remainder):
        eligible = np.flatnonzero(p[i] > 0)
        rank = eligible[np.argsort(-(raw[i, eligible] - out[i, eligible]), kind='stable')]
        if not 0 <= n <= len(eligible):
            raise ValueError('Invalid rounding residual')
        out[i, rank[:n]] += 1
    np.testing.assert_array_equal(out.sum(axis=1), totals)
    np.testing.assert_array_equal(out[p == 0], 0)
    return out.reshape(-1)


def verify_scored_files():
    records = json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    for row in records:
        path = ROOT/'forecasts'/row['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], path
    assert hashlib.sha256(ANCHOR.read_bytes()).hexdigest() == ANCHOR_HASH
    return len(records)


def evaluate():
    rows = []
    arrays = fold_arrays()
    exp = Experiment()
    for key, date, h in FOLDS:
        a = arrays[key]
        origin = pd.Timestamp(date).dayofyear - 1
        current = rescale(a, np.load(CACHE/f'daily_optimal_{key}.npy'), DAILY_WEIGHT)
        f, _ = factors(exp, origin, np.arange(origin+1, origin+h+1))
        shaped = transfer_shape(current, current, shares(key), a)
        variants = {'shape_only': shaped,
                    'city_only': apply_factor(current, a, f['tram'], CITY_WEIGHT),
                    'combined': apply_factor(shaped, a, f['tram'], CITY_WEIGHT)}
        for name, pred in variants.items():
            for route in [0] + [int(r) for r in ROUTES if r != 5]:
                mask = np.ones(len(pred), bool) if route == 0 else a['route'] == route
                total = a['y'][mask].sum()
                baseline = 1-abs(current[mask]-a['y'][mask]).sum()/total
                score = 1-abs(pred[mask]-a['y'][mask]).sum()/total
                rows.append(dict(fold=key, variant=name, route=route,
                                 anchor_score=baseline, score=score, gain=score-baseline))
    frame = pd.DataFrame(rows)
    frame.to_csv(TABLES/'round6_final_validation.csv', index=False)
    return frame


def main():
    count = verify_scored_files()
    validation = evaluate()
    a = future_arrays()
    current = rescale(a, np.load(CACHE/'daily_optimal_future.npy'), DAILY_WEIGHT)
    ctx = assembly_context()
    g = ctx[0]
    anchor = pd.read_csv(ANCHOR, sep=';', parse_dates=['date'])
    anchor_grid = g.merge(anchor, on=['route', 'date', 'hour'], validate='one_to_one').prediction.to_numpy()
    np.testing.assert_array_equal(assemble(current, a, ctx)[g.route != 5], anchor_grid[g.route != 5])
    shaped = transfer_shape(anchor_grid, current, shares('future'), a)
    ff, _ = factors(Experiment(), 303, np.arange(304, 365))
    level_factor = apply_factor(np.ones(len(current)), a, ff['tram'], CITY_WEIGHT)
    daily_factor = level_factor.reshape(-1, 24)[:, 0]
    np.testing.assert_array_equal(level_factor.reshape(-1, 24), np.repeat(daily_factor[:, None], 24, axis=1))
    totals = np.rint(anchor_grid.reshape(-1, 24).sum(axis=1)*daily_factor).astype('int64')
    result = round_daily(shaped, totals)
    np.testing.assert_array_equal(result[protected_cells(a)], anchor_grid[protected_cells(a)])
    np.testing.assert_array_equal(result[anchor_grid == 0], 0)
    frame = g[['route', 'date', 'hour']].assign(prediction=result)
    sub = anchor.drop(columns='prediction').merge(frame, on=['route', 'date', 'hour'], validate='one_to_one')
    assert len(sub) == 14640 and not sub.duplicated(['route', 'date', 'hour']).any()
    assert sub[['route', 'date', 'hour']].equals(anchor[['route', 'date', 'hour']])
    assert sub.prediction.dtype.kind in 'iu' and (sub.prediction >= 0).all()
    assert (sub.loc[(sub.date == pd.Timestamp('2025-12-31')) & (sub.hour >= 20), 'prediction'] == 0).all()
    assert (sub.loc[(sub.route == 5) & (sub.date < pd.Timestamp('2025-12-16')), 'prediction'] == 0).all()
    sub.date = sub.date.dt.strftime('%Y-%m-%d')
    sub.to_csv(OUTPUT, sep=';', index=False)
    diff = result-anchor_grid
    summaries = {}
    for name, part in validation[validation.route == 0].groupby('variant'):
        summaries[name] = dict(mean_gain=float(part.gain.mean()), worst_gain=float(part.gain.min()),
                              wins=int((part.gain > 0).sum()), folds=len(part),
                              october_gain=float(part.loc[part.fold == 'B', 'gain'].iloc[0]))
    provenance_paths = [ROOT/'analysis/s62_hourly_shape.py', ROOT/'analysis/s63_external_level_probe.py',
                        ROOT/'analysis/s64_package_shape_facts.py',
                        ROOT/'external/datamos_62521_monthly_ridership.csv']
    provenance_paths += [SHAPE_CACHE/f'{m}.txt' for m in ['direct', 'residual']]
    metadata = dict(file=OUTPUT.name, status='unscored', leaderboard_score=None,
        sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), anchor=ANCHOR.name,
        anchor_sha256=ANCHOR_HASH, anchor_score=.90418,
        method='35% normalized hourly share ensemble (50/50 direct/residual L1 LightGBM), plus 25% log city tram anomaly',
        daily_weight=DAILY_WEIGHT, shape_weight=SHAPE_WEIGHT, city_weight=CITY_WEIGHT,
        city_factor_clip=[.97, 1.03],
        city_factors={str(m):float(ff['tram'][d]**CITY_WEIGHT) for m, d in [(11, 0), (12, 30)]},
        external_information='Actual target-month city ridership and weather; previously deployed route/network facts. Not an ex-ante forecast.',
        new_exact_route_labels_found=False, validation=summaries,
        changed_rows=int((diff != 0).sum()), absolute_difference=int(abs(diff).sum()),
        sum_difference=int(diff.sum()), protected_scored_files=count,
        route_sum_difference={str(r):int(diff[g.route == r].sum()) for r in ROUTES},
        provenance_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in provenance_paths},
        caveats=['Overlapping historical periods were reused to develop and select this candidate, not untouched test folds.',
                 'Historical comparisons use the v4 core analogue. Future-specific network and fare rules only enter final assembly.',
                 'Rounded daily ridership statements for routes 11/12/17 are not exact paid-validation targets and were not used as equalities.',
                 'The city index includes routes outside these ten and cannot identify route-specific target levels.',
                 'Local gains do not establish any particular leaderboard score.'])
    # Rebuilding a scored artifact must not discard its confirmed platform result.
    for record in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()):
        if record['sha256'] == metadata['sha256'] and record.get('leaderboard_score') is not None:
            metadata.update(status='scored', leaderboard_score=record['leaderboard_score'],
                leaderboard_delta=round(record['leaderboard_score']-metadata['anchor_score'], 8),
                evidence=record.get('evidence'))
    OUTPUT.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    changes = g[['route', 'date']].assign(before=anchor_grid, after=result)
    changes['month'] = changes.date.dt.month
    grouped = changes.groupby(['route', 'month'])[['before', 'after']].sum()
    grouped['change_pct'] = 100*(grouped.after/grouped.before.replace(0, np.nan)-1)
    grouped.to_csv(TABLES/'round6_future_changes.csv')
    assert verify_scored_files() == count
    print(json.dumps({k:metadata[k] for k in ['file', 'sha256', 'changed_rows', 'sum_difference', 'city_factors', 'validation']}, indent=2))


if __name__ == '__main__':
    main()
