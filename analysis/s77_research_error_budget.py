"""Information diagnostics, NOT a forecast or a leaderboard estimate.

Every oracle fits the evaluation labels and is deliberately optimistic. The
triangle-inequality bound uses only scored forecast files and the approximate
target total from the existing route-5 probe. No submission files are written.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/analysis/tables/research_094'
BEST = .90570
TARGET = .94
TOTAL = 5_040_000 / (.90553 - .51431)


def weighted_median(values, weights):
    order = np.argsort(values)
    w = weights[order]
    return values[order[np.searchsorted(np.cumsum(w), w.sum()/2)]]


def oracle_scale(y, pred, group):
    """Exact nonnegative L1 scalar in each group, fixing zero support."""
    result = pred.copy()
    for key in np.unique(group):
        ix = (group == key) & (pred > 1e-10)
        if ix.any():
            result[ix] *= weighted_median(y[ix]/pred[ix], pred[ix])
    assert np.isfinite(result).all() and (result >= 0).all()
    assert abs(result-y).sum() <= abs(pred-y).sum() + 1e-6
    return result


def group_codes(frame, columns):
    return pd.MultiIndex.from_frame(frame[columns]).factorize()[0]


def prediction_budget():
    base = pd.read_csv(ROOT/'forecasts/submission_shape50_v7.csv', sep=';')
    registry = json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    rows = []
    for record in registry:
        path = ROOT/'forecasts'/record['file']
        if not path.exists():
            candidates = list((ROOT/'forecasts').rglob(Path(record['file']).name))
            candidates = [p for p in candidates if hashlib.sha256(p.read_bytes()).hexdigest() == record['sha256']]
            if not candidates:
                raise FileNotFoundError(record['file'])
            path = candidates[0]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
        other = pd.read_csv(path, sep=';')
        joined = base.merge(other, on=['route','date','hour'], validate='one_to_one', suffixes=('_v7','_other'))
        assert len(joined) == 14640
        displacement = abs(joined.prediction_v7-joined.prediction_other).sum()
        rows.append(dict(file=str(path.relative_to(ROOT/'forecasts')),
                         leaderboard_score=record['leaderboard_score'],
                         l1_distance_to_v7=int(displacement),
                         optimistic_score_bound=min(1., BEST+displacement/TOTAL),
                         sufficient_movement_for_094=bool(displacement >= (TARGET-BEST)*TOTAL)))
    pd.DataFrame(rows).to_csv(OUT/'submission_distance_bounds.csv', index=False)
    summary = dict(best_score=BEST, target_score=TARGET,
        approximate_target_total=TOTAL,
        remaining_absolute_error=(1-BEST)*TOTAL,
        target_absolute_error=(1-TARGET)*TOTAL,
        required_absolute_error_reduction=(TARGET-BEST)*TOTAL,
        required_relative_error_reduction=(TARGET-BEST)/(1-BEST),
        caveat='Total assumes route 5 is exactly zero in November; platform score rounding adds uncertainty. Bounds are necessary, not sufficient, and say nothing about an untested future model.')
    (OUT/'budget.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def historical_information():
    from s67_joint_day_net import v7_references, ALL_ROUTES
    rows, concentrations = [], []
    for fold, (a, pred) in v7_references().items():
        y = a['y'].astype(float)
        p = pred.reshape(-1).astype(float)
        dates = pd.Timestamp('2025-01-01') + pd.to_timedelta(a['day'], unit='D')
        frame = pd.DataFrame(dict(date=dates, month=dates.month, route=a['route'],
            kind=a['kind'], hour=np.tile(np.arange(24), len(y)//24)))
        total = y.sum()
        baseline_error = abs(p-y).sum()
        def record(name, values, groups):
            error = abs(values-y).sum()
            rows.append(dict(fold=fold, diagnostic=name, oracle_groups=groups,
                score=1-error/total, gain=(baseline_error-error)/total,
                error_removed_fraction=(baseline_error-error)/baseline_error,
                uses_evaluation_labels=name != 'reference'))
        record('reference', p, 0)
        specifications = {
            'route_month_level':['route','month'],
            'route_month_kind_level':['route','month','kind'],
            'route_month_kind_hour':['route','month','kind','hour'],
            'network_day_level':['date'],
            'route_day_level':['route','date'],
            'network_day_hour':['date','hour'],
        }
        for name, columns in specifications.items():
            code = group_codes(frame, columns)
            adjusted = oracle_scale(y, p, code)
            record(name, adjusted, len(np.unique(code)))
        # Alternating exact L1 fits: persistent route/hour bias and daily shocks.
        for name, groups in {
            'persistent_shape_plus_network_day':[
                ['route','month','kind','hour'], ['date']],
            'persistent_shape_plus_route_day':[
                ['route','month','kind','hour'], ['route','date']],
        }.items():
            codes = [group_codes(frame, cols) for cols in groups]
            adjusted = p.copy()
            for _ in range(8):
                for code in codes:
                    adjusted = oracle_scale(y, adjusted, code)
            record(name, adjusted, sum(len(np.unique(code)) for code in codes))
        # How much perfect knowledge of only the worst days could possibly help.
        errors = abs(p-y).reshape(-1, len(ALL_ROUTES), 24).sum((1,2))
        for n in [1,3,5,10]:
            reduction = np.sort(errors)[-n:].sum()
            rows.append(dict(fold=fold, diagnostic=f'perfect_worst_{n}_days',
                oracle_groups=n, score=1-(baseline_error-reduction)/total,
                gain=reduction/total, error_removed_fraction=reduction/baseline_error,
                uses_evaluation_labels=True))
        frame['absolute_error'] = abs(p-y)
        frame['boardings'] = y
        for grouping in ['route','hour','date']:
            for value, part in frame.groupby(grouping):
                concentrations.append(dict(fold=fold, grouping=grouping, value=str(value),
                    error=float(part.absolute_error.sum()), target=float(part.boardings.sum()),
                    fraction_of_fold_error=float(part.absolute_error.sum()/baseline_error),
                    global_score_cost=float(part.absolute_error.sum()/total)))
        print(fold, 'information diagnostics complete', flush=True)
    result = pd.DataFrame(rows)
    result.to_csv(OUT/'historical_oracles.csv', index=False)
    pd.DataFrame(concentrations).to_csv(OUT/'error_concentration.csv', index=False)
    print(result.pivot(index='diagnostic', columns='fold', values='score').round(6).to_string())


def draw_diagnostics():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    frame = pd.read_csv(OUT/'historical_oracles.csv')
    october = frame[frame.fold == 'B'].set_index('diagnostic')
    names = ['reference','route_month_level','route_day_level',
             'route_month_kind_hour','persistent_shape_plus_route_day']
    labels = ['v7 historical reference','Oracle route-month level',
              'Oracle route-day level','Oracle persistent hourly correction',
              'Oracle hourly correction + route-day level']
    values = october.loc[names,'score'].to_numpy()
    fig, ax = plt.subplots(figsize=(10,4.5))
    ax.barh(labels,values,color=['#547b9c']+['#ad8464']*4)
    ax.axvline(.94,color='#b3261e',linestyle='--',label='Requested score: 0.94')
    ax.set_xlim(.88,.965);ax.invert_yaxis();ax.set_xlabel('Score on October development period')
    for i,value in enumerate(values):
        ax.text(value+.0007,i,f'{value:.5f}',va='center',fontsize=9)
    ax.set_title('What information is missing? Oracle diagnostics, not forecasts',loc='left')
    ax.legend(loc='lower right');ax.spines[['top','right']].set_visible(False)
    fig.text(.02,.01,'Oracles fit known evaluation labels. These results do not establish a leaderboard score.',fontsize=9)
    fig.tight_layout(rect=[0,.04,1,1])
    path=ROOT/'docs/analysis/figures/research_094_information.png'
    fig.savefig(path,dpi=160,bbox_inches='tight');plt.close(fig)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps(prediction_budget(), indent=2), flush=True)
    historical_information()
    draw_diagnostics()
