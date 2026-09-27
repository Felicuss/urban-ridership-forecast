"""Export exactly two user-requested final candidates with distinct risk profiles."""
import json, hashlib
import numpy as np
import pandas as pd
from s113_two_candidates import prepare
from s118_compositional_profiles import Data, fit, covariates
from s119_profile_transfer import transfer
from s108_quantile_distribution import ROOT, ipf, balanced_round
from s93_entropy_scores import posterior
from s84_block_probes import T,write


def main():
    names=['submission_final_feedback_v25.csv','submission_final_profile_v26.csv']
    for name in names:
        if (ROOT/'forecasts'/name).exists():raise FileExistsError(name)
    dest=ROOT/'forecasts/final_two_candidates';dest.mkdir(exist_ok=True)
    g,order,inverse,anchor,champ,cons,A,b,pool,scores,noise,q,corr=prepare()
    registry=json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    for name in ['submission_centered_quantiles_v22.csv','submission_quantile_shape_v23.csv','submission_feedback_v24.csv']:
        row=next(r for r in registry if r['file']==name);path=ROOT/'forecasts'/name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        f=pd.read_csv(path,sep=';');pd.testing.assert_frame_equal(f[['route','date','hour']],g[['route','date','hour']],check_dtype=False)
        pool=np.r_[pool,f.prediction.to_numpy(dtype=float)[order][None]];scores=np.r_[scores,row['leaderboard_score']]
    (dest/'observations.json').write_text(json.dumps([r for r in registry if r['leaderboard_score']>=.8],ensure_ascii=False,indent=2)+'\n')
    pred,meta=posterior(anchor,pool,scores,A,b,T,noise_multiplier=noise,distribution='mixture',maxiter=1400)
    assert meta['score_rmse']<5e-6
    first=balanced_round(ipf(pred['mean'],A,b)[inverse],cons)
    print('Feedback posterior ready',meta['score_rmse'],flush=True)
    data=Data();days=np.arange(304,365)
    shares,prior,model=fit(data,covariates(),304,days,'smooth_l1',start_day=60)
    model.save_model(str(dest/'compositional_model.txt'))
    ordered=g.iloc[order];target=pd.DataFrame(dict(route=ordered.route.to_numpy(),kind=np.repeat(data.kind[days,0],240)))
    corrected=transfer(first[order],shares,prior,target,.25)
    second=balanced_round(ipf(corrected,A,b)[inverse],cons)
    np.savez_compressed(dest/'parameters.npz',order=order,shares=shares,causal_prior=prior,noise=noise,feedback_mean=pred['mean'])
    for name,values,method in zip(names,[first,second],['updated original mixture posterior','updated posterior plus grouped-softmax profile correction']):
        assert len(values)==14640 and np.isfinite(values).all() and (values>=0).all() and (values==np.floor(values)).all()
        assert not g.duplicated(['route','date','hour']).any()
        assert (values[champ[inverse]==0]==0).all()
        error=float(abs(np.einsum('gn,n->g',A[:,inverse],values)-b).max());assert error<5
        assert not np.array_equal(values,champ[inverse])
        output=ROOT/'forecasts'/name;write(g,values,output)
        info=dict(status='unscored',file=name,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),anchor='submission_distributional_v21.csv',anchor_score=.91263,method=method,observed_full_submissions=len(pool),changed_cells=int((values!=champ[inverse]).sum()),l1_distance=int(abs(values-champ[inverse]).sum()),max_constraint_error=error,feedback_diagnostics=meta)
        if name==names[0]:
            info.update(model_expected_gain_range=[.000021311528887169218,.00006535276395272539],caveat='Model expectation sensitivity, not independent validation or LB; large improvement not established.')
        else:
            info.update(profile_strength=.25,profile_loss='smooth_l1',profile_training_cutoff=304,profile_validation_mean_gain=float(pd.read_csv(ROOT/'docs/analysis/tables/compositional_profiles_v25/transfer_selection.csv').query("mode == 'smooth_l1' and strength == 0.25")['mean'].iloc[0]),profile_validation_min_gain=float(pd.read_csv(ROOT/'docs/analysis/tables/compositional_profiles_v25/transfer_selection.csv').query("mode == 'smooth_l1' and strength == 0.25")['min'].iloc[0]),caveat='Risky: profile component lost on autumn folds; this final combination with refreshed feedback has no independent historical validation or observed LB.')
        output.with_suffix('.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
        print('EXPORTED',name,info['sha256'],info['changed_cells'],info['l1_distance'],flush=True)
    assert not np.array_equal(first,second)
    print('Pair distance',int(abs(first-second).sum()),flush=True)

if __name__=='__main__':main()
