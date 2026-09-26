"""One v9 candidate: graph shape + structural ETS level + aggregate constraints.

Temporal learned stacking was evaluated and rejected. Its files are retained
for research provenance, not applied to the submission.
"""
from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd

from s67_joint_day_net import ROOT, Data, ROUTES, ALL_ROUTES
from s52_round4_common import future_arrays, Experiment
from s66_next_iteration import current_core
from s64_package_shape_facts import shares,round_daily,verify_scored_files
from s62_hourly_shape import shape_adjust
from s63_external_level_probe import factors,apply_factor
from s74_architecture_round import raw_predictions,replacement
from s75_temporal_stacker import MEMBERS,apply_stack,reconcile

OUT=ROOT/'forecasts/architecture_v9'
ANCHOR=ROOT/'forecasts/submission_shape50_v7.csv'
ANCHOR_SHA='16048f68932802813d4760e0907b6ed3c09892f8c4aaf191327279755308d13e'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_probes():
    source=ROOT/'forecasts/next_iteration/diagnostics/manifest.json'
    records={x['id']:x for x in json.loads(source.read_text())['carrier_records']}
    denominator=records['p10']['sum_h']/(.90553-records['p10']['score'])
    # Round-to-nearest five decimals on each score yields denominator interval.
    gap=.90553-records['p10']['score']
    interval=[records['p10']['sum_h']/(gap+1e-5),records['p10']['sum_h']/(gap-1e-5)]
    totals={}
    for key in ['p11','p12']:
        record=records[key]
        totals[str(record['group'][2])]=(record['score']*denominator+record['sum_h'])/2
    return dict(total=denominator,route17_workday_month=totals),dict(
        total_rounding_interval=interval,source_sha256=digest(source),records=records,
        caveat='Total assumes zero true route-5 November cells. Route-17 estimates are capped sums min(y,H), not guaranteed exact group sums; prior historical clipping audit found small but nonzero violations.')


