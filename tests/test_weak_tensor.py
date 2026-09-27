import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
import s91_weak_supervised_tensor as module


def test_cyclic_spline_is_periodic_partition():
    for knots in [6,12]:
        basis=module.cyclic_basis(np.arange(365),knots)
        assert (basis>=0).all()
        np.testing.assert_allclose(basis.sum(1),1,atol=1e-6)
        np.testing.assert_allclose(module.cyclic_basis([0,365],knots)[0],module.cyclic_basis([0,365],knots)[1])


def test_aggregate_supervision_reaches_model_weights():
    model=module.TensorField(6,2)
    pred=model(torch.tensor(module.cyclic_basis([330,331],6)),torch.zeros(2,2),
        torch.zeros(2,dtype=torch.long),torch.zeros(2,dtype=torch.long),torch.ones(2,9,24))
    loss=(pred.sum()-500)**2;loss.backward()
    assert model.season.grad.abs().sum()>0 and torch.isfinite(model.season.grad).all()


def test_fit_ignores_individual_future_labels(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'OUT',tmp_path)
    data=SimpleNamespace(y=np.full((365,9,24),10,dtype='float32'),
        kind=np.zeros((365,9),int),dow=np.zeros((365,9),int),
        cov=np.zeros((365,9,30),dtype='float32'),good=np.ones((365,9),bool))
    days=np.array([20,21]);anchor=np.full(480,10.)
    A=np.ones((1,480));b=np.array([4900.])
    p,_=module.fit(data,19,days,anchor,A,b,6,1,'first',steps=10)
    data.y[20:]=1e8
    q,_=module.fit(data,19,days,anchor,A,b,6,1,'second',steps=10)
    np.testing.assert_array_equal(p,q)
