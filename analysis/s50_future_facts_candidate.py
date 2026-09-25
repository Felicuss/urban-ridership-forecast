"""One aggressive ex-post candidate using public ridership facts.

City anomaly strength is chosen on reused development folds. Removing the new
T1 service from city totals requires a modeled counterfactual for route 90.
Neither that adjustment nor the route 5 press-total transfer has been validated
against hidden labels. Keep v2 as the registered champion until an actual score.
"""
from __future__ import annotations

import hashlib
import json
import numpy as np
import pandas as pd

from s42_adaptive_profiles import ROOT, TABLES, Experiment, DATES
from s49_future_city_probe import monthly_indices


def main():
    exp=Experiment()
    facts={x['id']:x for x in json.loads((ROOT/'external/future_ridership_facts.json').read_text())['facts']}
    anchor_path=ROOT/'forecasts/submission_kaggle_unified_v2.csv'
    anchor_hash=hashlib.sha256(anchor_path.read_bytes()).hexdigest()
    assert anchor_hash=='dcf149b828e1272a2b7004705e239abaf7d1291c4a645480c16f53d616eb334b'
    sub=pd.read_csv(anchor_path,sep=';',parse_dates=['date'])
    is5=sub.route==5
    ts=sub.date+pd.to_timedelta(sub.hour,unit='h')
    first_week=is5&(ts>='2025-12-16 18:00')&(ts<'2025-12-23 18:00')
    route5_denominator=int(sub.loc[first_week,'prediction'].sum())
    scale5=facts['route5_first_week']['value']/route5_denominator
    indices,weights=monthly_indices(exp,303)
    dayweight=np.array(weights)[exp.kind]*exp.calendar_factor
    # Interpret "first month" as launch date inclusive to monthly anniversary
    # exclusive. Publication dates and rounded totals do not supply daily labels.
    t1_first=(DATES>='2025-11-12')&(DATES<'2025-12-12')
    t1_level=facts['t1_first_month']['value']/dayweight[t1_first].sum()
    r90_first=(DATES>='2025-09-10')&(DATES<'2025-10-10')
    r90_level=facts['route90_first_month']['value']/dayweight[r90_first].sum()
    t1=np.where(DATES>='2025-11-12',dayweight*t1_level,0.)
    t1[DATES>='2025-12-12']=dayweight[DATES>='2025-12-12']*facts['t1_weekday_january_report']['value']
    counterfactual90=np.where(DATES>='2025-11-12',dayweight*r90_level,0.)
    net=t1-counterfactual90

    # Aggressive but bounded rule, declared here: choose max mean improvement
    # with >=5/6 positive folds and no fold loss exceeding 0.002. 20 source/weight
    # combinations were examined in s49; this is not an independent validation.
    probe=pd.read_csv(TABLES/'future_city_probe.csv')
    summary=probe.groupby(['source','strength']).gain.agg(['mean','min',lambda x:int((x>0).sum())])
    summary.columns=['mean_gain','worst_gain','wins']
    eligible=summary[(summary.wins>=5)&(summary.worst_gain>=-.002)&(summary.mean_gain>0)]
    choice=eligible.sort_values('mean_gain',ascending=False).index[0]
    source,strength=choice
    assert source=='tram','Reassess network correction if another transport source wins'
    city=pd.read_csv(ROOT/'external/datamos_62521_monthly_ridership.csv')
    city=city[(city.transport=='Трамвай')&(city.year==2025)].set_index('month').passengers
    monthly=[]
    factors={}
    for month in (11,12):
        m=exp.month==month
        # Remove gross T1 and restore its replaced route 90 counterfactual, so
        # comparison approximately retains the October network. Subtract new 5
        # as well, since it is calibrated separately below.
        new5=float(np.rint(sub.loc[is5&(sub.date.dt.month==month),'prediction']*scale5).sum())
        addition=float(net[m].sum())+new5
        anomaly=float(indices[source][month-1])*(1-addition/float(city[month]))
        factor=anomaly**strength
        factors[month]=factor
        monthly.append(dict(month=month,city_observed=int(city[month]),t1_gross_estimate=float(t1[m].sum()),
            replaced90_estimate=float(counterfactual90[m].sum()),route5_removed_estimate=new5,
            city_anomaly_unadjusted=float(indices[source][month-1]),
            city_anomaly_network_adjusted=anomaly,deployed_multiplier=factor))
    out=sub.copy()
    out.loc[~is5,'prediction']=np.rint(out.loc[~is5,'prediction']*out.loc[~is5,'date'].dt.month.map(factors)).astype('int64')
    # Seven elapsed days from assumed opening hour to publication hour. This
    # window is a modeling interpretation, not an exact timestamp from the post.
    out.loc[is5,'prediction']=np.rint(sub.loc[is5,'prediction']*scale5).astype('int64')
    assert len(out)==14640 and not out.duplicated(['route','date','hour']).any()
    assert out[['route','date','hour']].equals(sub[['route','date','hour']])
    assert np.isfinite(out.prediction).all() and (out.prediction>=0).all()
    assert (out.loc[(out.date==pd.Timestamp('2025-12-31'))&(out.hour>=20),'prediction']==0).all()
    assert (out.loc[is5&(ts<'2025-12-16 18:00'),'prediction']==0).all()
    assert hashlib.sha256(anchor_path.read_bytes()).hexdigest()==anchor_hash
    path=ROOT/'forecasts/submission_future_facts_v3.csv'
    out.date=out.date.dt.strftime('%Y-%m-%d')
    out.to_csv(path,sep=';',index=False)
    diff=out.prediction.to_numpy()-sub.prediction.to_numpy()
    metadata=dict(status='unscored_experimental',file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        anchor=anchor_path.name,anchor_score=.90358,anchor_sha256=anchor_hash,
        information_policy='Intentional permitted post-cutoff public facts; no hidden hourly target labels.',
        strength=float(strength),selection_rule='>=5/6 gains; worst >=-0.002; maximize mean gain; 20 source/strength combinations',
        development=summary.loc[choice].to_dict(),monthly=monthly,
        route5=dict(scale=scale5,reference_window_start='2025-12-16 18:00',reference_window_end_exclusive='2025-12-23 18:00',
                    baseline_in_reference_window=route5_denominator,reported_first_week=40000,
                    prediction_first_week=int(out.loc[first_week,'prediction'].sum()),
                    cutoff_uncertainty='Press report gives first week, not exact timestamps; 16–22 versus 17–23 December imply different factors.'),
        caveats=['Development scores validate only aggregate anomaly transfer, not November network adjustment or route 5.',
                 'T1 gross and replaced route 90 counterfactual are estimates from rounded public totals.',
                 'Published passenger trips are not proven identical to paid successful validations.',
                 'Same temporal folds reused for model development; no independent holdout.'],
        changed_rows=int((diff!=0).sum()),sum_difference=int(diff.sum()),absolute_difference=int(np.abs(diff).sum()))
    registry=ROOT/'forecasts/leaderboard_results.json'
    if registry.exists():
        for result in json.loads(registry.read_text()):
            if (result['file'],result['sha256'])==(metadata['file'],metadata['sha256']):
                metadata['leaderboard_score']=result['leaderboard_score']
                metadata['evidence']=result.get('evidence')
                if result['leaderboard_score'] is not None:
                    metadata['status']=('scored_rejected' if result['leaderboard_score']<metadata['anchor_score'] else 'scored')
    (ROOT/'forecasts/kaggle_round/future_facts_v3.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    pd.DataFrame(monthly).to_csv(TABLES/'future_facts_network_adjustment.csv',index=False)
    print(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
