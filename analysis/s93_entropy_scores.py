"""Maximum-entropy posterior constrained by aggregate counts and observed L1 losses.

Distributions over hourly counts are inferred, not claimed recovered labels.
Point forecasts are posterior medians/means, reconciled to known sums.
"""
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp,ndtr,stdtr
from s92_score_geometry import historical_pool
from s52_round4_common import ROOT,fold_arrays
from s87_reconciliation_pilot import constraints,ipf
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write
from s89_route17_probes import decode_sum,balanced_round

OUT=ROOT/'data/entropy_scores';TABLE=ROOT/'docs/analysis/tables/entropy_scores_v17'


def prior_grid(anchor,total_error,noise_multiplier=None,skew=None,distribution='laplace'):
    z=np.array([-8,-5,-3.5,-2.5,-1.75,-1.25,-.9,-.6,-.4,-.25,-.125,0,.125,.25,.4,.6,.9,1.25,1.75,2.5,3.5,5,8])
    edges=np.r_[-np.inf,(z[:-1]+z[1:])/2,np.inf]
    cdf=np.where(edges<=0,.5*np.exp(-abs(edges)),1-.5*np.exp(-abs(edges)))
    if distribution=='normal':cdf=ndtr(edges)
    elif distribution=='student3':cdf=stdtr(3,edges)
    elif distribution=='mixture':cdf=.5*cdf+.5*ndtr(edges)
    elif distribution!='laplace':raise ValueError(distribution)
    probabilities=np.diff(cdf)
    scale=(anchor+30)*(anchor>0)
    if noise_multiplier is not None:scale*=noise_multiplier
    offsets=z[None] if skew is None else z[None]*np.exp(np.sign(z)[None]*np.asarray(skew)[:,None])
    lo,hi=.001,1.
    for _ in range(40):
        alpha=(lo+hi)/2
        y=np.maximum(0,anchor[:,None]+alpha*scale[:,None]*offsets)
        error=np.einsum('nk,k->',abs(y-anchor[:,None]),probabilities)
        if error<total_error:lo=alpha
        else:hi=alpha
    return y,probabilities,alpha


def posterior(anchor,pool,scores,A,b,total,penalty=1e-6,maxiter=450,queries=None,noise_multiplier=None,skew=None,distribution='laplace',return_distribution=False,custom_prior=None,entropy_power=1.):
    reference=int(np.argmin(abs(pool-anchor[None]).sum(1)))
    if custom_prior is None:
        support,prior,noise=prior_grid(anchor,(1-scores[reference])*total,noise_multiplier,skew,distribution)
    else:
        support,prior=custom_prior
        support=np.asarray(support,dtype=float);prior=np.asarray(prior,dtype=float)
        if support.shape!=(len(anchor),len(prior)) or not np.isfinite(support).all() or (support<0).any():raise ValueError('Invalid custom support')
        if (np.diff(support,axis=1)<0).any() or (prior<=0).any() or not np.isclose(prior.sum(),1):raise ValueError('Invalid custom probabilities/order')
        noise=None
    weights=(anchor+30)**entropy_power
    weights/=weights.sum()
    normalized=support/(total*weights[:,None])
    # Difference constraints cancel much of the common irreducible noise.
    cost_anchor=abs(support-anchor[:,None])
    keep=[j for j in range(len(pool)) if j!=reference]
    cost=np.stack([abs(support-pool[j,:,None])-cost_anchor for j in keep]+[cost_anchor])
    targets=np.r_[scores[reference]-scores[keep],1-scores[reference]]
    features=cost/(total*weights[None,:,None])
    means=np.einsum('jnk,k->jn',features,prior)
    variance=np.einsum('jnk,k->jn',(features-means[:,:,None])**2,prior)
    score_scale=np.maximum(np.sqrt(np.einsum('jn,n->j',variance,weights)),1e-4)
    ymean=np.einsum('nk,k->n',normalized,prior)
    yvar=np.einsum('nk,k->n',(normalized-ymean[:,None])**2,prior)
    group_scale=np.maximum(np.sqrt(np.einsum('gn,n,n->g',A,weights,yvar)),1e-4)
    features/=score_scale[:,None,None]
    group=A/group_scale[:,None]
    targets=np.r_[targets/score_scale,(b/total)/group_scale]
    ns=len(score_scale);logprior=np.log(prior)[None]
    def objective(parameters,return_prob=False):
        field=np.einsum('j,jnk->nk',parameters[:ns],features)
        field+=np.einsum('g,gn->n',parameters[ns:],group)[:,None]*normalized
        logits=logprior-field
        normalizer=logsumexp(logits,axis=1)
        probability=np.exp(logits-normalizer[:,None])
        expected_score=np.einsum('jnk,nk,n->j',features,probability,weights)
        expected_y=np.einsum('nk,nk->n',normalized,probability)
        expected_group=np.einsum('gn,n,n->g',group,expected_y,weights)
        objective_value=np.dot(weights,normalizer)+np.dot(parameters,targets)+.5*penalty*np.dot(parameters,parameters)
        gradient=targets-np.r_[expected_score,expected_group]+penalty*parameters
        if return_prob:return probability
        return objective_value,gradient
    result=minimize(objective,np.zeros(len(targets)),jac=True,method='L-BFGS-B',
        options=dict(maxiter=maxiter,ftol=1e-12,gtol=1e-7,maxcor=30))
    probability=objective(result.x,True)
    mean=np.einsum('nk,nk->n',support,probability)
    midcdf=np.cumsum(probability,axis=1)-.5*probability
    median=np.array([np.interp(.5,cdf,values) for cdf,values in zip(midcdf,support)])
    posterior_losses=np.array([np.einsum('nk,nk->',abs(support-p[:,None]),probability) for p in pool])
    fitted_scores=1-posterior_losses/total
    expected_groups=np.einsum('gn,n->g',A,mean)
    meta=dict(converged=bool(result.success),message=str(result.message),iterations=int(result.nit),
        noise=noise,penalty=penalty,score_rmse=float(np.sqrt(np.mean((fitted_scores-scores)**2))),
        max_score_error=float(abs(fitted_scores-scores).max()),
        posterior_max_aggregate_error=float(abs(expected_groups-b).max()),
        fitted_scores=fitted_scores.tolist())
    if queries is not None:
        meta['query_scores']=[float(1-np.einsum('nk,nk->',abs(support-p[:,None]),probability)/total) for p in queries]
    forecast=dict(mean=mean,median=median)
    if return_distribution:forecast.update(support=support,probability=probability)
    return forecast,meta


