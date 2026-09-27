import numpy as np
import pandas as pd
from s112_daily_copula import correlation, scenario_posterior
from s93_entropy_scores import prior_grid


def test_daily_correlations_ignore_future_labels_and_are_psd():
    n=20*24
    frame=pd.DataFrame(dict(day=np.repeat(np.arange(20),24),route=1,
        hour=np.tile(np.arange(24),20),origin=-1,kind=0,p=100.,
        y=100+np.random.default_rng(42).normal(size=n)*10))
    a,meta=correlation(frame,15,[1])
    frame.loc[frame.day>=15,'y']=1e9
    b,_=correlation(frame,15,[1])
    np.testing.assert_array_equal(a,b)
    np.testing.assert_allclose(np.diag(a),1)
    assert np.linalg.eigvalsh(a).min()>-1e-10
    assert meta['last_training_day']==14


def test_scenario_conditioning_preserves_structural_zero_and_is_deterministic():
    anchor=np.array([0.,100.,200.,300.]);total=600.
    support,prior,_=prior_grid(anchor,60.)
    pool=np.array([anchor]);scores=np.array([.9]);A=np.ones((1,4));b=np.array([total])
    corr=np.array([[1.,.4],[.4,1.]])
    args=(anchor,pool,scores,A,b,total,support,prior,corr)
    first,meta=scenario_posterior(*args,samples=128)
    second,_=scenario_posterior(*args,samples=128)
    np.testing.assert_array_equal(first,second)
    assert first[0]==0 and np.isfinite(first).all() and (first>=0).all()
    assert meta['score_rmse']<1e-5
