"""Causal daily fitting and volume-constrained deployment regression tests."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'))
from s72_graph_regime_moe import RegimeData
from s82_daily_seasonal_level import forecast
from s83_package_seasonal_daily_v11 import constrained_daily_round
from s52_round4_common import future_arrays, DATES
from s64_package_shape_facts import protected_cells


def test_daily_fit_ignores_future_and_excluded_targets():
    data=RegimeData();cutoff=242;dates=np.arange(243,250)
    expected=forecast(data,cutoff,dates,harmonics=2,penalty=40)
    data.total[cutoff+1:]=1e10
    data.good[cutoff+1:]=True
    data.total[:cutoff+1][~data.good[:cutoff+1]]=1e10
    actual=forecast(data,cutoff,dates,harmonics=2,penalty=40)
    np.testing.assert_array_equal(expected,actual)
    assert np.isfinite(actual).all() and (actual>0).all()


def test_daily_round_preserves_groups_and_protected_days():
    before=np.array([100,101,102,0,12,45,18,9])
    proposed=np.array([130.,40.,99.,0.,200.,20.,1.,12.])
    groups=np.array([0,0,0,1,2,2,3,3])
    protected=np.array([False,True,False,True,True,True,False,False])
    result=constrained_daily_round(before,proposed,groups,protected)
    for group in np.unique(groups):
        assert result[groups==group].sum()==before[groups==group].sum()
    np.testing.assert_array_equal(result[protected],before[protected])
    assert (result>=0).all() and result.dtype.kind in 'iu'
    assert not np.array_equal(result,before)


def test_v11_preserves_monthly_constraints_and_calendar_rules():
    old=pd.read_csv(ROOT/'forecasts/submission_seasonal_v10.csv',sep=';',parse_dates=['date'])
    new=pd.read_csv(ROOT/'forecasts/submission_seasonal_daily_v11.csv',sep=';',parse_dates=['date'])
    assert len(new)==14640 and new[['date','route','hour']].equals(old[['date','route','hour']])
    a=future_arrays()
    grid=pd.DataFrame(dict(date=DATES[a['day']],route=a['route'],hour=np.tile(np.arange(24),610),kind=a['kind'],protected=protected_cells(a)))
    before=grid.merge(old,on=['date','route','hour'],validate='one_to_one')
    after=grid.merge(new,on=['date','route','hour'],validate='one_to_one')
    before['month']=before.date.dt.month;after['month']=after.date.dt.month
    pd.testing.assert_series_equal(before.groupby(['route','month','kind']).prediction.sum(),after.groupby(['route','month','kind']).prediction.sum())
    np.testing.assert_array_equal(after.loc[before.prediction==0,'prediction'],0)
    pd.testing.assert_series_equal(after.loc[after.protected,'prediction'],before.loc[before.protected,'prediction'])
    mask=after.date==pd.Timestamp('2025-12-31')
    pd.testing.assert_series_equal(after[mask].groupby('route').prediction.sum(),before[mask].groupby('route').prediction.sum())
    assert (new.loc[(new.date==pd.Timestamp('2025-12-31'))&(new.hour>=20),'prediction']==0).all()
    assert new.prediction.dtype.kind in 'iu' and (new.prediction>=0).all()
    assert new.prediction.sum()==old.prediction.sum()
