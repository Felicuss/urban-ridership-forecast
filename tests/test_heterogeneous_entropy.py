import pytest
pytest.importorskip("torch", reason="torch is not installed: uv sync --extra fm")
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s95_heterogeneous_entropy import uncertainty
from s93_entropy_scores import prior_grid


def test_uncertainty_excludes_future_residuals():
    days=np.repeat(np.arange(120,200),24)
    hours=np.tile(np.arange(24),80)
    error=np.where(hours<12,5.,30.)*np.where(days%2,1.,-1.)
    frame=pd.DataFrame(dict(day=days,hour=hours,route=17,kind=0,origin=100,p=100.,y=100+error))
    args=(170,np.full(24,17),np.zeros(24,int),np.arange(24))
    expected,meta=uncertainty(frame,*args)
    frame.loc[frame.day>=170,'y']=1e9
    again,_=uncertainty(frame,*args)
    np.testing.assert_array_equal(again,expected)
    assert meta['last_training_day']==169
    assert expected[:12].mean()<expected[12:].mean()
    assert np.all((expected>=.5)&(expected<=2))


def test_heterogeneous_prior_keeps_total_error_calibration():
    anchor=np.array([0.,100.,500.,1000.])
    support,p,_=prior_grid(anchor,150.,np.array([1.,2.,.5,1.2]))
    np.testing.assert_allclose(np.einsum('nk,k->',abs(support-anchor[:,None]),p),150,atol=1e-6)
    np.testing.assert_array_equal(support[0],0)
