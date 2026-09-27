import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s87_reconciliation_pilot import projection, prior_variance


def test_nonnegative_projection_and_structural_zero():
    p=np.array([1.,4.,0.]);A=np.ones((1,3));variance=np.ones(3)
    np.testing.assert_allclose(projection(p,A,np.array([10.]),variance),[3.5,6.5,0],atol=1e-7)
    np.testing.assert_allclose(projection(p,A,np.array([2.]),variance),[0,2,0],atol=1e-7)


def test_dependent_constraints_are_supported():
    p=np.array([1.,4.,0.]);A=np.array([[1,1,1],[2,2,2]],float)
    result=projection(p,A,np.array([10.,20.]),np.ones(3))
    np.testing.assert_allclose(A@result,[10.,20.],atol=1e-7)


def test_later_residuals_cannot_enter_variance():
    n=24*240
    frame=pd.DataFrame(dict(day=np.repeat(np.arange(24),240),origin=-1,
        route=np.tile(np.repeat(np.arange(10),24),24),hour=np.tile(np.arange(24),240),
        y=np.full(n,102.),p=np.full(n,100.)))
    a={'route':np.repeat(np.arange(10),24)};p=np.full(240,100.)
    expected=prior_variance(frame,22,a,p)
    frame.loc[frame.day>=22,'y']=1e10
    np.testing.assert_array_equal(prior_variance(frame,22,a,p),expected)
