from s98_joint_scenarios import *
from s100_markov_entropy import chain_posterior
rows=[]
for key in ['R06','R08','B']:
    a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum();champion=a['champion'];score0=1-abs(champion-y).sum()/total
    for strength in [0.,.4,.8]:
        p,meta=chain_posterior(a['original'],a['pool'],a['scores'],a['A'],a['b'],total,a['mult'],a['factor'],strength=strength)
        np.save(OUT/f'{key}_markov_{strength}.npy',p)
        for weight in [.5,1.]:
            q=ipf((1-weight)*champion+weight*p,a['A'],a['b']);score=1-abs(q-y).sum()/total
            row=dict(fold=key,weight=weight,score=score,gain=score-score0,**meta);rows.append(row);print(row,flush=True)
        pd.DataFrame(rows).to_csv(TABLE/'markov.csv',index=False)
print(pd.DataFrame(rows).groupby(['strength','weight']).gain.agg(['mean','min']),flush=True)
