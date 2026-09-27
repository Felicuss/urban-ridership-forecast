import pytest
pytest.importorskip("torch", reason="torch is not installed: uv sync --extra fm")
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s96_asymmetric_entropy import asymmetry
from s93_entropy_scores import prior_grid


def test_asymmetry_learns_direction_without_future_labels():
    days=np.repeat(np.arange(120,200),24);hours=np.tile(np.arange(24),80)
    frame=pd.DataFrame(dict(day=days,hour=hours,route=17,kind=0,origin=100,p=100.,
        y=100+np.where(hours<12,20.,-20.)))
    args=(170,np.full(24,17),np.zeros(24,int),np.arange(24))
    expected,meta=asymmetry(frame,*args)
    assert expected[:12].mean()>0 and expected[12:].mean()<0
    frame.loc[frame.day>=170,'y']=1e9
    result,_=asymmetry(frame,*args)
    np.testing.assert_array_equal(result,expected)
    assert meta['last_training_day']==169


def test_skewed_prior_keeps_calibration_and_sorted_support():
    anchor=np.array([0.,100.,500.,1000.])
    values,p,_=prior_grid(anchor,150.,np.ones(4),np.array([0,.3,-.3,.15]))
    np.testing.assert_allclose(np.einsum('nk,k->',abs(values-anchor[:,None]),p),150,atol=1e-6)
    assert (np.diff(values,axis=1)>=0).all()
    np.testing.assert_array_equal(values[0],0)


def test_zero_skew_replays_existing_prior_exactly():
    anchor=np.array([0.,100.,500.,1000.])
    original=prior_grid(anchor,150.,np.ones(4))
    explicit=prior_grid(anchor,150.,np.ones(4),np.zeros(4))
    for x,y in zip(original,explicit):np.testing.assert_array_equal(x,y)
