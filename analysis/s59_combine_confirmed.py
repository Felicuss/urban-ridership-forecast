"""Combine disjoint, scored improvements without training or changing source CSVs."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KEYS = ['route', 'date', 'hour']


def main():
    directory = ROOT / 'forecasts'
    names = ['submission_kaggle_unified_v2.csv',
             'round4/submit/05_daily_optimal_25.csv',
             'round4/submit/03_route5_weekly_fact.csv']
    registry = json.loads((directory / 'leaderboard_results.json').read_text())
    sources, frames = [], []
    for name in names:
        path = directory / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        matches = [r for r in registry if r['sha256'] == digest and r.get('leaderboard_score') is not None]
        assert matches, f'Missing confirmed score: {name}'
        assert len({r['leaderboard_score'] for r in matches}) == 1
        sources.append(dict(file=name, sha256=digest, score=matches[0]['leaderboard_score']))
        frames.append(pd.read_csv(path, sep=';'))
    base, daily, route5 = frames
    for frame in frames:
        assert len(frame) == 14640 and not frame.duplicated(KEYS).any()
        assert frame[KEYS].equals(base[KEYS])
        assert frame.prediction.dtype.kind in 'iu' and (frame.prediction >= 0).all()
    changed_daily = daily.prediction != base.prediction
    changed_route5 = route5.prediction != base.prediction
    assert not (changed_daily & changed_route5).any(), 'Score addition requires disjoint changes'
    assert not changed_daily[base.route == 5].any()
    assert not changed_route5[base.route != 5].any()
    assert all(s['score'] > sources[0]['score'] for s in sources[1:])
    combined = daily.copy()
    combined.loc[changed_route5, 'prediction'] = route5.loc[changed_route5, 'prediction']
    assert (combined.prediction >= 0).all()
    assert (combined.loc[(combined.date == '2025-12-31') & (combined.hour >= 20), 'prediction'] == 0).all()
    assert (combined.loc[(combined.route == 5) & ((combined.date < '2025-12-16') |
            ((combined.date == '2025-12-16') & (combined.hour < 18))), 'prediction'] == 0).all()
    # Cellwise L1 additivity is independent of unknown labels. Check several synthetic targets.
    for seed in range(3):
        y = np.random.default_rng(seed).integers(0, 4000, len(base))
        loss = lambda f: np.abs(y - f.prediction.to_numpy()).sum()
        assert loss(combined) == loss(daily) + loss(route5) - loss(base)
    path = directory / 'submission_daily_route5_v4.csv'
    combined.to_csv(path, sep=';', index=False)
    implied = round(sources[1]['score'] + sources[2]['score'] - sources[0]['score'], 8)
    metadata = dict(file=path.name, status='unscored', leaderboard_score=None,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), sources=sources,
        method='Daily correction on old routes plus the isolated route 5 weekly-total correction',
        changed_daily_cells=int(changed_daily.sum()), changed_route5_cells=int(changed_route5.sum()),
        overlap_cells=0, changed_total_cells=int((combined.prediction != base.prediction).sum()),
        implied_score=implied, implied_score_interval=[round(implied-0.000015,8), round(implied+0.000015,8)],
        derivation='S(combined) = S(daily) + S(route5) - S(v2): cellwise L1 errors add on disjoint supports.',
        assumptions='Same full target and global WAPE denominator; scores rounded to 5 decimals; no score clipping active.',
        caveat='Implied score is not a measured leaderboard result. Source CSVs are preserved.')
    for result in registry:
        if result['sha256'] == metadata['sha256'] and result.get('leaderboard_score') is not None:
            metadata.update(status='scored', leaderboard_score=result['leaderboard_score'],
                            evidence=result.get('evidence'),
                            caveat='Implied score is derived separately; leaderboard_score is the user-reported result. Source CSVs are preserved.')
    path.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
