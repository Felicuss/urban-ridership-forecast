"""Season-feature regularization for conditional quantiles, inspired by M5."""
from s108_quantile_distribution import *


def main():
    arrays=fold_arrays();history=residual_history(arrays);cov=covariates();rows=[]
    for key in ['R06','R08','B']:
        a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum()
        cons=[(m.astype(bool),v,str(j)) for j,(m,v) in enumerate(zip(a['A'],a['b']))]
        markov=balanced_round(ipf(np.load(OUT/f'{key}_markov_0.8.npy'),a['A'],a['b']),cons)
        pool=np.r_[a['pool'],markov[None]];scores=np.r_[a['scores'],round(float(1-abs(markov-y).sum()/total),5)]
        previous=pool[scores.argmax()]
        v21=balanced_round(ipf(.5*previous+.5*np.load(ROOT/f'data/distributional_noise/{key}_1.0.npy'),a['A'],a['b']),cons)
        pool=np.r_[pool,v21[None]];scores=np.r_[scores,round(float(1-abs(v21-y).sum()/total),5)]
        champion=pool[scores.argmax()];score0=1-abs(champion-y).sum()/total
        f=arrays[key];target=pd.DataFrame(dict(day=f['day'],route=f['route'],hour=np.tile(np.arange(24),len(y)//24),kind=f['kind'],p=a['original']))
        noise,_,_=learn(history,cov,int(f['day'].min()),target)
        ref=np.argmin(abs(pool-a['original']).sum(1));error=(1-scores[ref])*total
        for variant in ['stationary','jitter']:
            q=train_quantiles(history,cov,int(f['day'].min()),target,variant=variant);np.save(CACHE/f'{key}_{variant}_quantiles.npy',q)
            for shrink in [.25,.5]:
                custom=quantile_prior(a['original'],error,q,noise,shrink)
                p,meta=posterior(a['original'],pool,scores,a['A'],a['b'],total,custom_prior=custom,maxiter=800)
                for weight in [.5,1.]:
                    pred=balanced_round(ipf((1-weight)*champion+weight*p['mean'],a['A'],a['b']),cons)
                    score=1-abs(pred-y).sum()/total
                    rows.append(dict(fold=key,variant=variant,shrink=shrink,weight=weight,score=score,gain=score-score0,fit_rmse=meta['score_rmse']))
                print(rows[-2:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'robustness.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['variant','shrink','weight']).gain.agg(['mean','min']);summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'robustness_selection.csv');print(summary,flush=True)

if __name__=='__main__':main()
