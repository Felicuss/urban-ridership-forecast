"""Re-anchor the score-constrained posterior to the best observed submission.

Historical feedback includes the scored Markov iteration before re-anchoring.
"""
import json
import numpy as np
import pandas as pd
from s98_joint_scenarios import ROOT,OUT,ipf,balanced_round
from s93_entropy_scores import posterior
TABLE=ROOT/'docs/analysis/tables/recentered_v21'
CACHE=ROOT/'data/recentered_entropy'


def validate():
    TABLE.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    rows=[]
    for key in ['R06','R08','B']:
        a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum()
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(a['A'],a['b']))]
        markov=balanced_round(ipf(np.load(OUT/f'{key}_markov_0.8.npy'),a['A'],a['b']),cons)
        pool=np.r_[a['pool'],markov[None]];scores=np.r_[a['scores'],round(float(1-abs(markov-y).sum()/total),5)]
        champion=pool[scores.argmax()];score0=1-abs(champion-y).sum()/total
        for family in ['laplace','mixture','student3']:
            p,meta=posterior(champion,pool,scores,a['A'],a['b'],total,noise_multiplier=a['mult'],distribution=family,maxiter=700)
            for weight in [.5,1.]:
                pred=balanced_round(ipf((1-weight)*champion+weight*p['mean'],a['A'],a['b']),cons)
                score=1-abs(pred-y).sum()/total
                rows.append(dict(fold=key,family=family,weight=weight,score=score,gain=score-score0,champion_score=score0,fit_rmse=meta['score_rmse']))
            np.save(CACHE/f'{key}_{family}.npy',p['mean'])
            print(rows[-2:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'validation.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['family','weight']).gain.agg(['mean','min'])
    summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'selection.csv')
    print(summary,flush=True)

if __name__=='__main__':validate()
