"""Transfer only learned log-share corrections onto the strong incumbent."""
import numpy as np
import pandas as pd
from s118_compositional_profiles import Data,ROUTES,ALL_ROUTES,ROOT,OUT,TABLE,causal_prior,fold_arrays,validation_inputs,ipf,balanced_round


def transfer(current,shares,prior,target,strength):
    p=np.asarray(current,dtype=float).reshape(-1,10,24);result=p.copy()
    for ri,route in enumerate(ROUTES):
        j=ALL_ROUTES.index(route)
        delta=np.clip(np.log(np.maximum(shares[:,ri],1e-8)/np.maximum(prior[:,ri],1e-8)),-.35,.35)
        q=p[:,j]*np.exp(strength*delta)
        q*=p[:,j].sum(1,keepdims=True)/np.maximum(q.sum(1,keepdims=True),1e-12)
        result[:,j]=q
    protected=(target.route.isin([7,50])&(target.kind!=0)).to_numpy().reshape(-1,10,24)
    result[protected]=p[protected]
    return result.reshape(-1)


def main():
    data=Data();arrays=fold_arrays();rows=[]
    for key in ['R06','R08','B']:
        a,target,cons=validation_inputs(key,arrays);days=np.unique(target.day);cutoff=int(days.min());y=a['y'];current=np.load(OUT/f'{key}_incumbent.npy')
        prior=np.array([causal_prior(data,day,cutoff) for day in days])
        for mode in ['cross_entropy','smooth_l1']:
            shares=np.load(OUT/f'{key}_{mode}.npy')
            for strength in [.25,.5,1.]:
                pred=balanced_round(ipf(transfer(current,shares,prior,target,strength),a['A'],a['b']),cons)
                gain=(abs(current-y).sum()-abs(pred-y).sum())/y.sum()
                rows.append(dict(fold=key,mode=mode,strength=strength,gain=gain))
    table=pd.DataFrame(rows);table.to_csv(TABLE/'transfer.csv',index=False)
    summary=table.groupby(['mode','strength']).gain.agg(['mean','min']);summary.to_csv(TABLE/'transfer_selection.csv');print(table.to_string(index=False));print(summary.to_string())

if __name__=='__main__':main()
