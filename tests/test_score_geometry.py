import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s92_score_geometry import expected_absolute,directions,solve


def test_laplace_expected_absolute_matches_sampling():
    rng=np.random.default_rng(4)
    noise=rng.laplace(0,2,300000)
    for offset in [0,1,5]:
        formula=float(expected_absolute(torch.tensor(float(offset)),torch.tensor(2.)))
        assert abs(formula-np.abs(noise+offset).mean())<.02


def test_score_directions_preserve_overlapping_aggregates_and_zero_support():
    anchor=np.array([0.,10.,20.,30.,40.])
    pool=anchor+np.random.default_rng(2).normal(0,2,(8,5))
    A=np.array([[1,1,1,1,1],[0,1,1,0,0]],float)
    basis,_=directions(anchor,pool,A,4)
    np.testing.assert_allclose(A@basis,0,atol=1e-8)
    np.testing.assert_array_equal(basis[0],0)


def test_score_feedback_moves_toward_better_direction():
    anchor=np.array([100.,100.]);pool=np.array([[100,100],[90,110],[110,90],[115,85]],float)
    truth=np.array([120.,80.]);scores=1-abs(pool-truth).sum(1)/200
    result,meta=solve(anchor,pool,scores,np.ones((1,2)),np.array([200.]),200,2,1,steps=250)
    assert abs(result-truth).sum()<abs(anchor-truth).sum()
    np.testing.assert_allclose(result.sum(),200,atol=1e-6)
    assert np.isfinite(meta['fit_rmse'])


def test_anchor_calibration_reproduces_observed_reference_score():
    anchor=np.array([100.,100.]);pool=np.array([[100,100],[90,110],[110,90],[115,85]],float)
    center=torch.tensor([110.,90.]);noise=torch.tensor([10.,10.])
    scores=(1-expected_absolute(center[None]-torch.tensor(pool),noise[None]).sum(1)/200).numpy()
    _,meta=solve(anchor,pool,scores,np.ones((1,2)),np.array([200.]),200,2,10,steps=150,calibrate_anchor=True)
    assert abs(meta['fitted_scores'][0]-scores[0])<1e-5
