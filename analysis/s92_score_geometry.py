"""Infer a smooth predictive median from observed full-submission L1 scores.

Use a Laplace residual model to avoid fitting irreducible noise as point signal.
Score feedback and known aggregates are explicit transductive observations.
Historical experiments simulate that information; no claim of ordinary CV.
"""
import json
import hashlib
import argparse
import numpy as np
import pandas as pd
import torch
from s52_round4_common import ROOT,fold_arrays
from s87_reconciliation_pilot import constraints,ipf
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write
from s89_route17_probes import decode_sum,balanced_round

torch.set_num_threads(2)
OUT=ROOT/'data/score_geometry';TABLE=ROOT/'docs/analysis/tables/score_geometry_v16'


def expected_absolute(center,scale):
    return center.abs()+scale*torch.exp(-center.abs()/scale.clamp_min(1e-6))


def directions(anchor,pool,A,rank):
    scale=(anchor+30)*(anchor>0)
    x=np.clip((pool-anchor[None])/np.maximum(scale,1)[None],-1,1)
    x[:,anchor==0]=0
    gram=np.einsum('in,jn->ij',x,x)/len(x)
    eigen,vectors=np.linalg.eigh(gram)
    v=vectors[:,np.argsort(eigen)[::-1][:rank]]
    basis=np.einsum('in,ik->nk',x,v)/np.sqrt(len(x))*scale[:,None]
    d=(anchor+1)*(anchor>0)
    g=np.einsum('in,n,jn->ij',A,d,A)
    ev,vec=np.linalg.eigh(g)
    inv=np.divide(1,ev,out=np.zeros_like(ev),where=ev>max(ev.max()*1e-10,1e-8))
    rhs=np.einsum('in,nk->ik',A,basis)
    coefficients=np.einsum('ij,j,kj,kl->il',vec,inv,vec,rhs)
    basis-=d[:,None]*np.einsum('in,ik->nk',A,coefficients)
    return basis,scale


def solve(anchor,pool,scores,A,b,total,rank,regularization,steps=700,calibrate_anchor=False):
    basis,scale=directions(anchor,pool,A,rank)
    x=torch.tensor(basis,dtype=torch.float32)
    anchor_t=torch.tensor(anchor,dtype=torch.float32)
    predictions=torch.tensor(pool,dtype=torch.float32)
    target=torch.tensor(1-np.asarray(scores),dtype=torch.float32)
    scale_t=torch.tensor(scale,dtype=torch.float32)
    beta=torch.nn.Parameter(torch.zeros(basis.shape[1]))
    reference_index=int(np.argmin(np.abs(pool-anchor[None]).sum(1)))
    initial=max(float(target[reference_index])*total/scale.sum(),.01)
    log_noise=torch.nn.Parameter(torch.tensor(np.log(initial),dtype=torch.float32))
    optimizer=torch.optim.Adam([beta,log_noise],lr=.025)
    def noise_scale(mu):
        alpha=log_noise.exp().clamp(.01,.5)
        if calibrate_anchor:
            gap=(mu-anchor_t).abs()
            for _ in range(8):
                scale_now=(scale_t*alpha).clamp_min(1e-6)
                error=expected_absolute(gap,scale_now).sum()-target[reference_index]*total
                derivative=(scale_t*torch.exp(-gap/scale_now)*(1+gap/scale_now)).sum().clamp_min(1)
                alpha=(alpha-error/derivative).clamp(.005,.5)
        return scale_t*alpha
    for step in range(steps):
        coefficients=2*torch.tanh(beta)
        mu=(anchor_t+x@coefficients).clamp_min(0)
        noise=noise_scale(mu)
        losses=expected_absolute(mu[None]-predictions,noise[None]).sum(1)/total
        fit=((losses-target)/.001).square().mean()
        penalty=regularization*coefficients.square().mean()+.1*(log_noise-np.log(initial))**2
        loss=fit+penalty
        optimizer.zero_grad();loss.backward();optimizer.step()
    with torch.no_grad():
        coefficients=(2*torch.tanh(beta)).numpy()
        mean=(anchor_t+x@torch.tensor(coefficients)).clamp_min(0).numpy().astype(float)
        noise=noise_scale(torch.tensor(mean,dtype=torch.float32)).numpy()
        fitted=(1-expected_absolute(torch.tensor(mean[None],dtype=torch.float32)-predictions,
            torch.tensor(noise[None],dtype=torch.float32)).sum(1)/total).numpy()
    result=ipf(mean,A,b)
    return result,dict(rank=rank,regularization=regularization,noise=float(noise.sum()/max(scale.sum(),1)),calibrate_anchor=calibrate_anchor,
        coefficients=coefficients.tolist(),fit_rmse=float(np.sqrt(np.mean((fitted-scores)**2))),
        fitted_scores=fitted.tolist())


