"""Package prioritized candidates, hashes and checks; never overwrite old submissions."""
from __future__ import annotations

import hashlib
import json
import shutil

import numpy as np
import pandas as pd

from s42_adaptive_profiles import ROOT,OUT,TABLES


def main():
    choices=[
        ('submission_kaggle_v1','residual_calendar_profiles_events_25_incidents',
         'Primary: median windows + 25% L1 residual without weather + measured incident effect.'),
        ('submission_kaggle_v1_weather','residual_with_weather_25_incidents',
         'Second: hourly weather dynamics in the residual learner, not the old weather multiplier.'),
        ('submission_kaggle_profile','profile_median_windows',
         'Ablation: only multi-window profile; all existing s32 rules retained.'),
        ('submission_kaggle_incidents_only','anchor_incidents_only',
         'Ablation: only official incident intervals added to registered best.'),
    ]
    manifest=[]
    anchor=pd.read_csv(ROOT/'forecasts/submission_ex_ante_route5.csv',sep=';')
    for rank,(name,source,description) in enumerate(choices,1):
        path=ROOT/f'forecasts/{name}.csv'
        shutil.copyfile(OUT/f'{source}.csv',path)
        metadata=json.loads((OUT/f'{source}.json').read_text())
        metadata.update(file=path.name,priority=rank,description=description,source_candidate=source,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        df=pd.read_csv(path,sep=';')
        assert list(df.columns)==list(anchor.columns)
        assert df[['route','date','hour']].equals(anchor[['route','date','hour']])
        assert len(df)==14640 and not df.duplicated(['route','date','hour']).any()
        assert np.isfinite(df.prediction).all() and (df.prediction>=0).all()
        assert pd.api.types.is_integer_dtype(df.prediction)
        assert (df.loc[(df.date=='2025-12-31')&(df.hour>=20),'prediction']==0).all()
        assert df.loc[df.route==5,'prediction'].equals(anchor.loc[anchor.route==5,'prediction'])
        manifest.append(metadata)
    # QA says to drop route 5, but the recorded best contains it. Keep the choice explicit.
    df=pd.read_csv(ROOT/'forecasts/submission_kaggle_v1.csv',sep=';')
    df.loc[df.route==5,'prediction']=0
    path=ROOT/'forecasts/submission_kaggle_v1_no_route5.csv'
    df.to_csv(path,sep=';',index=False)
    manifest.append(dict(file=path.name,priority=None,description='QA variant: same primary candidate with route 5 zeroed.',
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest(),leaderboard_score=None,
                         source_candidate='submission_kaggle_v1.csv'))
    results_path=ROOT/'forecasts/leaderboard_results.json'
    results=json.loads(results_path.read_text()) if results_path.exists() else []
    for item in manifest:
        matching=[r for r in results if (r['file'],r['sha256'])==(item['file'],item['sha256'])]
        if matching:
            result=matching[-1]
            for key in ['leaderboard_score','platform_display_number','submitted_at','evidence']:
                item[key]=result.get(key)
    (ROOT/'forecasts/kaggle_round_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    # Comparison uses the same six folds for all model rows, not incompatible means.
    profiles=pd.read_csv(TABLES/'kaggle_profile_backtest.csv')
    residual=pd.read_csv(TABLES/'kaggle_residual_backtest.csv')
    folds=['R04','R05','R06','R07','R08','B']
    records=[]
    for name,variant in [('registered_best_core','median_14d'),('median_windows','median_windows')]:
        for fold in folds:
            value=profiles[(profiles.variant==variant)&(profiles.fold==fold)].iloc[0]
            records.append(dict(model=name,fold=fold,score=value.score))
    for model in ['calendar_profiles_events','with_weather']:
        for row in residual[(residual.model==model)&(residual.blend_weight==.25)].itertuples():
            records.append(dict(model=model+'_25',fold=row.fold,score=row.score))
    comparison=pd.DataFrame(records).pivot(index='model',columns='fold',values='score')
    comparison['mean']=comparison[folds].mean(axis=1)
    comparison['gain_pp_vs_anchor_core']=(comparison['mean']-comparison.loc['registered_best_core','mean'])*100
    comparison.to_csv(TABLES/'kaggle_final_comparison.csv')
    print(comparison.round(6).to_string())
    print('PASS: all packaged candidates have valid grids, finite nonnegative integers and free-fare zeros.')
    print('Primary:',ROOT/'forecasts/submission_kaggle_v1.csv')


if __name__=='__main__':
    main()
