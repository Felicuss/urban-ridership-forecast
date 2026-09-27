"""Combine historical noise with epistemic disagreement of observed predictors."""
import numpy as np
import pandas as pd
from s98_joint_scenarios import ROOT,OUT,ipf,balanced_round
from s93_entropy_scores import posterior
TABLE=ROOT/'docs/analysis/tables/ensemble_uncertainty_v21'
CACHE=ROOT/'data/ensemble_uncertainty'


def disagreement(anchor,pool,scores,power):
    weights=np.exp(np.clip((scores-scores.max())/.003,-30,0));weights/=weights.sum()
    # Weighted spread of *relative* model predictions; floor avoids collapsing
    # uncertainty simply because all models share the same systematic bias.
    relative=np.clip((pool-anchor)/(anchor+30),-1,1)
    mean=np.einsum('j,jn->n',weights,relative)
    variance=np.einsum('j,jn->n',weights,(relative-mean)**2)
    spread=np.sqrt(variance+.02**2)
    geometric=np.exp(np.average(np.log(spread),weights=anchor+30))
    return np.clip((spread/geometric)**power,.5,2.)


def main():
    TABLE.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True);rows=[]
    for key in ['R06','R08','B']:
        a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum()
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(a['A'],a['b']))]
        markov=balanced_round(ipf(np.load(OUT/f'{key}_markov_0.8.npy'),a['A'],a['b']),cons)
        pool=np.r_[a['pool'],markov[None]];scores=np.r_[a['scores'],round(float(1-abs(markov-y).sum()/total),5)]
        champion=pool[scores.argmax()];score0=1-abs(champion-y).sum()/total
        for power in [-.5,.5,1.]:
            mult=a['mult']*disagreement(a['original'],pool,scores,power)
            pred,meta=posterior(a['original'],pool,scores,a['A'],a['b'],total,noise_multiplier=mult,distribution='mixture',maxiter=700)
            for weight in [.5,1.]:
                p=balanced_round(ipf((1-weight)*champion+weight*pred['mean'],a['A'],a['b']),cons)
                score=1-abs(p-y).sum()/total
                rows.append(dict(fold=key,power=power,weight=weight,score=score,gain=score-score0,fit_rmse=meta['score_rmse']))
            np.save(CACHE/f'{key}_{power}.npy',pred['mean']);print(rows[-2:],flush=True)
            pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['power','weight']).gain.agg(['mean','min']);summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv');print(summary,flush=True)

if __name__=='__main__':main()
