"""Compare volume-weighted entropy with ordinary independent-prior conditioning."""
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
        for power in [0.,.5,1.5]:
            p,meta=posterior(a['original'],pool,scores,a['A'],a['b'],total,noise_multiplier=noise,distribution='mixture',entropy_power=power,maxiter=800)
            for weight in [.5,1.]:
                pred=balanced_round(ipf((1-weight)*champion+weight*p['mean'],a['A'],a['b']),cons)
                score=1-abs(pred-y).sum()/total
                rows.append(dict(fold=key,power=power,weight=weight,score=score,gain=score-score0,fit_rmse=meta['score_rmse']))
            print(rows[-2:],flush=True);pd.DataFrame(rows).to_csv(TABLE/'entropy_weights.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['power','weight']).gain.agg(['mean','min']);summary['selection']=summary['mean']+.5*summary['min'];summary.to_csv(TABLE/'entropy_weights_selection.csv');print(summary,flush=True)

if __name__=='__main__':main()
