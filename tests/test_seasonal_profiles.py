"""Causality, normalization and deployed artifact invariants for v10."""
import importlib.util
import unittest

if importlib.util.find_spec("torch") is None:
    raise unittest.SkipTest("torch is not installed: uv sync --extra fm or analysis/requirements-neural-py312.txt")
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'))
from s67_joint_day_net import Data
from s80_seasonal_profiles import smooth


def test_targets_after_cutoff_cannot_change_profile():
    data = Data()
    cutoff = 119
    dates = np.arange(120,125)
    before = smooth(data,cutoff,dates,harmonics=1,penalty=40)
    data.shape[cutoff+1:] = np.random.default_rng(12).uniform(0,1,data.shape[cutoff+1:].shape)
    data.total[cutoff+1:] = 1e9
    data.good[cutoff+1:] = True
    after = smooth(data,cutoff,dates,harmonics=1,penalty=40)
    np.testing.assert_array_equal(before,after)
    np.testing.assert_allclose(before.sum(-1),1,atol=1e-12)
    assert np.isfinite(before).all() and (before>=0).all()


def test_excluded_corrupt_history_cannot_change_profile():
    data = Data()
    dates = np.arange(304,307)
    before = smooth(data,303,dates,harmonics=2,penalty=40)
    bad = ~data.good[:304]
    data.shape[:304][bad] = 1e6
    data.total[:304][bad] = 1e9
    after = smooth(data,303,dates,harmonics=2,penalty=40)
    np.testing.assert_array_equal(before,after)


def test_v10_preserves_daily_totals_and_fare_rules():
    old = pd.read_csv(ROOT/'forecasts/submission_shape50_v7.csv',sep=';')
    new = pd.read_csv(ROOT/'forecasts/submission_seasonal_v10.csv',sep=';')
    assert len(new)==14640
    assert new[['route','date','hour']].equals(old[['route','date','hour']])
    pd.testing.assert_series_equal(new.groupby(['route','date']).prediction.sum(),old.groupby(['route','date']).prediction.sum())
    np.testing.assert_array_equal(new.loc[old.prediction==0,'prediction'],0)
    pd.testing.assert_series_equal(new.loc[new.route==5,'prediction'],old.loc[old.route==5,'prediction'])
    assert (new.loc[(new.date=='2025-12-31')&(new.hour>=20),'prediction']==0).all()
    assert new.prediction.dtype.kind in 'iu' and (new.prediction>=0).all()
