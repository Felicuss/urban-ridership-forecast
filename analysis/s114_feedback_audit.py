"""Audit pre-result posterior expectations; do not infer unknown score/file mapping."""
import json
import numpy as np
import pandas as pd
from s113_two_candidates import prepare, SNAPSHOT
from s108_quantile_distribution import quantile_prior
from s93_entropy_scores import posterior
from s84_block_probes import T


def main():
    g,order,inverse,anchor,champ,cons,A,b,pool,scores,noise,q,corr=prepare()
    names=['submission_distributional_v21.csv','submission_centered_quantiles_v22.csv','submission_quantile_shape_v23.csv']
    queries=np.array([pd.read_csv(SNAPSHOT.parent/name,sep=';').prediction.to_numpy(dtype=float)[order] for name in names])
    ref=np.argmin(abs(pool-anchor).sum(1));rows=[]
    for mode in ['centered','quantile_risk']:
        quantiles=q-q[:,5,None] if mode=='centered' else q
        custom=quantile_prior(anchor,(1-scores[ref])*T,quantiles,noise,.5 if mode=='centered' else .25)
        _,meta=posterior(anchor,pool,scores,A,b,T,custom_prior=custom,maxiter=1200,queries=queries)
        for name,score in zip(names,meta['query_scores']):
            rows.append(dict(prior=mode,file=name,expected_score=score,expected_gain_vs_v21=score-meta['query_scores'][0]))
    out=SNAPSHOT/'pre_result_expectations.csv';pd.DataFrame(rows).to_csv(out,index=False)
    print(pd.DataFrame(rows).to_string(index=False),flush=True)

if __name__=='__main__':main()
