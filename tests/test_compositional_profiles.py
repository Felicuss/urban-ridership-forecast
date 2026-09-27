import numpy as np
from scipy.special import softmax
from s118_compositional_profiles import objective_arrays, causal_prior


def test_joint_gradient_matches_finite_differences():
    rng=np.random.default_rng(42);raw=rng.normal(size=48);truth=softmax(rng.normal(size=(2,24)),axis=1).reshape(-1)
    weights=np.repeat([.7,1.3],24)
    for mode in ['cross_entropy','smooth_l1']:
        grad,hess=objective_arrays(raw,truth,weights,mode)
        def loss(z):
            p=softmax(z.reshape(-1,24),axis=1).reshape(-1)
            if mode=='cross_entropy':return -(weights*truth*np.log(p)).sum()
            return (weights*np.sqrt((p-truth)**2+.003**2)).sum()
        for i in [0,7,23,24,47]:
            delta=np.zeros(48);delta[i]=1e-6
            expected=(loss(raw+delta)-loss(raw-delta))/2e-6
            np.testing.assert_allclose(grad[i],expected,atol=1e-7)
        assert np.isfinite(hess).all() and (hess>0).all()
        np.testing.assert_allclose(grad.reshape(-1,24).sum(1),0,atol=1e-12)


def test_causal_profile_does_not_read_future_counts():
    class Data:pass
    data=Data();rng=np.random.default_rng(42)
    data.shape=softmax(rng.normal(size=(50,9,24)),axis=2)
    data.good=np.ones((50,9),bool);data.kind=np.zeros((50,9),int);data.dow=np.arange(50)[:,None]%7+np.zeros((50,9),int)
    first=causal_prior(data,40,30)
    data.shape[30:]=999
    second=causal_prior(data,40,30)
    np.testing.assert_array_equal(first,second)
    np.testing.assert_allclose(first.sum(1),1)


def test_profile_transfer_keeps_daily_totals_and_structural_zeros():
    import pandas as pd
    from s119_profile_transfer import transfer
    from s67_joint_day_net import ALL_ROUTES
    rng=np.random.default_rng(8)
    current=rng.integers(10,100,size=(2,10,24));current[:,:,2:5]=0
    prior=softmax(rng.normal(size=(2,9,24)),axis=2)
    shares=softmax(rng.normal(size=(2,9,24)),axis=2)
    target=pd.DataFrame(dict(route=np.tile(np.repeat(ALL_ROUTES,24),2),kind=1))
    result=transfer(current.reshape(-1),shares,prior,target,.25).reshape(current.shape)
    np.testing.assert_allclose(result.sum(2),current.sum(2),atol=1e-10)
    np.testing.assert_array_equal(result[current==0],0)
    for route in [5,7,50]:
        j=ALL_ROUTES.index(route);np.testing.assert_array_equal(result[:,j],current[:,j])
