"""Pair public incident/recovery announcements and estimate a cautious hourly effect.

Publication times are proxies for incident boundaries, not dispatch telemetry.
Effect diagnostics use unaffected hours of each historical day as level controls;
they are not an end-to-end forecasting backtest. No unknown-ended incident is
silently assigned a duration. Network/night rules remain separate hypotheses.
"""
from __future__ import annotations

import json
import re
import numpy as np
import pandas as pd

from s42_adaptive_profiles import Experiment, ROOT, OUT, TABLES, DATES, ROUTES, save_candidate


def extract():
    posts=json.loads((ROOT/'data/deptrans_archive/all_posts.json').read_text())
    events=[]
    for p in posts.values():
        if not p.get('reply_to') or 'восстановлено движение трамва' not in p['text'].lower():
            continue
        parent=posts.get(p['reply_to'].replace('https://t.me/',''))
        if not parent or 'задерживаются трамваи' not in parent['text']:
            continue
        m=re.search(r'№\s*([^\.]+)',parent['text'])
        routes=set(map(int,re.findall(r'\b\d+\b',m[1]))) & set(ROUTES) if m else set()
        if not routes:
            continue
        start=pd.Timestamp(parent['published']).tz_convert('Europe/Moscow')
        end=pd.Timestamp(p['published']).tz_convert('Europe/Moscow')
        if start.year!=2025 or not 0<(end-start).total_seconds()<86400:
            continue
        events.append(dict(event_id=parent['post'].split('/')[-1],routes=';'.join(map(str,sorted(routes))),
                           start_ts=start.isoformat(),end_ts=end.isoformat(),
                           minutes=(end-start).total_seconds()/60,
                           cause=('road_accident' if 'ДТП' in parent['text'] else 'contact_network' if 'контактн' in parent['text']
                                  else 'blocked_tracks' if 'автомобил' in parent['text'] else 'technical_or_unspecified'),
                           location=parent['text'].split('задерживаются')[0].strip(),
                           source_url='https://t.me/'+parent['post'],recovery_url='https://t.me/'+p['post'],
                           boundary_basis='publication_times',confidence='paired_official_announcements'))
    events=pd.DataFrame(events).sort_values('start_ts').drop_duplicates('event_id')
    events.to_csv(ROOT/'external/deptrans_incidents_2025.csv',index=False)
    return events


def exposure(events):
    result=np.zeros((365,10,24))
    identifiers=np.full((365,10,24),'',dtype=object)
    for event in events.itertuples():
        start=pd.Timestamp(event.start_ts).tz_localize(None)
        end=pd.Timestamp(event.end_ts).tz_localize(None)
        for h in pd.date_range(start.floor('h'),end.floor('h'),freq='h'):
            duration=(min(end,h+pd.Timedelta(hours=1))-max(start,h)).total_seconds()/3600
            if duration<=0 or h.year!=2025:
                continue
            d=h.dayofyear-1
            for route in map(int,event.routes.split(';')):
                j=list(ROUTES).index(route)
                result[d,j,h.hour]=min(1,result[d,j,h.hour]+duration)
                identifiers[d,j,h.hour]=str(event.event_id)
    return result,identifiers


def calibrate(exp,ex,ids):
    rows=[]
    for d,j,h in zip(*np.where(ex[:304]>0)):
        prior=np.arange(max(0,d-35),d)
        prior=prior[(exp.kind[prior]==exp.kind[d]) & ~exp.holiday[prior]]
        if len(prior)<3 or exp.holiday[d]:
            continue
        prof=np.median(exp.y[prior,j],axis=0)
        controls=(ex[d,j]==0) & (prof>50) & (np.arange(24)>=6) & (np.arange(24)<=21)
        # Avoid recovery hours in the nuisance daily-level estimate.
        controls &= np.roll(ex[d,j],1)==0
        if controls.sum()<5 or prof[h]<10:
            continue
        level=np.median((exp.y[d,j,controls]+1)/(prof[controls]+1))
        baseline=prof[h]*level
        rows.append(dict(event_id=ids[d,j,h],date=str(DATES[d].date()),route=ROUTES[j],hour=h,
                         exposure=ex[d,j,h],baseline=baseline,y=exp.y[d,j,h]))
    df=pd.DataFrame(rows)
    def choose(frame):
        alphas=np.arange(0,.801,.025)
        errors=[np.abs(frame.y-frame.baseline*(1-a*frame.exposure)).sum() for a in alphas]
        return float(alphas[np.argmin(errors)])
    alpha=choose(df)
    df['loo_alpha']=[choose(df[df.event_id!=event]) for event in df.event_id]
    df['loo_prediction']=df.baseline*(1-df.loo_alpha*df.exposure)
    before=float(np.abs(df.y-df.baseline).sum())
    after=float(np.abs(df.y-df.loo_prediction).sum())
    # Half shrinkage recognises few independent events and uncertain publication delays.
    chosen=alpha*.5 if after<before else 0.
    report=dict(historical_events=int(df.event_id.nunique()),hour_cells=len(df),raw_alpha=alpha,
                deployed_alpha=chosen,baseline_absolute_error=before,leave_event_out_absolute_error=after,
                relative_error_reduction=1-after/before,
                evaluation='Event-cell diagnostic with same-day unaffected-hour controls; NOT a full forecast backtest.')
    df.to_csv(TABLES/'kaggle_incident_diagnostics.csv',index=False)
    (TABLES/'kaggle_incident_calibration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return chosen


def main():
    exp=Experiment()
    events=extract()
    ex,ids=exposure(events)
    alpha=calibrate(exp,ex,ids)
    print('Forecast events:',sum(events.start_ts.str[:10]>='2025-11-01'),flush=True)
    g=exp.grid(np.arange(304,365))
    for base_name in ['profile_median_windows','residual_calendar_profiles_events_25','residual_with_weather_25']:
        sub=pd.read_csv(OUT/f'{base_name}.csv',sep=';',parse_dates=['date'])
        base=g.merge(sub,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
        p=base*(1-alpha*ex[304:].reshape(-1))
        save_candidate(g,p,base_name+'_incidents',f'{base_name} + paired official incident exposure; shrinkage alpha={alpha}.')
    # Separate ablation on registered best allows measuring the external data alone.
    anchor=pd.read_csv(ROOT/'forecasts/submission_ex_ante_route5.csv',sep=';',parse_dates=['date'])
    base=g.merge(anchor,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    save_candidate(g,base*(1-alpha*ex[304:].reshape(-1)),'anchor_incidents_only',
                   f'Registered best + incident exposure only; shrinkage alpha={alpha}.')


if __name__=='__main__':
    main()
