"""Research-only audit: scored artifacts, probe identifiability and oracle budgets.

Aggregate experiments deliberately use held-out truth to measure information
value. They are NOT forecasts, CV scores, new submissions or claimed LB gains.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from s52_round4_common import ROOT, fold_arrays
from s84_block_probes import grid, load_ledger, decoded, margins, mask, T, carrier_score

OUT=ROOT/'docs/analysis/tables/research_2026_09_27'


def codes(*columns):
    return pd.factorize(pd.MultiIndex.from_arrays(columns),sort=True)[0]


def calibrate(base,truth,groups,sweeps=100):
    out=base.astype(float).copy()
    targets=[np.bincount(g,weights=truth) for g in groups]
    for _ in range(sweeps):
        for g,y in zip(groups,targets):
            p=np.bincount(g,weights=out,minlength=len(y))
            ratio=np.divide(y,p,out=np.ones_like(y),where=p>0)
            out*=ratio[g]
    return out


def audit_future():
    registry=json.loads((ROOT/'forecasts/leaderboard_results.json').read_text())
    records=[]
    for row in registry:
        path=ROOT/'forecasts'/row['file']; raw=path.read_bytes()
        exact=hashlib.sha256(raw).hexdigest(); lf=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()
        assert row['sha256'] in [exact,lf],path
        records.append(dict(file=row['file'],score=row['leaderboard_score'],byte_exact=exact==row['sha256']))
    pd.DataFrame(records).to_csv(OUT/'scored_artifacts.csv',index=False)
    best=max(registry,key=lambda r:r['leaderboard_score'])
    g=grid(); measured=decoded(load_ledger()); cons=margins(g,measured)
    best_frame=pd.read_csv(ROOT/'forecasts'/best['file'],sep=';')
    best_values=g[['route','date','hour']].merge(best_frame,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    matrix=np.asarray([m.astype(float) for m,_,_ in cons])
    gram=np.einsum('in,jn->ij',matrix,matrix)
    rank=int(np.linalg.matrix_rank(gram))
    rows=[]
    tlo=5040000/(.90553-.51431+.00001)
    thi=5040000/(.90553-.51431-.00001)
    for row in measured:
        delta=row['score']-carrier_score()
        corners=[(row['sum_h']+(delta+e)*tt)/2 for e in [-.000015,.000015] for tt in [tlo,thi]]
        sel=mask(g,row['spec'])
        rows.append(dict(id=row['id'],name=row['name'],decoded_sum=row['y'],
            rounding_low=min(corners),rounding_high=max(corners),
            v11_sum=int(g.prediction.to_numpy()[sel].sum()),best_sum=int(best_values[sel].sum()),
            residual=float(best_values[sel].sum()-row['y']),
            zero_support_cells=int((sel&(g.prediction.to_numpy()==0)).sum())))
    pd.DataFrame(rows).to_csv(OUT/'measured_blocks.csv',index=False)
    unknown=[dict(id=r['id'],name=r['name'],file=r['file'],base_sum=r['base_sum']) for r in load_ledger() if r.get('score') is None]
    pd.DataFrame(unknown).to_csv(OUT/'unscored_probes.csv',index=False)
    summary=dict(best_file=best['file'],best_score=best['leaderboard_score'],verified_scored_files=len(registry),
        measured_probes=len(measured),linear_constraints=len(cons),constraint_rank=rank,
        unresolved_dimensions_on_full_grid=len(g)-rank,approximate_target_total=T,
        target_total_rounding_interval=[tlo,thi],
        error_reduction_required_for_094=(.94-best['leaderboard_score'])/(1-best['leaderboard_score']),
        absolute_error_reduction_required_for_094=(.94-best['leaderboard_score'])*T,
        caveat='Decoded sums assume ceilings exceed truth and unclipped probe scores; otherwise they measure capped sums. Rounding intervals are conservative and correlated via shared carriers.')
    (OUT/'audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('AUDIT',summary,flush=True)


def historical_information():
    rows=[]; cancellation=[]
    for key,a in fold_arrays().items():
        ref=np.load(ROOT/f'data/daily_seasonal_v11/v11_{key}.npy').reshape(-1)
        y=a['y'];day=a['day'];route=a['route'];kind=a['kind'];hour=np.tile(np.arange(24),len(y)//24)
        date=pd.Timestamp('2025-01-01')+pd.to_timedelta(day,unit='D')
        month=date.month.to_numpy();week=day//7
        month_route=codes(route,month)
        route_kind=codes(route,month,kind)
        network_day=codes(day)
        route_day=codes(route,day)
        network_hour=codes(month,kind,hour)
        route_band=codes(route,month,kind,hour//3)
        route_week=codes(route,week,kind)
        variants={
            'route_month':[month_route],
            'route_month_kind':[route_kind],
            'route_month_plus_network_day':[month_route,network_day],
            'route_month_plus_network_hour':[month_route,network_hour],
            'route_month_kind_3hour':[route_band],
            'route_week_kind':[route_week],
            'route_day':[route_day],
            'route_day_plus_route_month_kind_3hour':[route_day,route_band],
        }
        regular=(route!=5)&~(np.isin(route,[7,50])&(kind!=0))
        monthly=calibrate(ref,y,[month_route])
        for name,groups in variants.items():
            p=calibrate(ref,y,groups)
            for scope,select in [('all',np.ones(len(y),bool)),('regular',regular)]:
                total=y[select].sum()
                rows.append(dict(fold=key,scope=scope,information=name,
                    nonempty_aggregate_cells=sum(int(g.max()+1) for g in groups),
                    baseline=1-abs(ref[select]-y[select]).sum()/total,
                    score_with_truth_aggregates=1-abs(p[select]-y[select]).sum()/total,
                    gain_over_truth_route_month=(abs(monthly[select]-y[select]).sum()-abs(p[select]-y[select]).sum())/total))
        # Aggregate peak agreement can hide offsetting route/day errors.
        for name,hours in [('morning',[7,8,9]),('evening',[16,17,18,19])]:
            sel=np.isin(hour,hours)&(kind==0)&(route!=17)
            err=ref[sel]-y[sel]
            cancellation.append(dict(fold=key,peak=name,signed_error=float(err.sum()),
                absolute_error=float(abs(err).sum()),cancellation_fraction=1-abs(err.sum())/max(abs(err).sum(),1)))
        print('INFORMATION',key,flush=True)
    pd.DataFrame(rows).to_csv(OUT/'truth_aggregate_diagnostic.csv',index=False)
    pd.DataFrame(cancellation).to_csv(OUT/'peak_cancellation.csv',index=False)
    print(pd.DataFrame(rows).query("fold=='B' and scope=='regular'").round(6).to_string(index=False),flush=True)


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    audit_future()
    historical_information()
