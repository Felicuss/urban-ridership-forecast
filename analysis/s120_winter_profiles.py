"""Include short-context winter training examples, keeping every origin causal."""
import numpy as np
import pandas as pd
from s118_compositional_profiles import Data,ROOT,OUT,TABLE,fit,covariates,fold_arrays,validation_inputs,apply_shape,ipf,balanced_round
from s119_profile_transfer import transfer


def main():
    data=Data();cov=covariates();arrays=fold_arrays();rows=[]
    for key in ['R06','R08','B']:
        a,target,cons=validation_inputs(key,arrays);days=np.unique(target.day);cutoff=int(days.min());y=a['y'];current=np.load(OUT/f'{key}_incumbent.npy')
        for mode in ['cross_entropy','smooth_l1']:
            shares,prior,model=fit(data,cov,cutoff,days,mode,start_day=28)
            np.save(OUT/f'{key}_winter_{mode}.npy',shares)
            for method in ['replace','transfer']:
                for strength in [.1,.25]:
                    raw=apply_shape(current,shares,target,strength) if method=='replace' else transfer(current,shares,prior,target,strength)
                    pred=balanced_round(ipf(raw,a['A'],a['b']),cons)
                    gain=(abs(current-y).sum()-abs(pred-y).sum())/y.sum()
                    rows.append(dict(fold=key,mode=mode,method=method,strength=strength,gain=gain))
            print(key,mode,rows[-4:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'winter.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['mode','method','strength']).gain.agg(['mean','min']);summary.to_csv(TABLE/'winter_selection.csv');print(summary.to_string(),flush=True)

if __name__=='__main__':main()
