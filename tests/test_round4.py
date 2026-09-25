"""Guard target-date leakage in selection and daily/regime feature construction."""
import unittest
import numpy as np
import pandas as pd
from s52_round4_common import prior_blocks
from s42_adaptive_profiles import Experiment
from s44_residual_learner import Features
from s47_unified_candidate import make_frame
from s55_daily_level import daily_frame,regimes
from s56_regime_weekends import normal_profiles


class Round4Checks(unittest.TestCase):
    def test_partial_overlap_is_excluded(self):
        arrays={'old':{'day':np.array([20,39])},'overlap':{'day':np.array([35,45])},
                'touches':{'day':np.array([30,40])},'future':{'day':np.array([50,70])}}
        kept=prior_blocks(arrays,{'day':np.array([40,60])})
        self.assertEqual(list(kept),['old'])

    def test_daily_features_do_not_read_future_labels(self):
        exp=Experiment();o=150;days=np.arange(151,154);state=regimes(exp)
        first=daily_frame(make_frame(Features(exp),exp,o,days),exp,state)
        exp.y[o+1:]=999999
        second=daily_frame(make_frame(Features(exp),exp,o,days),exp,state)
        excluded=['optimal_scale','daily_sum']
        pd.testing.assert_frame_equal(first.drop(columns=excluded),second.drop(columns=excluded))

    def test_restored_profiles_do_not_read_future_labels(self):
        exp=Experiment();state=regimes(exp)
        before,_=normal_profiles(exp,state,150)
        exp.y[151:]=999999
        after,_=normal_profiles(exp,state,150)
        self.assertTrue(before)
        self.assertEqual(before.keys(),after.keys())
        for key in before:np.testing.assert_array_equal(before[key],after[key])


if __name__=='__main__':unittest.main()
