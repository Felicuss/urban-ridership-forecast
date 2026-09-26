import importlib.util
import unittest

if importlib.util.find_spec("torch") is None:
    raise unittest.SkipTest("torch is not installed: uv sync --extra fm or analysis/requirements-neural-py312.txt")
import sys
from pathlib import Path
if not (Path(__file__).resolve().parents[1] / "data/neural_training_pack/history.parquet").exists():
    raise unittest.SkipTest("data/neural_training_pack is missing: build it with analysis/s66_next_iteration.py")
import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis'))
from s72_graph_regime_moe import RegimeData,RegimeGraphNet
from s75_temporal_stacker import reconcile,fit_weights,apply_stack


def test_causal_experts_and_context_ignore_later_targets():
    data=RegimeData();origin=150;dates=np.array([151,160,170])
    context,scale=data.origin_features(origin)
    before=data.experts(origin,dates)
    data.y[origin+1:]=1e9;data.total[origin+1:]=1e9
    data.shape[origin+1:]=1/24;data.good[origin+1:]=True
    after=data.experts(origin,dates)
    np.testing.assert_array_equal(before,after)
    other,other_scale=data.origin_features(origin)
    np.testing.assert_array_equal(context,other)
    np.testing.assert_array_equal(scale,other_scale)


def test_joint_graph_gradients_and_positive_forecast():
    model=RegimeGraphNet(56*30,33)
    prediction,gate,_,_=model(torch.randn(2,9,56*30),torch.randn(2,9,33),
                              torch.rand(2,9,6,24)*100,torch.full((2,9),2000.))
    prediction.mean().backward()
    torch.testing.assert_close(gate.sum(-1),torch.ones(2,9))
    assert (prediction>=0).all() and torch.isfinite(prediction).all()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())


def test_reconciliation_preserves_protected_cells_and_hits_small_constraints():
    pred=np.full((4,10,24),100.)
    pred[:,:,0:4]=0
    kind=np.zeros_like(pred,dtype=int);kind[1]=1
    day=np.broadcast_to(np.array([304,305,334,335])[:,None,None],pred.shape)
    targets=dict(total=float(pred.sum()*1.01),route17_workday_month={'11':2020.,'12':4020.})
    result=reconcile(pred,day,kind,targets)
    np.testing.assert_allclose(result.sum(),targets['total'],atol=1e-6)
    np.testing.assert_allclose(result[0,5].sum(),2020.,atol=1e-6)
    np.testing.assert_allclose(result[2:,5].sum(),4020.,atol=1e-6)
    np.testing.assert_array_equal(result[pred==0],0)
    np.testing.assert_array_equal(result[:,1],pred[:,1])
    np.testing.assert_array_equal(result[1,[2,9]],pred[1,[2,9]])


def test_stacker_rejects_bad_member_and_bounds_total_weight():
    X=np.column_stack([np.full(100,100.),np.full(100,-100.)])
    w=fit_weights(X,np.full(100,40.),np.ones(100),penalty=.001)
    assert abs(w[0]-.4)<.02 and w[1]<.02 and w.sum()<=.800001


def test_final_submission_rules_and_recorded_aggregates():
    import pandas as pd
    import json,hashlib
    root=Path(__file__).resolve().parents[1]
    anchor=pd.read_csv(root/'forecasts/submission_shape50_v7.csv',sep=';')
    final=pd.read_csv(root/'forecasts/submission_architecture_v9.csv',sep=';')
    metadata=json.loads((root/'forecasts/submission_architecture_v9.json').read_text())
    pd.testing.assert_frame_equal(anchor[['route','date','hour']],final[['route','date','hour']])
    assert len(final)==14640 and final.prediction.dtype.kind in 'iu' and (final.prediction>=0).all()
    np.testing.assert_array_equal(final.loc[anchor.prediction==0,'prediction'],0)
    np.testing.assert_array_equal(final.loc[final.route==5,'prediction'],anchor.loc[anchor.route==5,'prediction'])
    # At most half a count per daily total is lost to integer rounding.
    assert abs(final.prediction.sum()-metadata['raw_aggregate_targets']['total'])<=305
    calendar=pd.read_parquet(root/'data/neural_training_pack/future_covariates.parquet')[['route','date','hour','kind']]
    calendar['date']=calendar.date.dt.strftime('%Y-%m-%d')
    grid=final.merge(calendar,on=['route','date','hour'],validate='one_to_one')
    protected=grid.route.isin([7,50])&grid.kind.ne(0)
    np.testing.assert_array_equal(grid.loc[protected,'prediction'],anchor.loc[protected,'prediction'])
    for month,total in metadata['raw_aggregate_targets']['route17_workday_month'].items():
        mask=grid.route.eq(17)&grid.kind.eq(0)&grid.date.str[5:7].astype(int).eq(int(month))
        assert abs(grid.loc[mask,'prediction'].sum()-total)<=16
    for row in json.loads((root/'forecasts/leaderboard_results.json').read_text()):
        assert hashlib.sha256((root/'forecasts'/row['file']).read_bytes()).hexdigest()==row['sha256']
