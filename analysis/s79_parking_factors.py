"""Research a low-rank relation between parking anomalies and route residuals.

Unlike s78, remove each month's usual parking profile using public covariates
from that month. Actual target-period external data is explicitly permitted.
The supervised PLS mapping sees only tram labels before each evaluation fold.
This diagnostic does not generate a submission.
"""
import numpy as np
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from s67_joint_day_net import v7_references
from s78_parking_signal_research import ROOT, OUT, CACHE, load


def main():
    OUT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    wide,_=load()
    cov=pd.concat([pd.read_parquet(ROOT/'data/neural_training_pack'/name)
        for name in ['history.parquet','future_covariates.parquet']],ignore_index=True)
    calendar=cov[['date','kind']].drop_duplicates().set_index('date').kind
    kind=calendar.reindex(wide.index.normalize()).to_numpy()
    code=wide.index.month*100+kind*24+wide.index.hour
    # Known external data, not tram labels: monthly profile removal is allowed.
    profile=wide.groupby(code).median().reindex(code).set_axis(wide.index)
    anomalies=(wide-profile).fillna(0)
    refs=v7_references();pieces=[]
    for key,(a,p) in refs.items():
        times=pd.Timestamp('2025-01-01')+pd.to_timedelta(a['day'].reshape(-1,10,24)[:,0,0],unit='D')
        idx=pd.date_range(times.min(),periods=len(p)*24,freq='h')
        # time × route order
        pieces.append((times.min(), pd.DataFrame(p.transpose(0,2,1).reshape(-1,10),index=idx),
            pd.DataFrame(a['y'].reshape(p.shape).transpose(0,2,1).reshape(-1,10),index=idx)))
    bp=pd.concat([x[1] for x in sorted(pieces,key=lambda z:z[0])])
    by=pd.concat([x[2] for x in sorted(pieces,key=lambda z:z[0])])
    bp=bp[~bp.index.duplicated(keep='last')];by=by[~by.index.duplicated(keep='last')]
    rows=[]
    for key in ['R06','R07','R08','B']:
        a,p=refs[key];y=a['y'].reshape(p.shape)
        start=pd.Timestamp('2025-01-01')+pd.Timedelta(days=int(a['day'][0]))
        tr=bp.index<start;period=bp.index[tr]
        stats=wide.reindex(period)
        selected=(stats.notna().mean()>.7)&(stats.std()>.03)
        X=anomalies.loc[:,selected]
        xtrain=X.reindex(period).to_numpy()
        target=(by.loc[period]-bp.loc[period])/(bp.loc[period]+100)
        target=target.clip(-.7,.7)
        train_kind=calendar.reindex(period.normalize()).to_numpy()
        group=period.month*100+train_kind*24+period.hour
        target=target-target.groupby(group).transform('median')
        # No fitting of the persistent level on evaluation labels.
        idx=pd.date_range(start,periods=len(p)*24,freq='h')
        xtest=X.reindex(idx).to_numpy()
        for rank in [2,6]:
            model=PLSRegression(n_components=rank,scale=False,max_iter=1000)
            model.fit(xtrain,target.to_numpy())
            delta=model.predict(xtest).reshape(len(p),24,10).transpose(0,2,1)
            assert np.isfinite(delta).all()
            protected=(p<20)
            k=calendar.reindex(pd.date_range(start,periods=len(p))).to_numpy()
            protected[:,[2,9],:] |= (k!=0)[:,None,None]
            for weight in [.25,.5,1.]:
                raw=p+weight*np.clip(delta,-.3,.3)*(p+100)
                raw[protected]=p[protected];raw=np.maximum(0,raw)
                shape=raw*np.divide(p.sum(-1,keepdims=True),raw.sum(-1,keepdims=True),
                    out=np.ones_like(p.sum(-1,keepdims=True)),where=raw.sum(-1,keepdims=True)>0)
                for mode,values in [('joint',raw),('shape',shape)]:
                    rows.append(dict(fold=key,rank=rank,weight=weight,mode=mode,
                        gain=(abs(p-y).sum()-abs(values-y).sum())/y.sum(),
                        score=1-abs(values-y).sum()/y.sum()))
        print(key,'PLS done',flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'parking_factor_ablation.csv',index=False)
    print(frame.pivot(index=['rank','weight','mode'],columns='fold',values='gain').round(6).to_string())


if __name__=='__main__':main()
