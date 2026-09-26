"""Train a causal joint 24-hour profile model locally; evaluate against v7.

No validation labels enter model training. Future weather is an explicitly
permitted external covariate. Folds are reused development periods, not a test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'data/neural_training_pack'
OUT = ROOT / 'data/joint_day_net'
ROUTES = [1, 7, 11, 12, 17, 25, 26, 28, 50]
ALL_ROUTES = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]
CONTEXT = 56


def norm(x):
    return x / np.maximum(x.sum(axis=-1, keepdims=True), 1e-8)


class Data:
    def __init__(self):
        history = pd.read_parquet(PACK/'history.parquet')
        future = pd.read_parquet(PACK/'future_covariates.parquet')
        frame = pd.concat([history, future], ignore_index=True)
        frame = frame[frame.route.isin(ROUTES)].sort_values(['date', 'route', 'hour'])
        assert not frame.duplicated(['date', 'route', 'hour']).any()
        self.y = frame.boardings.to_numpy().reshape(365, 9, 24).astype('float32')
        assert np.isnan(self.y[304:]).all()
        self.total = np.nan_to_num(self.y).sum(-1)
        self.shape = norm(np.nan_to_num(self.y))
        daily = frame[frame.hour == 0]
        self.kind = daily.kind.to_numpy().reshape(365, 9)
        self.dow = daily.dow.to_numpy().reshape(365, 9)
        self.good = daily.train_quality_ok.to_numpy(copy=True).reshape(365, 9)  # pandas 3 hands out read-only arrays
        self.good &= self.total > 100
        # Match deployed protections; validation still scores every cell.
        self.good &= ~((np.isin(ROUTES, [7, 50])[None, :]) & (self.kind != 0))
        day = np.arange(365)[:, None, None]
        pieces = [np.eye(3)[self.kind], np.eye(7)[self.dow],
                  daily.holiday.to_numpy().reshape(365, 9, 1),
                  daily.network_regime.to_numpy().reshape(365, 9, 1)/5,
                  np.broadcast_to(np.sin(2*np.pi*day/365), (365, 9, 1)),
                  np.broadcast_to(np.cos(2*np.pi*day/365), (365, 9, 1))]
        for name, scale in [('temperature_2m', 20), ('precipitation', 5),
                            ('cloud_cover', 100), ('wind_speed_10m', 30)]:
            w = frame[name].to_numpy().reshape(365, 9, 24)/scale
            # Four 6-hour summaries retain intraday weather without 96 inputs.
            pieces.append(w.reshape(365, 9, 4, 6).mean(-1))
        self.cov = np.concatenate(pieces, axis=-1).astype('float32')
        assert np.isfinite(self.cov).all()

    def context(self, origin):
        """Only source dates <= origin. Bad history is masked, never backfilled."""
        lo = max(0, origin-CONTEXT+1)
        sl = slice(lo, origin+1)
        quality = self.good[sl]
        local_level = np.log1p(self.total[sl])/10
        x = np.concatenate([self.shape[sl]*24, local_level[..., None],
                            np.eye(3)[self.kind[sl]], quality[..., None]], axis=-1)
        x[..., :25] *= quality[..., None]
        x = np.pad(x, ((CONTEXT-len(x), 0), (0, 0), (0, 0)))
        return x.transpose(1, 0, 2).reshape(9, -1).astype('float32')

    def baseline(self, origin, dates):
        lo = max(0, origin-83)
        source = np.arange(lo, origin+1)
        age = (origin-source)[:, None]
        decay = np.exp(-age/28)*self.good[source]
        outputs = []
        for d in dates:
            weights = decay * (0.02 + (self.kind[source] == self.kind[d]))
            weights *= 1 + .25*(self.dow[source] == self.dow[d])
            p = (weights[..., None]*self.shape[source]).sum(axis=0)
            # Minimal smoothing prevents log(0); deployed support masks apply later.
            outputs.append(norm(p + 1e-4))
        return np.asarray(outputs, dtype='float32')

    def samples(self, cutoff):
        origins = np.arange(27, cutoff, 7)
        pairs = [(i, d) for i, o in enumerate(origins)
                 for d in range(o+1, min(o+62, cutoff+1))]
        idx = np.array([i for i, d in pairs])
        dates = np.array([d for i, d in pairs])
        counts = np.bincount(dates, minlength=365)
        assert dates.max() <= cutoff and np.all(origins[idx] < dates)
        bases = np.concatenate([self.baseline(o, np.arange(o+1, min(o+62, cutoff+1)))
                                for o in origins])
        cov = np.concatenate([self.cov[dates],
              np.broadcast_to(((dates-origins[idx])/61)[:, None, None], (len(dates),9,1))], axis=-1)
        weights = self.total[dates] * self.good[dates] / counts[dates, None]
        weights /= max(weights.mean(), 1)
        return dict(context=np.stack([self.context(o) for o in origins]),
                    index=idx, cov=cov, base=bases, target=self.shape[dates],
                    weight=weights, dates=dates, origins=origins)


class JointDayNet(nn.Module):
    def __init__(self, context_dim, cov_dim, width=96):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(context_dim, width), nn.LayerNorm(width),
                                     nn.GELU(), nn.Dropout(.1), nn.Linear(width, width), nn.GELU())
        self.route = nn.Embedding(9, 12)
        self.decoder = nn.Sequential(nn.Linear(width*2+cov_dim+24+12, width), nn.GELU(),
                                     nn.Dropout(.1), nn.Linear(width, width), nn.GELU(),
                                     nn.Linear(width, 24))
        nn.init.zeros_(self.decoder[-1].weight)
        nn.init.zeros_(self.decoder[-1].bias)

    def forward(self, context, cov, base):
        encoded = self.encoder(context)
        shared = encoded.mean(dim=1, keepdim=True).expand_as(encoded)
        route = self.route.weight[None].expand(context.shape[0], -1, -1)
        x = torch.cat([encoded, shared, cov, base*24, route], dim=-1)
        correction = .75*torch.tanh(self.decoder(x))
        return torch.softmax(torch.log(base.clamp_min(1e-8))+correction, dim=-1), correction


def fit_predict(data, cutoff, horizon, seed, steps, device, label, batch_size=64):
    path = OUT / f'{label}_seed{seed}_steps{steps}.npz'
    if path.exists():
        result = np.load(path)
        print('CACHE', path.name, flush=True)
        return result['prediction'], json.loads(str(result['metadata']))
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    samples = data.samples(cutoff)
    model = JointDayNet(samples['context'].shape[-1], samples['cov'].shape[-1]).to(device)
    tensors = {k: torch.as_tensor(samples[k], dtype=torch.float32, device=device)
               for k in ['context', 'cov', 'base', 'target', 'weight']}
    indexes = torch.as_tensor(samples['index'], dtype=torch.long, device=device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=.02)
    started = time.monotonic()
    losses = []
    model.train()
    for step in range(steps):
        ix = torch.as_tensor(rng.integers(0, len(indexes), batch_size), dtype=torch.long, device=device)
        pred, correction = model(tensors['context'][indexes[ix]], tensors['cov'][ix], tensors['base'][ix])
        loss = ((pred-tensors['target'][ix]).abs().sum(-1)*tensors['weight'][ix]).mean()
        loss = loss + .002*correction.square().mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1)
        optimizer.step()
        if step == 0 or (step+1) % 100 == 0:
            val = float(loss.detach().cpu())
            losses.append([step+1, val])
            print(label, seed, f'{step+1}/{steps}', 'loss', round(val,6),
                  'seconds', round(time.monotonic()-started,1), flush=True)
    dates = np.arange(cutoff+1, cutoff+horizon+1)
    cov = np.concatenate([data.cov[dates],
           np.broadcast_to(((dates-cutoff)/61)[:, None, None], (horizon,9,1))], axis=-1)
    base = data.baseline(cutoff, dates)
    model.eval()
    with torch.no_grad():
        prediction, _ = model(torch.as_tensor(np.broadcast_to(data.context(cutoff),
                                  (horizon,9,samples['context'].shape[-1])).copy(), device=device),
                              torch.as_tensor(cov, dtype=torch.float32, device=device),
                              torch.as_tensor(base, device=device))
        prediction = prediction.cpu().numpy()
    assert np.isfinite(prediction).all()
    np.testing.assert_allclose(prediction.sum(-1), 1, atol=1e-6)
    info = dict(fold=label, seed=seed, steps=steps, device=str(device),
                cutoff=int(cutoff), max_training_target=int(samples['dates'].max()),
                training_pairs=len(indexes), parameters=sum(p.numel() for p in model.parameters()),
                seconds=time.monotonic()-started, loss_trace=losses,
                torch_version=torch.__version__)
    if device == 'mps':
        info['mps_driver_allocated_bytes'] = torch.mps.driver_allocated_memory()
    np.savez_compressed(path, prediction=prediction, base=base, metadata=json.dumps(info))
    if label == 'future':
        torch.save(dict(state_dict={k:v.cpu() for k,v in model.state_dict().items()},
                        context_dim=samples['context'].shape[-1], cov_dim=samples['cov'].shape[-1],
                        metadata=info), OUT/f'joint_day_net_seed{seed}.pt')
    return prediction, info


def v7_references():
    # Reuse exact historical analogue, without importing it into the training path.
    from s52_round4_common import fold_arrays, FOLDS, Experiment
    from s66_next_iteration import current_core
    from s64_package_shape_facts import shares
    from s62_hourly_shape import shape_adjust
    from s63_external_level_probe import factors, apply_factor
    exp = Experiment()
    arrays = fold_arrays()
    result = {}
    for key, date, h in FOLDS:
        a = arrays[key]
        o = pd.Timestamp(date).dayofyear-1
        ff, _ = factors(exp, o, np.arange(o+1, o+h+1))
        ref = apply_factor(shape_adjust(current_core(key,a), shares(key), a, .5), a, ff['tram'], .25)
        result[key] = (a, ref.reshape(-1,10,24))
    return result


def blend_shape(reference, proposed, kind, weight):
    out = reference.astype('float64', copy=True)
    for ri, route in enumerate(ROUTES):
        j = ALL_ROUTES.index(route)
        p = reference[:,j]
        s = proposed[:,ri].copy()
        s[p == 0] = 0
        s = norm(s)
        mixed = (1-weight)*p + weight*s*p.sum(-1,keepdims=True)
        mixed[s.sum(-1)==0] = p[s.sum(-1)==0]
        if route in [7,50]:
            mixed[kind[:,ri] != 0] = p[kind[:,ri] != 0]
        out[:,j] = mixed
    np.testing.assert_allclose(out.sum(-1), reference.sum(-1), rtol=1e-6, atol=.01)
    assert np.all(out[reference == 0] == 0)
    return out


def evaluate(data, results):
    references = v7_references()
    rows = []
    controls = []
    for key, (prediction, meta) in results.items():
        if key == 'future': continue
        a, ref = references[key]
        truth = a['y'].reshape(ref.shape)
        cutoff = meta[0]['cutoff']
        kind = data.kind[cutoff+1:cutoff+1+len(ref)]
        causal_profile = data.baseline(cutoff, np.arange(cutoff+1, cutoff+1+len(ref)))
        for weight in [0, .1, .2, .35, .5, 1.]:
            p = blend_shape(ref, prediction, kind, weight)
            if weight in [.2, .35, .5]:
                untrained = blend_shape(ref, causal_profile, kind, weight)
                for name, values in [('causal_profile', untrained), ('joint_net', p)]:
                    controls.append(dict(fold=key, mode=name, weight=weight,
                        gain=(abs(ref-truth).sum()-abs(values-truth).sum())/truth.sum()))
            for route in [0]+ROUTES:
                mask = np.ones_like(truth, dtype=bool)
                if route:
                    mask[:] = False
                    mask[:,ALL_ROUTES.index(route)] = True
                total = truth[mask].sum()
                loss = abs(p[mask]-truth[mask]).sum()
                base_loss = abs(ref[mask]-truth[mask]).sum()
                rows.append(dict(fold=key,route=route,weight=weight,score=1-loss/total,
                                 reference_score=1-base_loss/total,gain=(base_loss-loss)/total))
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT/'validation.csv',index=False)
    pd.DataFrame(controls).to_csv(OUT/'profile_control.csv',index=False)
    summary = frame[frame.route == 0].pivot(index='weight',columns='fold',values='gain')
    summary['mean'] = summary.mean(axis=1)
    summary.to_csv(OUT/'summary.csv')
    print(summary.round(6).to_string(), flush=True)
    return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folds', default='R05,R07,B')
    parser.add_argument('--seeds', default='2026')
    parser.add_argument('--steps', type=int, default=600)
    parser.add_argument('--device', choices=['cpu','mps','auto'], default='auto')
    parser.add_argument('--batch-size', type=int, default=64)
    args = parser.parse_args()
    device = ('mps' if torch.backends.mps.is_available() else 'cpu') if args.device == 'auto' else args.device
    torch.set_num_threads(4)
    OUT.mkdir(parents=True, exist_ok=True)
    data = Data()
    folds = {x['name']:(pd.Timestamp(x['train_end']).dayofyear-1,x['horizon_days'])
             for x in json.loads((PACK/'folds.json').read_text())}
    folds['future'] = (303,61)
    results = {}
    for key in args.folds.split(','):
        cutoff,horizon = folds[key]
        trained = [fit_predict(data, cutoff,horizon,int(seed),args.steps,device,key,args.batch_size)
                   for seed in args.seeds.split(',')]
        results[key] = (np.mean([x[0] for x in trained],axis=0),[x[1] for x in trained])
        np.save(OUT/f'ensemble_{key}.npy',results[key][0])
    if any(key != 'future' for key in results):
        evaluate(data,results)
    (OUT/'run.json').write_text(json.dumps(dict(arguments=vars(args),requested_device=device,
         training_devices=sorted({m['device'] for _,ms in results.values() for m in ms}),
         source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         runs={k:m for k,(_,m) in results.items()}),indent=2)+'\n')


if __name__ == '__main__':
    main()
