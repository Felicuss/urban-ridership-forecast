from s98_joint_scenarios import *
rows=[]
for key in ['R06','R08','B']:
    a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum();champion=a['champion'];score0=1-abs(champion-y).sum()/total
    preds=[]
    for seed in [2026,2027]:
        p,meta=joint_posterior(a['original'],a['pool'],a['scores'],a['A'],a['b'],total,a['mult'],a['factor'],rho=.7,block=6,scenarios=1024,seed=seed,whiten=True,penalty=1e-9)
        preds.append(p)
        q=ipf(.5*champion+.5*p,a['A'],a['b']);score=1-abs(q-y).sum()/total
        rows.append(dict(fold=key,seed=seed,gain=score-score0,**meta));print(rows[-1],flush=True)
    p=np.mean(preds,axis=0);np.save(OUT/f'{key}_joint_ensemble.npy',p)
    q=ipf(.5*champion+.5*p,a['A'],a['b']);score=1-abs(q-y).sum()/total
    rows.append(dict(fold=key,seed='ensemble',gain=score-score0));print(rows[-1],flush=True)
    pd.DataFrame(rows).to_csv(TABLE/'stability.csv',index=False)
