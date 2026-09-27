import numpy as np
import pandas as pd
from s106_distributional_noise import learn,FEATURES


def test_noise_training_excludes_future_labels():
    rng=np.random.default_rng(42)
    n=40*24
    history=pd.DataFrame(dict(day=np.repeat(np.arange(120,160),24),route=np.ones(n,dtype=int),hour=np.tile(np.arange(24),40),kind=np.zeros(n,dtype=int),p=np.tile(np.arange(24)*30+100,40),origin=np.repeat(np.arange(120,160)-1,24)))
    history['y']=np.maximum(0,history.p+rng.normal(size=n)*(.1*history.p+5))
    cov=history[['day','route','hour']].copy()
    for f in FEATURES:
        if f not in cov and f not in ['kind','log_level']:cov[f]=0
    cov['dow']=cov.day%7
    cov['date']=pd.Timestamp('2025-01-01')+pd.to_timedelta(cov.day,unit='D')
    target=history[history.day>=155]
    first,_,info=learn(history,cov,150,target)
    history.loc[history.day>=150,'y']=1e8
    second,_,other=learn(history,cov,150,target)
    np.testing.assert_array_equal(first,second)
    assert info['last_training_day']==149 and info['training_days']==30
    assert np.isfinite(first).all() and (first>=.5).all() and (first<=2).all()


def test_ceiling_probe_measures_clipped_sum():
    y=np.array([10.,30.,100.]);h=np.array([20.,40.,50.])
    s=1-abs(y-h).sum()/y.sum()
    measured=(h.sum()+s*y.sum())/2
    assert measured==np.minimum(y,h).sum()
    assert y.sum()-measured==np.maximum(y-h,0).sum()
