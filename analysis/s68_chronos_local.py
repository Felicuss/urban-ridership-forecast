"""Chronos-2 24-channel daily forecast and LoRA trial on Apple MPS/CPU.

Run in data/neural_env (Python 3.12). Each fold is fitted from the original
checkpoint, using labels only up to its origin. No leaderboard submissions.
"""
from __future__ import annotations
import argparse
import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline
from chronos.chronos2.preprocess import from_data_frame
import peft  # Explicitly required: never silently fall back to full training.

from s67_joint_day_net import ROOT, PACK, ROUTES, Data, norm

OUT = ROOT/'data/chronos_local'
MODEL_REVISION = '29ec3766d36d6f73f0696f85560a422f50e8498c'
TARGETS = [f'h{h:02}' for h in range(24)]
COVS = ['workday','holiday','dow_sin','dow_cos','temperature','precipitation','regime']


def daily_frame():
    h = pd.read_parquet(PACK/'history.parquet')
    f = pd.read_parquet(PACK/'future_covariates.parquet')
    g = pd.concat([h,f], ignore_index=True)
    g = g[g.route.isin(ROUTES)].sort_values(['route','date','hour'])
    daily = g.groupby(['route','date'],sort=True).agg(kind=('kind','first'),
        holiday=('holiday','first'),dow=('dow','first'),temperature=('temperature_2m','mean'),
        precipitation=('precipitation','sum'),regime=('network_regime','first'),
        good=('train_quality_ok','first')).reset_index()
    y = g.pivot(index=['route','date'],columns='hour',values='boardings').to_numpy()
    assert len(y) == len(daily)
    y[~daily.good.to_numpy()] = np.nan
    for i,name in enumerate(TARGETS): daily[name] = y[:,i]
    daily['workday'] = (daily.kind == 0).astype(float)
    daily['holiday'] = daily.holiday.astype(float)
    daily['dow_sin'] = np.sin(2*np.pi*daily.dow/7)
    daily['dow_cos'] = np.cos(2*np.pi*daily.dow/7)
    return daily[['route','date']+TARGETS+COVS]


def predict(pipeline, inputs, horizon):
    quantiles, _ = pipeline.predict_quantiles(inputs,prediction_length=horizon,
                    quantile_levels=[.5],batch_size=40,context_length=112)
    # list of route tensors [24 targets, horizon, 1 quantile]
    p = np.stack([q[...,0].detach().cpu().numpy().T for q in quantiles],axis=1)
    assert p.shape == (horizon,9,24) and np.isfinite(p).all()
    return np.maximum(p,0)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folds',default='B')
    parser.add_argument('--steps',type=int,default=100)
    parser.add_argument('--device',default='mps',choices=['cpu','mps'])
    args=parser.parse_args()
    torch.set_num_threads(4)
    OUT.mkdir(parents=True,exist_ok=True)
    frame=daily_frame()
    folds={x['name']:(x['train_end'],x['horizon_days']) for x in json.loads((PACK/'folds.json').read_text())}
    folds['future']=('2025-10-31',61)
    info=[]
    for key in args.folds.split(','):
        path=OUT/f'{key}_steps{args.steps}_{args.device}.npz'
        if path.exists():
            print('CACHE',path.name,flush=True)
            continue
        date,horizon=folds[key]; origin=pd.Timestamp(date)
        train=frame[frame.date<=origin].copy()
        future=frame[(frame.date>origin)&(frame.date<=origin+pd.Timedelta(days=horizon))].drop(columns=TARGETS)
        assert train.date.max()==origin and len(future)==9*horizon
        train_inputs=from_data_frame(train,target_columns=TARGETS,prediction_length=61,
                    known_covariates_names=COVS,id_column='route',timestamp_column='date',use_target_encoding=False)
        pred_inputs=from_data_frame(train,target_columns=TARGETS,prediction_length=horizon,
                    future_df=future,id_column='route',timestamp_column='date',use_target_encoding=False)
        print('LOAD',key,args.device,flush=True)
        started=time.monotonic()
        pipeline=Chronos2Pipeline.from_pretrained('amazon/chronos-2',revision=MODEL_REVISION,
                                                 device_map=args.device,torch_dtype=torch.float32)
        zero=predict(pipeline,pred_inputs,horizon)
        print('ZERO',key,'seconds',round(time.monotonic()-started,2),flush=True)
        np.savez_compressed(OUT/f'{key}_zero_{args.device}.npz',prediction=zero)
        if args.steps:
            start_fit=time.monotonic()
            fitted=pipeline.fit(train_inputs,prediction_length=61,context_length=112,
                    finetune_mode='lora',learning_rate=1e-5,num_steps=args.steps,batch_size=40,min_past=28,
                    output_dir=OUT/f'{key}_lora_{args.steps}',optim='adamw_torch',
                    bf16=False,fp16=False,tf32=False,disable_tqdm=True,logging_steps=25,
                    seed=2026,data_seed=2026,disable_data_parallel=False)
            assert any('lora' in n for n,p in fitted.model.named_parameters() if p.requires_grad)
            training_seconds=time.monotonic()-start_fit
            prediction=predict(fitted,pred_inputs,horizon)
            parameters=sum(p.numel() for p in fitted.model.parameters() if p.requires_grad)
            del fitted
        else:
            prediction=zero;training_seconds=0.;parameters=0
        meta=dict(fold=key,origin=date,steps=args.steps,device=args.device,
                  trainable_parameters=parameters,training_seconds=training_seconds,
                  total_seconds=time.monotonic()-started,peft=peft.__version__,torch=torch.__version__,
                  model_revision=getattr(pipeline.model.config,'_commit_hash',None))
        if args.device=='mps': meta['mps_driver_allocated_bytes']=torch.mps.driver_allocated_memory()
        np.savez_compressed(path,prediction=prediction,zero=zero,metadata=json.dumps(meta))
        print('DONE',meta,flush=True);info.append(meta)
        del pipeline;gc.collect()
        if args.device=='mps':torch.mps.empty_cache()
    (OUT/f'run_steps{args.steps}_{args.device}.json').write_text(json.dumps(info,indent=2)+'\n')


if __name__=='__main__':main()
