"""Audit recovery-hour residuals with held-out incidents, not target-label training.

Same-day controls make this an event-effect diagnostic, not a forecast CV score.
"""
import json
import numpy as np
import pandas as pd
from s52_round4_common import ROOT,Experiment,ROUTES,DATES
from s45_incident_adjustment import exposure

TABLE=ROOT/'docs/analysis/tables/external_audit_v21'


def fit(frame):
    # Scalar LAD slope with weak shrinkage toward no additional correction.
    x=(frame.baseline*frame.recovery).to_numpy();y=(frame.y-frame.baseline).to_numpy()
    grid=np.linspace(-.5,.5,201)
    errors=np.array([abs(y-v*x).sum()+.05*abs(v)*abs(x).sum() for v in grid])
    return float(grid[errors.argmin()])


def main():
    TABLE.mkdir(parents=True,exist_ok=True)
    events=pd.read_csv(ROOT/'external/deptrans_incidents_2025.csv');ex,ids=exposure(events)
    exp=Experiment();rows=[]
    # Two-hour post-restoration window, exposure decays linearly to zero.
    recovery=np.zeros_like(ex);eventids=np.full(ex.shape,'',dtype=object)
    for event in events.itertuples():
        end=pd.Timestamp(event.end_ts).tz_localize(None)
        for hour in pd.date_range(end.floor('h'),(end+pd.Timedelta(hours=2)).floor('h'),freq='h'):
            left=max(0,(hour-end).total_seconds()/3600);right=min(2,(hour+pd.Timedelta(hours=1)-end).total_seconds()/3600)
            if right<=left or hour.year!=2025:continue
            value=(right-left)-(right*right-left*left)/4
            for route in map(int,event.routes.split(';')):
                j=list(ROUTES).index(route);d=hour.dayofyear-1
                recovery[d,j,hour.hour]=max(recovery[d,j,hour.hour],value);eventids[d,j,hour.hour]=str(event.event_id)
    for d,j,h in zip(*np.where(recovery[:304]>0)):
        prior=np.arange(max(0,d-35),d);prior=prior[(exp.kind[prior]==exp.kind[d])&~exp.holiday[prior]]
        if len(prior)<3 or exp.holiday[d]:continue
        prof=np.median(exp.y[prior,j],axis=0)
        controls=(ex[d,j]==0)&(recovery[d,j]==0)&(prof>50)&(np.arange(24)>=6)&(np.arange(24)<=21)
        if controls.sum()<5 or prof[h]<10 or ex[d,j,h]>0:continue
        level=np.median((exp.y[d,j,controls]+1)/(prof[controls]+1))
        rows.append(dict(event_id=eventids[d,j,h],date=str(DATES[d].date()),route=int(ROUTES[j]),hour=int(h),baseline=float(prof[h]*level),y=float(exp.y[d,j,h]),recovery=float(recovery[d,j,h])))
    frame=pd.DataFrame(rows)
    frame['loo_slope']=[fit(frame[frame.event_id!=e]) for e in frame.event_id]
    frame['prediction']=frame.baseline*(1+frame.loo_slope*frame.recovery)
    frame['gain_abs']=abs(frame.y-frame.baseline)-abs(frame.y-frame.prediction)
    frame.to_csv(TABLE/'recovery_leave_event_out.csv',index=False)
    byevent=frame.groupby('event_id').gain_abs.sum();byevent.to_csv(TABLE/'recovery_event_gains.csv')
    report=dict(events=int(frame.event_id.nunique()),cells=len(frame),coefficient_all=fit(frame),
        baseline_absolute_error=float(abs(frame.y-frame.baseline).sum()),loo_absolute_error=float(abs(frame.y-frame.prediction).sum()),
        error_reduction=float(frame.gain_abs.sum()),events_improved=int((byevent>0).sum()),
        caveat='Same-day controls, leave-event-out effect diagnostic; NOT forecast CV or predicted LB improvement.')
    # Bootstrap events, not correlated hours.
    rng=np.random.default_rng(42);samples=rng.choice(byevent.to_numpy(),size=(10000,len(byevent))).sum(1)
    report['event_bootstrap_gain_95']=np.quantile(samples,[.025,.975]).tolist()
    report['status']='supported_diagnostic' if report['event_bootstrap_gain_95'][0]>0 else 'rejected_no_reliable_increment'
    (TABLE/'recovery_diagnostic.json').write_text(json.dumps(report,indent=2)+'\n')
    # Quantify scope on the champion without mutating or stacking an existing effect.
    champion=pd.read_csv(ROOT/'forecasts/submission_prior_family_v19.csv',sep=';')
    dates=pd.to_datetime(champion.date).dt.dayofyear.to_numpy()-1
    routes=np.array([list(ROUTES).index(r) for r in champion.route]);hours=champion.hour.to_numpy()
    champion['incident_exposure']=ex[dates,routes,hours];champion['recovery_exposure']=recovery[dates,routes,hours]
    champion[ (champion.incident_exposure>0)|(champion.recovery_exposure>0)].to_csv(TABLE/'champion_event_cells.csv',index=False)
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
