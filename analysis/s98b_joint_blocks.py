from s98_joint_scenarios import *
rows=[]
for key in ['R06','R08','B']:
    a=np.load(OUT/f'validation_{key}.npz');y=a['y'];total=y.sum();champion=a['champion'];champion_score=1-abs(champion-y).sum()/total
    for block in [6,24]:
        for rho in [.35,.7]:
            p,meta=joint_posterior(a['original'],a['pool'],a['scores'],a['A'],a['b'],total,a['mult'],a['factor'],rho=rho,block=block,scenarios=512)
            np.save(OUT/f'{key}_block{block}_rho{rho}.npy',p)
            for weight in [.5,1.]:
                q=ipf((1-weight)*champion+weight*p,a['A'],a['b']);score=1-abs(q-y).sum()/total
                row=dict(fold=key,block=block,weight=weight,score=score,gain=score-champion_score,**meta);rows.append(row);print(row,flush=True)
            pd.DataFrame(rows).to_csv(TABLE/'blocks.csv',index=False)
print(pd.DataFrame(rows).groupby(['block','rho','weight']).gain.agg(['mean','min']),flush=True)
