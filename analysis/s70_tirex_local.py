"""Evaluate pretrained TiRex-2 on 24-channel daily targets on Mac; no fine-tuning."""
from __future__ import annotations
import argparse
import json
import time

import numpy as np
import pandas as pd
import torch
from tirex2 import load_model, TimeseriesType
from s68_chronos_local import daily_frame, TARGETS, COVS
from s67_joint_day_net import ROOT, PACK, ROUTES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folds',default='R05,R07,B')
    parser.add_argument('--device',default='mps',choices=['cpu','mps'])
    args=parser.parse_args()
    torch.set_num_threads(4)
    out=ROOT/'data/tirex_local';out.mkdir(parents=True,exist_ok=True)
    folds={x['name']:(x['train_end'],x['horizon_days']) for x in json.loads((PACK/'folds.json').read_text())}
    folds['future']=('2025-10-31',61)
    frame=daily_frame()
    print('LOAD TiRex-2',args.device,flush=True)
    model=load_model('NX-AI/TiRex-2',device=args.device,use_flex_attention=False)
    levels=model._quantile_levels(); qi=levels.index(.5)
    for key in args.folds.split(','):
        path=out/f'{key}_{args.device}.npz'
        if path.exists():print('CACHE',path.name,flush=True);continue
        date,horizon=folds[key];origin=pd.Timestamp(date)
        start=origin-pd.Timedelta(days=111);end=origin+pd.Timedelta(days=horizon)
        inputs=[]
        for route in ROUTES:
            g=frame[(frame.route==route)&(frame.date>=start)&(frame.date<=end)]
            history=g[g.date<=origin]
            assert history.date.max()==origin and len(history)==112
            inputs.append(TimeseriesType(target=torch.from_numpy(history[TARGETS].to_numpy(dtype='float32').T.copy()),
               past_covariates=None,future_covariates=torch.from_numpy(g[COVS].to_numpy(dtype='float32').T.copy())))
        started=time.monotonic()
        forecasts=model.forecast(inputs,prediction_length=horizon,output_type='numpy',batch_size=1)
        pred=np.stack([np.asarray(f)[:,qi,:].T for f in forecasts],axis=1)
        assert pred.shape==(horizon,9,24) and np.isfinite(pred).all()
        info=dict(fold=key,origin=date,context=112,device=args.device,seconds=time.monotonic()-started,
                  mode='pretrained zero-shot, no fitting',quantile_levels=levels)
        if args.device=='mps':info['mps_driver_allocated_bytes']=torch.mps.driver_allocated_memory()
        np.savez_compressed(path,prediction=np.maximum(pred,0),metadata=json.dumps(info))
        print('DONE',info,flush=True)


if __name__=='__main__':main()
