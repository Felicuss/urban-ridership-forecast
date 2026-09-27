import pytest
pytest.importorskip("torch", reason="torch is not installed: uv sync --extra fm")
import numpy as np
import pandas as pd
from s98_joint_scenarios import residual_factor,joint_posterior


def test_future_residuals_do_not_change_factor():
    h=pd.DataFrame([dict(day=d,route=1,hour=t,kind=0,origin=0,p=100.,y=100+d*(t+1)) for d in range(10) for t in range(3)])
    f,info=residual_factor(h,5,[(1,t) for t in range(3)])
    h.loc[h.day>=5,'y']=1e9
    other,_=residual_factor(h,5,[(1,t) for t in range(3)])
    np.testing.assert_array_equal(f,other)
    assert info['last_training_day']==4


def test_joint_posterior_preserves_zero_and_responds_to_total():
    anchor=np.array([0.,100.,150.,0.,100.,150.]);pool=np.array([anchor,anchor*1.1])
    y=np.array([0.,110.,160.,0.,90.,140.]);total=y.sum()
    scores=1-abs(pool-y).sum(1)/total
    pred,meta=joint_posterior(anchor,pool,scores,np.ones((1,6)),np.array([total]),total,np.ones(6),np.eye(3),scenarios=256)
    assert np.isfinite(pred).all() and (pred>=0).all()
    np.testing.assert_array_equal(pred[[0,3]],0)
    assert abs(pred.sum()-total)<1
    assert meta['score_rmse']<.001


def test_whitening_preserves_solution():
    anchor=np.array([20.,100.,150.,20.,100.,150.]);pool=np.array([anchor,anchor*1.1])
    y=np.array([20.,110.,160.,20.,90.,140.]);total=y.sum();scores=1-abs(pool-y).sum(1)/total
    args=(anchor,pool,scores,np.ones((1,6)),np.array([total]),total,np.ones(6),np.eye(3))
    first,_=joint_posterior(*args,scenarios=256)
    second,_=joint_posterior(*args,scenarios=256,whiten=True)
    np.testing.assert_allclose(first,second,atol=.01)
