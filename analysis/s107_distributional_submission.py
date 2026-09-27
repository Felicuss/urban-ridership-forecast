"""Export one ordinary submission after joint scenario stability validation."""
import hashlib
from s98_joint_scenarios import *
from s106_distributional_noise import learn,covariates,FEATURES,TABLE
from s93_entropy_scores import posterior
from s84_block_probes import grid,margins,decoded,load_ledger,mask,T,write
from s89_route17_probes import decode_sum
from s67_joint_day_net import Data


def main():
    output=ROOT/'forecasts/submission_distributional_v21.csv'
    if output.exists():raise FileExistsError(output)
    validation=pd.read_csv(TABLE/'validation.csv')
    summary=validation.groupby(['strength','weight']).gain.agg(['mean','min'])
    strength,weight=(summary['mean']+.5*summary['min']).idxmax()
    chosen=validation[(validation.strength==strength)&(validation.weight==weight)]
    assert len(chosen)==3 and chosen.gain.min()>0 and chosen.gain.mean()>.0001
    g=grid();order=g.sort_values(['date','route','hour']).index.to_numpy();inverse=np.argsort(order)
    ordered=g.iloc[order]
    original=pd.read_csv(ROOT/'forecasts/submission_r17_measured_v13.csv',sep=';').prediction.to_numpy(dtype=float)[order]
    champion=pd.read_csv(ROOT/'forecasts/submission_prior_family_v19.csv',sep=';').prediction.to_numpy(dtype=float)[order]
    cons=margins(g,decoded(load_ledger()))
    for r in json.loads((ROOT/'forecasts/route17_diagnostics/ledger.json').read_text()):
        if r.get('score') is not None and not r.get('source_id'):cons.append((mask(g,r['spec']),decode_sum(r['sum_h'],r['score'],r['carrier_score']),r['id']))
    A=np.array([m for m,_,_ in cons],float)[:,order];b=np.array([v for _,v,_ in cons])
    snapshot=ROOT/'forecasts/distributional_v21';snapshot.mkdir(exist_ok=True)
    registry=[r for r in json.loads((ROOT/'forecasts/leaderboard_results.json').read_text()) if r['leaderboard_score']>=.8]
    (snapshot/'observations.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    pool=[];scores=[]
    for r in registry:
        path=ROOT/'forecasts'/r['file'];raw=path.read_bytes()
        assert r['sha256'] in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()]
        frame=ordered[['route','date','hour']].merge(pd.read_csv(path,sep=';'),on=['route','date','hour'],validate='one_to_one',sort=False)
        pool.append(frame.prediction.to_numpy());scores.append(r['leaderboard_score'])
    history=residual_history(fold_arrays());days=(pd.to_datetime(ordered.date)-pd.Timestamp('2025-01-01')).dt.days.to_numpy()
    target=pd.DataFrame(dict(day=days,route=ordered.route.to_numpy(),hour=ordered.hour.to_numpy(),kind=Data().kind[days,0],p=original))
    mult,model,info=learn(history,covariates(),304,target)
    historical_mult,_=uncertainty(history,304,target.route.to_numpy(),target.kind.to_numpy(),target.hour.to_numpy())
    mult=historical_mult**(1-strength)*mult**strength
    forecasts,diagnostic=posterior(original,np.array(pool),np.array(scores),A,b,T,noise_multiplier=mult,distribution='mixture',maxiter=1000)
    diagnostics=[diagnostic];print(diagnostic,flush=True)
    assert diagnostic['score_rmse']<5e-6,diagnostic
    pred=ipf((1-weight)*champion+weight*forecasts['mean'],A,b)[inverse]
    model.booster_.save_model(str(snapshot/'noise_model.txt'))
    pd.DataFrame(dict(feature=FEATURES,importance=model.feature_importances_)).sort_values('importance',ascending=False).to_csv(TABLE/'feature_importance.csv',index=False)
    result=balanced_round(pred,cons)
    original_champion=champion[inverse]
    assert np.all(result[original_champion==0]==0)
    assert len(result)==14640 and np.isfinite(result).all() and (result>=0).all()
    assert not g.duplicated(['route','date','hour']).any()
    error=float(abs(np.einsum('gn,n->g',A[:,inverse],result)-b).max())
    assert error<5,error
    write(g,result,output)
    np.savez_compressed(snapshot/'parameters.npz',multiplier=mult,order=order)
    meta=dict(status='unscored',file=output.name,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        anchor='submission_prior_family_v19.csv',anchor_score=.91255,observed_full_submissions=len(pool),
        model='LightGBM conditional uncertainty with score-constrained posterior',strength=float(strength),weight=float(weight),
        validation_mean_gain=float(chosen.gain.mean()),validation_min_gain=float(chosen.gain.min()),
        changed_cells=int((result!=original_champion).sum()),l1_distance=int(abs(result-original_champion).sum()),
        max_constraint_error=error,diagnostics=diagnostics,noise_model=info,
        caveat='Selected on three reused historical feedback simulations; not an independent evaluation or an observed LB gain.')
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n');print('EXPORTED',meta,flush=True)

if __name__=='__main__':main()
