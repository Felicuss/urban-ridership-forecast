import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s93_entropy_scores import prior_grid,posterior


@pytest.mark.parametrize('family',['normal','student3','mixture'])
def test_prior_family_probabilities_and_error_calibration(family):
    anchor=np.array([0.,100.,500.,1000.])
    values,p,_=prior_grid(anchor,150.,distribution=family)
    assert (p>0).all()
    np.testing.assert_allclose(p.sum(),1)
    np.testing.assert_allclose(np.einsum('nk,k->',abs(values-anchor[:,None]),p),150,atol=1e-6)
    np.testing.assert_array_equal(values[0],0)


def test_prior_calibrates_expected_error_and_preserves_zero():
    anchor=np.array([0.,10.,100.,1000.])
    values,probability,_=prior_grid(anchor,100.)
    np.testing.assert_allclose(probability.sum(),1)
    np.testing.assert_allclose(np.einsum('nk,k->',abs(values-anchor[:,None]),probability),100,atol=1e-6)
    np.testing.assert_array_equal(values[0],0)
    assert (values>=0).all() and (np.diff(values,axis=1)>=0).all()


def test_posterior_uses_score_feedback_and_has_finite_outputs():
    anchor=np.array([100.,100.,100.,100.]);truth=np.array([110.,90.,115.,85.])
    pool=np.array([anchor,[110,90,110,90],[90,110,90,110]],float)
    scores=1-abs(pool-truth).sum(1)/400
    output,meta=posterior(anchor,pool,scores,np.ones((1,4)),np.array([400.]),400,maxiter=300,queries=pool)
    assert all(np.isfinite(p).all() and (p>=0).all() for p in output.values())
    assert output['mean'][0]>output['mean'][1]
    assert meta['score_rmse']<.002
    np.testing.assert_allclose(meta['query_scores'],meta['fitted_scores'])
