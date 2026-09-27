import pytest
pytest.importorskip("torch", reason="torch is not installed: uv sync --extra fm")
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s90_memory_transport import MemoryMetric,memory_profile,joint_values


def test_memory_excludes_future_donors_and_bad_route_days():
    torch.manual_seed(4)
    model=MemoryMetric(3);x=torch.randn(12,3)
    logits=model(x,torch.tensor([10]),torch.tensor([5]))
    profiles=torch.rand(12,2,24);profiles/=profiles.sum(-1,keepdim=True)
    quality=torch.ones(12,2,dtype=torch.bool);quality[2,0]=False
    expected,weights=memory_profile(logits,profiles,quality)
    assert torch.all(weights[:,6:]==0) and weights[0,2,0]==0
    altered=profiles.clone();altered[6:]=1e6;altered[2,0]=1e6
    result,_=memory_profile(logits,altered,quality)
    torch.testing.assert_close(result,expected)
    torch.testing.assert_close(result.sum(-1),torch.ones(1,2))


def test_causal_level_detrending_ignores_later_counts():
    data=SimpleNamespace(total=np.full((365,9),1000,dtype='float32'),
        good=np.ones((365,9),bool),kind=np.zeros((365,9),int),
        shape=np.ones((365,9,24),dtype='float32')/24)
    before=joint_values(data)
    data.total[150:]=1e9
    after=joint_values(data)
    np.testing.assert_array_equal(before[:150],after[:150])
    assert np.isfinite(after).all()


def test_memory_metric_has_finite_training_gradients():
    torch.manual_seed(3)
    model=MemoryMetric(4)
    x=torch.randn(20,4)
    profile=torch.rand(20,2,24);profile/=profile.sum(-1,keepdim=True)
    pred,_=memory_profile(model(x,torch.tensor([15,18]),torch.tensor([8,10])),
        profile,torch.ones(20,2,dtype=torch.bool))
    loss=(pred-profile[[15,18]]).abs().sum();loss.backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
