"""Compare IPF with diagonal covariance projections at equal information.

Each validation target supplies ONLY prescribed aggregate observations to all
methods equally. This simulates having those aggregates, not a forecast test.
Empirical variances use strictly earlier, deduplicated development residuals.
No submission is generated.
"""
import numpy as np
import pandas as pd
from s52_round4_common import ROOT, fold_arrays
from s86_ml_research_audit import OUT, codes


def constraints(a):
    route=a['route']; day=a['day']; kind=a['kind']; hour=np.tile(np.arange(24),len(day)//24)
    month=(pd.Timestamp('2025-01-01')+pd.to_timedelta(day,unit='D')).month.to_numpy()
    rows=[np.ones(len(day),bool)]
    for m in np.unique(month):
        for r in np.unique(route):
            if r!=5:rows.append((month==m)&(route==r))
        rows.append((month==m)&(route==17)&(kind==0))
    rows.extend([(kind==0)&(route!=17)&np.isin(hour,hs) for hs in [[7,8,9],[16,17,18,19]]])
    return np.asarray(rows,dtype=float)


def ipf(p,A,b):
    q=p.copy()
    for _ in range(300):
        for mask,t in zip(A>0,b):
            s=q[mask].sum()
            if s>0:q[mask]*=t/s
    return q


def projection(p,A,b,variance):
    # Dykstra projection onto affine constraints and nonnegative orthant in
    # variance-standardized coordinates. Structural zero support is fixed.
    scale=np.sqrt(variance)*(p>0)
    M=A*scale[None]
    rownorm=np.maximum(np.sqrt(np.einsum('ij,ij->i',M,M)),1)
    M=M/rownorm[:,None]; target=b/rownorm
    gram=np.einsum('in,jn->ij',M,M)
    eigen,vectors=np.linalg.eigh(gram)
    reciprocal=np.divide(1,eigen,out=np.zeros_like(eigen),where=eigen>max(eigen.max()*1e-10,1e-12))
    inverse=np.einsum('ik,k,jk->ij',vectors,reciprocal,vectors)
    z=np.divide(p,scale,out=np.zeros_like(p),where=scale>0)
    u=np.zeros_like(z);v=np.zeros_like(z)
    for _ in range(400):
        x=z+u
        residual=np.einsum('ij,j->i',M,x)-target
        correction=np.einsum('ij,j->i',inverse,residual)
        y=x-np.einsum('ij,i->j',M,correction)
        u=x-y
        x=y+v
        new=np.maximum(x,0)
        v=x-new
        converged=np.max(abs(new-z))<1e-8
        z=new
        if converged:break
    result=z*scale
    assert np.isfinite(result).all() and (result>=0).all()
    return result


def prior_variance(history,cutoff,a,p):
    prior=history[history.day<cutoff].sort_values('origin').drop_duplicates(['day','route','hour'],keep='last')
    if len(prior)<240*21:return None
    ratio=np.clip((prior.y-prior.p)/(prior.p+50),-1,1)
    prior=prior.assign(square=ratio**2)
    # Smooth sparse route/hour groups toward a pooled prior.
    group=prior.groupby(['route','hour']).square.agg(['sum','count'])
    pooled=float(prior.square.mean())
    value=(group['sum']+30*pooled)/(group['count']+30)
    index=pd.MultiIndex.from_arrays([a['route'],np.tile(np.arange(24),len(p)//24)])
    var=value.reindex(index).fillna(pooled).to_numpy()
    return (p+50)**2*np.maximum(var,.0001)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    arrays=fold_arrays(); hist=[]
    for key,a in arrays.items():
        p=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        hist.append(pd.DataFrame(dict(day=a['day'],route=a['route'],hour=np.tile(np.arange(24),len(p)//24),
            origin=int(a['day'].min())-1,y=a['y'],p=p)))
    history=pd.concat(hist,ignore_index=True);rows=[]
    for key,a in arrays.items():
        p=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1).astype(float)
        y=a['y'];A=constraints(a);b=np.einsum('ij,j->i',A,y)
        variants={'ipf':ipf(p,A,b)}
        variances={'variance_count':p+1,'variance_squared':(p+50)**2}
        empirical=prior_variance(history,int(a['day'].min()),a,p)
        if empirical is not None:variances['variance_empirical']=empirical
        for name,var in variances.items():variants[name]=projection(p,A,b,var)
        for name,q in variants.items():
            regular=(a['route']!=5)&~(np.isin(a['route'],[7,50])&(a['kind']!=0))
            for scope,sel in [('all',np.ones(len(p),bool)),('regular',regular)]:
                score=1-abs(y[sel]-q[sel]).sum()/y[sel].sum()
                ipf_score=1-abs(y[sel]-variants['ipf'][sel]).sum()/y[sel].sum()
                rows.append(dict(fold=key,method=name,scope=scope,score=score,gain_vs_ipf=score-ipf_score,
                    max_constraint_residual=float(abs(np.einsum('ij,j->i',A,q)-b).max()),
                    training_labels_end=int(a['day'].min())-1 if name=='variance_empirical' else None))
        print('RECONCILE',key,flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'reconciliation_pilot.csv',index=False)
    print(frame[frame.scope=='regular'].pivot(index='method',columns='fold',values='gain_vs_ipf').round(6).to_string(),flush=True)


if __name__=='__main__':main()