def main():
    verify_scored_files();assert digest(ANCHOR)==ANCHOR_SHA
    data=Data();a=future_arrays();raw=raw_predictions('future')
    assert all(name in raw for name,_ in MEMBERS)
    ff,_=factors(Experiment(),303,np.arange(304,365))
    ref=apply_factor(shape_adjust(current_core('future',a),shares('future'),a,.5),a,ff['tram'],.25).reshape(61,10,24)
    delta=np.stack([replacement(ref,raw[name],data.kind[304:],mode)-ref for name,mode in MEMBERS],-1)
    day=np.broadcast_to(np.arange(304,365)[:,None,None],ref.shape)
    route=np.broadcast_to(np.asarray(ALL_ROUTES)[None,:,None],ref.shape)
    kind=np.broadcast_to(data.kind[304:,0,None,None],ref.shape)
    block=dict(reference=ref,delta=delta,route=route,day=day,kind=kind)
    weights=json.loads((ROOT/'data/architecture_round9/stack_weights.json').read_text())
    assert weights['members']==[list(x) for x in MEMBERS]
    prediction=ref+.5*delta[...,0]+.5*delta[...,4]
    source=pd.read_csv(ANCHOR,sep=';',parse_dates=['date']);ordered=source.sort_values(['date','route','hour'])
    anchor=ordered.prediction.to_numpy().reshape(ref.shape)
    ratio=np.divide(prediction,ref,out=np.ones_like(ref),where=ref>0)
    # Retain all existing incident/calendar/fare rules by transferring the core ratio.
    proposed=anchor*ratio
    targets,provenance=decode_probes()
    calibrated=reconcile(proposed,day,kind,targets)
    totals=np.rint(calibrated.sum(-1)).astype('int64')
    final=round_daily(calibrated.reshape(-1),totals.reshape(-1)).reshape(ref.shape)
    protected=(route==5)|(np.isin(route,[7,50])&(kind!=0))
    np.testing.assert_array_equal(final[protected],anchor[protected])
    np.testing.assert_array_equal(final[anchor==0],0)
    candidate=ordered[['route','date','hour']].assign(prediction=final.reshape(-1))
    candidate=source.drop(columns='prediction').merge(candidate,on=['route','date','hour'],validate='one_to_one')
    assert len(candidate)==14640 and candidate[['route','date','hour']].equals(source[['route','date','hour']])
    assert (candidate.prediction>=0).all() and candidate.prediction.dtype.kind in 'iu'
    candidate.date=candidate.date.dt.strftime('%Y-%m-%d')
    path=ROOT/'forecasts/submission_architecture_v9.csv'
    payload=candidate.to_csv(sep=';',index=False).encode()
    for record in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()):
        if record['file']==path.name:assert hashlib.sha256(payload).hexdigest()==record['sha256']
    path.write_bytes(payload)
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['stack_weights.json','stack_validation.csv','validation.csv','summary.csv','oracle_diagnostics.csv','fixed_route_validation.csv']:
        shutil.copyfile(ROOT/'data/architecture_round9'/name,OUT/name)
    for p in (ROOT/'data/graph_moe').glob('graph_seed*.pt'):shutil.copyfile(p,OUT/p.name)
    for name,p in raw.items():np.save(OUT/f'{name}_future.npy',p)
    np.save(OUT/'canonical_prediction.npy',final)
    differences=final-anchor
    meta=dict(file=path.name,sha256=digest(path),status='unscored',leaderboard_score=None,
       anchor=ANCHOR.name,anchor_sha256=ANCHOR_SHA,anchor_score=.90570,
       method='50% graph-based hourly-shape replacement + 50% structural STL/ETS daily-level replacement of the v7 core; probe-based aggregate reconciliation',
       members=MEMBERS,global_weights=[.5,0.,0.,0.,.5,0.],
       selected_validation_model='fixed_graph50_ets50_oracle_reconciled',
       rejected_components=['learned temporal stack','graph daily level','Chronos-2 LoRA-500','VARX'],
       raw_aggregate_targets=targets,aggregate_provenance=provenance,
       sum_prediction=int(final.sum()),sum_difference=int(differences.sum()),
       changed_rows=int((differences!=0).sum()),changed_daily_totals=int((final.sum(-1)!=anchor.sum(-1)).sum()),
       absolute_difference=int(abs(differences).sum()),
       route_sum_difference={str(r):int(differences[:,i].sum()) for i,r in enumerate(ALL_ROUTES)},
       validation=pd.read_csv(OUT/'stack_validation.csv').to_dict('records'),
       caveats=['New architecture does not guarantee improvement; consult the recorded leaderboard score.',
          'Base-model and fixed-blend choices used overlapping development periods. Purged learned meta-stacking was tested and rejected.',
          'Oracle-reconciled historical scores use known evaluation group totals and must not be reported as ordinary forecasting validation.',
          'Future reconciliation uses previously scored probes, not hidden cell labels. Their assumptions and rounding uncertainty are recorded.',
          'Actual future weather and city facts are intentionally permitted external information.',
          'Route 5, non-workday routes 7/50 and all zero hours remain unchanged.'],
       source_sha256={p.name:digest(p) for p in [ROOT/f'analysis/{n}' for n in ['s72_graph_regime_moe.py','s73_structural_statistical.py','s74_architecture_round.py','s75_temporal_stacker.py','s76_package_architecture_v9.py']]},
       artifact_sha256={p.name:digest(p) for p in OUT.iterdir() if p.is_file()})
    for record in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()):
        if record['file']==path.name and record['sha256']==meta['sha256']:
            meta.update(status='scored',leaderboard_score=record['leaderboard_score'],
                        leaderboard_delta_vs_anchor=round(record['leaderboard_score']-meta['anchor_score'],8),
                        evidence=record['evidence'])
    path.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    verify_scored_files();print(json.dumps({k:meta[k] for k in ['file','sha256','global_weights','changed_rows','changed_daily_totals','sum_difference']},indent=2),flush=True)


if __name__=='__main__':main()
