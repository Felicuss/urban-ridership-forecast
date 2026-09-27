import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s88_factor_reconciliation import conditioned, learn_basis
from s89_route17_probes import decode_sum, make_probe, balanced_round


def test_rounding_overlapping_groups_preserves_total_and_zeros():
    values=np.array([0.,1.49,1.49,2.49,2.49,3.49])
    masks=[np.ones(6,bool),np.array([1,1,1,0,0,0],bool),np.array([0,0,1,1,0,0],bool)]
    cons=[(m,values[m].sum(),str(i)) for i,m in enumerate(masks)]
    result=balanced_round(values,cons)
    assert result[0]==0 and result.sum()==round(values.sum())
    assert np.all(abs(result-values)<1)
    for m,t,_ in cons:assert abs(result[m].sum()-t)<2


def test_factor_conditioning_matches_dense_covariance():
    p=np.array([100.,100.,100.])
    a=np.array([[1.,1.,0.]])
    b=np.array([210.])
    u=np.array([[1.,2.],[3.,1.],[2.,4.]])
    covariance=np.diag(p+1)+u@u.T
    expected=p+covariance@a.T@np.linalg.solve(a@covariance@a.T,b-a@p)
    np.testing.assert_allclose(conditioned(p,a,b,u,1),expected,atol=1e-8)


def test_basis_excludes_future_dates():
    n=35*240
    h=pd.DataFrame(dict(day=np.repeat(np.arange(35),240),
        route=np.tile(np.repeat([1,5,7,11,12,17,25,26,28,50],24),35),
        hour=np.tile(np.arange(24),350),kind=0,origin=-1,p=100.,
        y=100+np.random.default_rng(42).normal(size=n)))
    basis,_=learn_basis(h,30)
    h.loc[h.day>=30,'y']=1e9
    again,meta=learn_basis(h,30)
    np.testing.assert_array_equal(basis,again)
    assert meta['last_training_day']==29


def test_probe_decoding_and_ceiling_violation():
    y=np.array([10.,20.,30.,40.]);total=y.sum()
    # Carrier occupies the last two cells; target is the first two.
    carrier=np.array([0.,0.,40.,50.])
    sc=1-abs(y-carrier).sum()/total
    probe=carrier.copy();probe[:2]=[15,25]
    score=1-abs(y-probe).sum()/total
    assert decode_sum(40,score,sc,total)==pytest.approx(30)
    probe[0]=5
    score=1-abs(y-probe).sum()/total
    assert decode_sum(30,score,sc,total)==pytest.approx(25)
    with pytest.raises(ValueError):decode_sum(40,0,sc,total)


def test_opposite_carrier_alignment_and_overlap():
    g=pd.DataFrame(dict(route=[17,17],date=['2025-11-03','2025-12-01'],hour=[7,7],
        month=[11,12],kind=['wd','wd']))
    carrier=g[['route','date','hour']].assign(prediction=[0,100]).iloc[::-1]
    p,m=make_probe(g,np.array([30,40]),{'months':[11]},carrier,{'months':[12]})
    np.testing.assert_array_equal(p,[75,100])
    with pytest.raises(ValueError):
        make_probe(g,np.array([30,40]),{'months':[12]},carrier,{'months':[12]})
