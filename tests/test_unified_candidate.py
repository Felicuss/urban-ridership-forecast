"""Checks for history boundaries and horizon-dependent ensemble arithmetic."""
import unittest

import numpy as np

from s42_adaptive_profiles import Experiment
from s47_unified_candidate import reliability_features, combine


class UnifiedCandidateChecks(unittest.TestCase):
    def test_reliability_features_ignore_targets_after_origin(self):
        exp=Experiment()
        days=np.arange(151,158)
        before=reliability_features(exp,150,days)
        exp.y[151:]=999999
        after=reliability_features(exp,150,days)
        np.testing.assert_array_equal(before.to_numpy(),after.to_numpy())

    def test_horizon_blend_changes_only_after_day_30(self):
        a=dict(base=np.full(4,100.),old=np.full(4,120.),rich=np.full(4,140.),
               direct=np.full(4,160.),horizon=np.array([1,30,31,61]))
        cfg=dict(old=.5,rich=.5,direct=0.,near=.25,far=.5)
        np.testing.assert_allclose(combine(a,cfg),[107.5,107.5,115.,115.])


if __name__=='__main__':
    unittest.main()