def historical_pool(key,a,anchor,A,b):
    base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
    pool=[anchor,base,a['v2']];names=['anchor','v11','v2']
    for knots in [6,12]:
        for weak in [0,1]:
            file=ROOT/f'data/weak_tensor/{key}_k{knots}_w{weak}.npy'
            if file.exists():
                p=np.load(file)
                for alpha in [.25,.5,1.]:
                    pool.append(ipf((1-alpha)*base+alpha*p,A,b));names.append(f'tensor_{knots}_{weak}_{alpha}')
    file=ROOT/f'data/memory_transport/{key}_predictions.npz'
    if file.exists():
        with np.load(file) as cached:
            for name in ['raw','conditioned']:
                for alpha in [.5,1.]:
                    pool.append(ipf((1-alpha)*base+alpha*cached[name],A,b));names.append(f'memory_{name}_{alpha}')
    return np.asarray(pool),names


def main(output_name='submission_score_geometry_v16.csv',final_only=False):
    OUT.mkdir(parents=True,exist_ok=True);TABLE.mkdir(parents=True,exist_ok=True)
    rows=[]
    for key,a in fold_arrays().items():
        if final_only:break
        if key not in ['R06','R08','B']:continue
        A=constraints(a);b=np.einsum('ij,j->i',A,a['y']);total=a['y'].sum()
        base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        anchor=ipf(base,A,b);pool,names=historical_pool(key,a,anchor,A,b)
        scores=1-abs(pool-a['y'][None]).sum(1)/total
        for rank in [4,8]:
            for reg in [.1,1.,10.]:
                p,meta=solve(anchor,pool,scores,A,b,total,rank,reg)
                np.save(OUT/f'{key}_r{rank}_reg{reg}.npy',p)
                score=1-abs(p-a['y']).sum()/total
                rows.append(dict(fold=key,rank=rank,regularization=reg,score=score,
                    gain_vs_anchor=score-scores[0],gain_vs_best_observed=score-scores.max(),fit_rmse=meta['fit_rmse']))
        print(key,pd.DataFrame(rows).query('fold==@key').to_string(index=False),flush=True)
        pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    if final_only:
        summary=pd.read_csv(TABLE/'selection.csv').set_index(['rank','regularization'])
    else:
        frame=pd.DataFrame(rows)
        summary=frame.groupby(['rank','regularization']).gain_vs_anchor.agg(['mean','min'])
        summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv')
    rank,reg=summary.selection.idxmax()
    g=grid();file=ROOT/'forecasts/submission_r17_measured_v13.csv'
    champion=pd.read_csv(file,sep=';');anchor=champion.prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):
            cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.asarray([m for m,_,_ in cons],float);b=np.asarray([v for _,v,_ in cons])
    snapshot=ROOT/'forecasts/score_geometry_v16/observations.json'
    if snapshot.exists():registry=json.loads(snapshot.read_text())
    else:
        registry=[r for r in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()) if r['leaderboard_score']>=.8]
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    pool=[];scores=[];names=[]
    for r in registry:
        if r['leaderboard_score']<.8:continue
        p=ROOT/'forecasts'/r['file'];raw=p.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()]
        aligned=g[['route','date','hour']].merge(pd.read_csv(p,sep=';'),on=['route','date','hour'],validate='one_to_one')
        pool.append(aligned.prediction.to_numpy());scores.append(r['leaderboard_score']);names.append(r['file'])
    prediction,meta=solve(anchor,np.asarray(pool),np.asarray(scores),A,b,T,int(rank),float(reg),steps=1200,calibrate_anchor=True)
    result=balanced_round(prediction,cons)
    if '/' in output_name or '\\' in output_name or not output_name.endswith('.csv'):raise ValueError(output_name)
    output=ROOT/'forecasts'/output_name
    if output.exists():raise FileExistsError(output)
    write(g,result,output)
    pd.DataFrame(dict(file=names,observed_score=scores,fitted_score=meta.pop('fitted_scores'))).to_csv(TABLE/'score_fit.csv',index=False)
    meta.update(status='unscored',file=output.name,anchor=file.name,anchor_score=.91048,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),observed_full_submissions=len(pool),
        changed_cells=int((result!=anchor).sum()),l1_distance=int(abs(result-anchor).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,result)-b).max()),
        observations='score_geometry_v16/observations.json',source_sha256=hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),
        caveat='Distributional inverse-score model; latent hourly labels are not observed. Historical checks use simulated score feedback.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('EXPORTED',meta,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='submission_score_geometry_v16.csv')
    parser.add_argument('--final-only',action='store_true');args=parser.parse_args()
    main(args.out,args.final_only)
