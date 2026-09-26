"""Causality and forecast invariants of the local neural experiment."""
import importlib.util
import unittest

if importlib.util.find_spec("torch") is None:
    raise unittest.SkipTest("torch is not installed: uv sync --extra fm or analysis/requirements-neural-py312.txt")
import sys
from pathlib import Path
if not (Path(__file__).resolve().parents[1] / "data/neural_training_pack/history.parquet").exists():
    raise unittest.SkipTest("data/neural_training_pack is missing: build it with analysis/s66_next_iteration.py")

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'analysis'))
from s67_joint_day_net import Data, JointDayNet, blend_shape


def test_later_targets_cannot_change_training_or_context():
    data = Data()
    cutoff = 150
    before = data.samples(cutoff)
    context = data.context(cutoff)
    baseline = data.baseline(cutoff, np.arange(cutoff+1, cutoff+10))
    data.y[cutoff+1:] = 1e9
    data.total[cutoff+1:] = 1e9
    data.shape[cutoff+1:] = 1/24
    data.good[cutoff+1:] = True
    after = data.samples(cutoff)
    for key in before:
        np.testing.assert_array_equal(before[key], after[key])
    np.testing.assert_array_equal(context, data.context(cutoff))
    np.testing.assert_array_equal(baseline, data.baseline(cutoff, np.arange(cutoff+1,cutoff+10)))


def test_blend_keeps_daily_sums_closed_hours_and_protected_routes():
    rng = np.random.default_rng(42)
    reference = rng.integers(1, 100, (3,10,24))
    reference[:,:,0:4] = 0
    reference[0,0] = 0
    proposed = rng.random((3,9,24))
    kind = np.ones((3,9), dtype=int)
    result = blend_shape(reference, proposed, kind, .35)
    np.testing.assert_allclose(result.sum(-1),reference.sum(-1))
    np.testing.assert_array_equal(result[reference == 0],0)
    for j in [1,2,9]:  # route 5, non-workday 7 and 50
        np.testing.assert_array_equal(result[:,j],reference[:,j])


def test_network_forward_backward_is_finite_and_joint_profile_normalizes():
    torch.manual_seed(7)
    model = JointDayNet(56*29,31)
    shape, correction = model(torch.randn(2,9,56*29), torch.randn(2,9,31),
                              torch.full((2,9,24),1/24))
    torch.testing.assert_close(shape.sum(-1),torch.ones(2,9))
    (shape[:,:,8].mean()+correction.square().mean()).backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())


def test_packaged_candidate_schema_daily_mass_and_scored_artifacts():
    import hashlib
    import json
    import pandas as pd
    root=Path(__file__).resolve().parents[1]
    anchor=pd.read_csv(root/'forecasts/submission_shape50_v7.csv',sep=';')
    candidate=pd.read_csv(root/'forecasts/submission_joint_day_v8.csv',sep=';')
    pd.testing.assert_frame_equal(anchor[['route','date','hour']],candidate[['route','date','hour']])
    assert len(candidate)==14640 and not candidate.duplicated(['route','date','hour']).any()
    assert candidate.prediction.dtype.kind in 'iu' and (candidate.prediction>=0).all()
    pd.testing.assert_series_equal(anchor.groupby(['route','date']).prediction.sum(),
                                   candidate.groupby(['route','date']).prediction.sum())
    np.testing.assert_array_equal(candidate.loc[anchor.prediction==0,'prediction'],0)
    for row in json.loads((root/'forecasts/leaderboard_results.json').read_text()):
        assert hashlib.sha256((root/'forecasts'/row['file']).read_bytes()).hexdigest()==row['sha256']
