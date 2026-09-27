from s98_joint_scenarios import *
from s99_constrained_bayes import bayes_action
rows=[]
for key in ['R06','R08','B']:
    a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum();champion=a['champion'];score0=1-abs(champion-y).sum()/total
    f,_=posterior(a['original'],a['pool'],a['scores'],a['A'],a['b'],total,noise_multiplier=a['mult'],distribution='mixture',return_distribution=True)
    p,meta=bayes_action(f['support'],f['probability'],a['A'],a['b'])
    np.save(OUT/f'{key}_bayes.npy',p)
    for weight in [.5,1.]:
        q=ipf((1-weight)*champion+weight*p,a['A'],a['b']);score=1-abs(q-y).sum()/total
        rows.append(dict(fold=key,weight=weight,score=score,gain=score-score0,**meta));print(rows[-1],flush=True)
    pd.DataFrame(rows).to_csv(TABLE/'bayes.csv',index=False)
