"""Freeze the locally trained 3-seed ensemble and one shape-only v8 submission."""
from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from s67_joint_day_net import ROOT, PACK, OUT, ROUTES, ALL_ROUTES, Data, JointDayNet, blend_shape
from s64_package_shape_facts import round_daily, verify_scored_files

ANCHOR = ROOT/'forecasts/submission_shape50_v7.csv'
ANCHOR_SHA = '16048f68932802813d4760e0907b6ed3c09892f8c4aaf191327279755308d13e'
WEIGHT = .35
CHRONOS_WEIGHT = .35
SEEDS = [2026, 2027, 2028]


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    verify_scored_files()
    assert digest(ANCHOR) == ANCHOR_SHA
    directory = ROOT/'forecasts/joint_day_v8'
    directory.mkdir(parents=True,exist_ok=True)
    data = Data()
    # Recreate final predictions from portable CPU state dictionaries.
    dates = np.arange(304,365)
    cov = np.concatenate([data.cov[dates],np.broadcast_to(((dates-303)/61)[:,None,None],(61,9,1))],axis=-1)
    base = data.baseline(303,dates)
    predictions=[]
    torch.set_num_threads(4)
    for seed in SEEDS:
        path=OUT/f'joint_day_net_seed{seed}.pt'
        checkpoint=torch.load(path,map_location='cpu',weights_only=False)
        assert checkpoint['metadata']['cutoff']==303 and checkpoint['metadata']['steps']==600
        model=JointDayNet(checkpoint['context_dim'],checkpoint['cov_dim'])
        model.load_state_dict(checkpoint['state_dict']); model.eval()
        with torch.no_grad():
            shape,_=model(torch.as_tensor(np.broadcast_to(data.context(303),(61,9,checkpoint['context_dim'])).copy()),
                          torch.as_tensor(cov,dtype=torch.float32),torch.as_tensor(base))
        predictions.append(shape.numpy())
        shutil.copyfile(path,directory/path.name)
    shape=np.mean(predictions,axis=0)
    np.testing.assert_allclose(shape,np.load(OUT/'ensemble_future.npy'),rtol=2e-4,atol=2e-6)
    # CPU regeneration may have tiny FP32 differences; freeze MPS predictions as
    # the canonical artifact so largest-remainder rounding is reproducible.
    shape=np.load(OUT/'ensemble_future.npy')
    np.save(directory/'future_shares.npy',shape)
    source=pd.read_csv(ANCHOR,sep=';',parse_dates=['date'])
    ordered=source.sort_values(['date','route','hour'])
    reference=ordered.prediction.to_numpy().reshape(61,10,24)
    prediction=blend_shape(reference,shape,data.kind[304:],WEIGHT)
    chronos_path=ROOT/'data/chronos_local/future_steps0_mps.npz'
    chronos=np.load(chronos_path)
    chronos_prediction=chronos['prediction']
    chronos_metadata=json.loads(str(chronos['metadata']))
    prediction=blend_shape(prediction,chronos_prediction,data.kind[304:],CHRONOS_WEIGHT)
    np.save(directory/'chronos_future.npy',chronos_prediction)
    rounded=round_daily(prediction.reshape(-1),reference.sum(-1).reshape(-1))
    frame=ordered[['route','date','hour']].assign(prediction=rounded)
    sub=source.drop(columns='prediction').merge(frame,on=['route','date','hour'],validate='one_to_one')
    assert len(sub)==14640 and sub[['route','date','hour']].equals(source[['route','date','hour']])
    np.testing.assert_array_equal(sub.groupby(['route','date']).prediction.sum(),source.groupby(['route','date']).prediction.sum())
    np.testing.assert_array_equal(sub.loc[source.prediction==0,'prediction'],0)
    protected=ordered.route.eq(5).to_numpy() | (ordered.route.isin([7,50]).to_numpy() &
                   np.repeat(data.kind[304:,0]!=0,240))
    np.testing.assert_array_equal(rounded[protected],ordered.prediction.to_numpy()[protected])
    sub.date=sub.date.dt.strftime('%Y-%m-%d')
    output=ROOT/'forecasts/submission_joint_day_v8.csv'
    payload=sub.to_csv(sep=';',index=False).encode('utf-8')
    for record in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()):
        if record['file']==output.name:
            assert hashlib.sha256(payload).hexdigest()==record['sha256'], 'Refusing to overwrite a scored artifact'
    output.write_bytes(payload)
    comparison=ROOT/'docs/analysis/tables/local_neural_comparison.csv'
    validation=pd.read_csv(comparison)
    chosen=validation[validation.model=='joint35_then_chronos0_0.35']
    assert len(chosen)==6 and chosen.gain.mean()>0 and (chosen.gain>0).sum()==6
    for name in ['validation.csv','summary.csv','profile_control.csv','run.json']:
        shutil.copyfile(OUT/name,directory/name)
    shutil.copyfile(comparison,directory/'model_comparison.csv')
    meta=dict(file=output.name,sha256=digest(output),status='unscored',leaderboard_score=None,
        anchor=ANCHOR.name,anchor_sha256=ANCHOR_SHA,anchor_score=.90570,
        method='Shape ensemble: 42.25% v7, 22.75% 3-seed JointDayNet, 35% pretrained Chronos-2; exact v7 daily integer totals',
        parameters_per_model=202212,seeds=SEEDS,training_steps=600,context_days=56,
        device='Apple M5 Pro / PyTorch MPS',route_order=ROUTES,shape_weight=WEIGHT,
        chronos_weight=CHRONOS_WEIGHT,chronos=chronos_metadata,
        selection='JointDayNet 35% first, then Chronos zero-shot 35%; best mean of tested fixed blends across all six reused development folds, positive on all six',
        validation=chosen.to_dict('records'),mean_gain=float(chosen.gain.mean()),
        worst_gain=float(chosen.gain.min()),wins=int((chosen.gain>0).sum()),
        october_gain=float(chosen.loc[chosen.fold=='B','gain'].iloc[0]),
        changed_rows=int((sub.prediction.to_numpy()!=source.prediction.to_numpy()).sum()),
        sum_difference=int(sub.prediction.sum()-source.prediction.sum()),
        training_data_sha256=digest(PACK/'history.parquet'),
        source_sha256={p.name:digest(p) for p in [Path(__file__),ROOT/'analysis/s67_joint_day_net.py',ROOT/'analysis/s68_chronos_local.py',ROOT/'analysis/s71_local_model_comparison.py']},
        artifacts_sha256={p.name:digest(p) for p in directory.iterdir() if p.is_file()},
        caveats=['Historical improvement does not guarantee leaderboard improvement; consult the recorded platform score.',
                 'Six development periods overlap and were reused for model/blend selection.',
                 'Actual future weather is an explicitly permitted external covariate.',
                 'Future route targets are unknown; only labels through Oct31 train final weights.',
                 'All daily totals, zero hours, route 5, and non-workday 7/50 are preserved.',
                 'Chronos is used without fine-tuning. Tested LoRA and TiRex variants are not part of this candidate.'])
    for record in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()):
        if record['file']==output.name and record['sha256']==meta['sha256']:
            meta.update(status='scored',leaderboard_score=record['leaderboard_score'],
                        leaderboard_delta_vs_anchor=round(record['leaderboard_score']-meta['anchor_score'],8),
                        evidence=record['evidence'])
    output.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    verify_scored_files()
    print(json.dumps({k:meta[k] for k in ['file','sha256','changed_rows','mean_gain','october_gain','worst_gain']},indent=2),flush=True)


if __name__=='__main__':main()