def main(output_name):
    if '/' in output_name or '\\' in output_name or not output_name.endswith('.csv'):raise ValueError(output_name)
    output=ROOT/'forecasts'/output_name
    if output.exists():raise FileExistsError(output)
    TABLE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    rows=[];diagnostics=[]
    for key,a in fold_arrays().items():
        if key not in ['R06','R08','B']:continue
        A=constraints(a);b=np.einsum('ij,j->i',A,a['y']);total=a['y'].sum()
        base=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        ref=ipf(base,A,b);pool,names=historical_pool(key,a,ref,A,b)
        scores=1-abs(pool-a['y'][None]).sum(1)/total
        best=int(scores.argmax());anchor=pool[best]
        forecasts,meta=posterior(anchor,pool,scores,A,b,total)
        diagnostics.append(dict(fold=key,anchor_name=names[best],**meta))
        for name,p in forecasts.items():
            for alpha in [.5,1.]:
                q=ipf((1-alpha)*anchor+alpha*p,A,b)
                score=1-abs(q-a['y']).sum()/total
                rows.append(dict(fold=key,method=name,alpha=alpha,anchor_score=float(scores[best]),score=score,gain=score-scores[best]))
        pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
        print(key,pd.DataFrame(rows).query('fold==@key').to_string(index=False),meta['score_rmse'],meta['converged'],flush=True)
    summary=pd.DataFrame(rows).groupby(['method','alpha']).gain.agg(['mean','min'])
    summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv')
    method,alpha=summary.selection.idxmax()
    g=grid();champion=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';');anchor=champion.prediction.to_numpy(dtype=float)
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):
            cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float);b=np.array([v for _,v,_ in cons])
    snapshot=ROOT/'forecasts/entropy_scores_v17/observations.json';snapshot.parent.mkdir(exist_ok=True)
    if snapshot.exists():registry=json.loads(snapshot.read_text())
    else:
        registry=[r for r in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()) if r['leaderboard_score']>=.8]
        snapshot.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    pool=[];scores=[];names=[]
    for r in registry:
        p=ROOT/'forecasts'/r['file'];raw=p.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()]
        aligned=g[['route','date','hour']].merge(pd.read_csv(p,sep=';'),on=['route','date','hour'],validate='one_to_one')
        pool.append(aligned.prediction.to_numpy());scores.append(r['leaderboard_score']);names.append(r['file'])
    forecasts,meta=posterior(anchor,np.asarray(pool),np.asarray(scores),A,b,T,maxiter=700)
    np.savez_compressed(OUT/'future.npz',**forecasts)
    pred=balanced_round(ipf((1-alpha)*anchor+alpha*forecasts[method],A,b),cons)
    write(g,pred,output)
    pd.DataFrame(dict(file=names,observed=scores,fitted=meta.pop('fitted_scores'))).to_csv(TABLE/'score_fit.csv',index=False)
    (TABLE/'validation_diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
    meta.update(status='unscored',method=method,weight=float(alpha),file=output.name,anchor_score=.91048,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),observed_full_submissions=len(pool),
        l1_distance=int(abs(pred-anchor).sum()),changed_cells=int((pred!=anchor).sum()),
        max_constraint_error=float(abs(np.einsum('ij,j->i',A,pred)-b).max()),
        caveat='Maximum-entropy distribution conditioned on scores; neither individual labels nor an LB gain are observed.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('EXPORTED',meta,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='submission_entropy_scores_v17.csv')
    main(parser.parse_args().out)
