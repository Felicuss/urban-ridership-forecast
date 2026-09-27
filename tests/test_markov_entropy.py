import pytest
pytest.importorskip("torch", reason="torch is not installed: uv sync --extra fm")
import numpy as np
from s100_markov_entropy import chain_posterior
from s93_entropy_scores import posterior


def test_singleton_chain_matches_independent_inference():
    anchor=np.array([0.,100.,150.,0.,100.,150.]);pool=np.array([anchor,anchor*1.1])
    y=np.array([0.,110.,160.,0.,90.,140.]);total=y.sum()
    scores=1-abs(pool-y).sum(1)/total;A=np.ones((1,6));b=np.array([total])
    first,_=posterior(anchor,pool,scores,A,b,total,distribution='mixture',penalty=1e-10)
    second,meta=chain_posterior(anchor,pool,scores,A,b,total,np.ones(6),np.eye(6),block=1)
    np.testing.assert_allclose(first['mean'],second,atol=.03)
    assert meta['score_rmse']<1e-6
    np.testing.assert_array_equal(second[[0,3]],0)


def test_correlated_chain_respects_margins():
    anchor=np.array([20.,100.,150.,20.,100.,150.]);pool=np.array([anchor,anchor*1.1])
    y=np.array([20.,110.,160.,20.,90.,140.]);total=y.sum()
    scores=1-abs(pool-y).sum(1)/total
    p,meta=chain_posterior(anchor,pool,scores,np.ones((1,6)),np.array([total]),total,np.ones(6),np.ones((6,1)),block=3,strength=.6)
    assert np.isfinite(p).all() and (p>=0).all()
    assert abs(p.sum()-total)<.1
    assert meta['score_rmse']<1e-6
