"""Four route-17 peak probes with disjoint opposite-month carriers.

build makes seven ordered diagnostic uploads (three existing probes are copied).
score records a user-reported result; apply makes one aggregate-corrected candidate.
Diagnostic files intentionally have low scores and are not ordinary forecasts.
"""
import argparse
import hashlib
import json
import shutil
import numpy as np
import pandas as pd
from s84_block_probes import (ROOT, OUT as OLD, CARRIERS, T, grid, mask, write,
    load_ledger, decoded, margins, rake)

OUT=ROOT/'forecasts/route17_diagnostics'
LEDGER=OUT/'ledger.json'
ANCHOR=ROOT/'forecasts/submission_v11_probe_rake_r3.csv'


def decode_sum(sum_h, score, carrier_score, total=T):
    if not 0 < score <= 1:
        raise ValueError('A clipped/zero probe score cannot identify an aggregate.')
    return (sum_h+(score-carrier_score)*total)/2


def make_probe(g,base,spec,carrier_frame,carrier_spec):
    selected=mask(g,spec); occupied=mask(g,carrier_spec)
    if not selected.any() or (selected & occupied).any():
        raise ValueError('Probe must be nonempty and disjoint from its carrier.')
    pred=g[['route','date','hour']].merge(carrier_frame,on=['route','date','hour'],validate='one_to_one').prediction.to_numpy().copy()
    assert len(pred)==len(g) and np.isfinite(pred).all() and (pred[~occupied]==0).all()
    pred[selected]=np.ceil(2*base[selected]+15).astype(np.int64)
    return pred,selected


def balanced_round(values, cons):
    """Round within identical constraint-membership groups, preserving total."""
    membership=np.stack([m for m,_,_ in cons],axis=1)
    _,group=np.unique(membership,axis=0,return_inverse=True)
    sums=np.bincount(group,weights=values)
    totals=np.floor(sums).astype(np.int64)
    extra=int(np.rint(values.sum())-totals.sum())
    totals[np.argsort(-(sums-totals),kind='stable')[:extra]]+=1
    out=np.floor(values).astype(np.int64)
    for k,target in enumerate(totals):
        cells=np.flatnonzero(group==k)
        n=int(target-out[cells].sum())
        assert 0<=n<=len(cells)
        order=np.argsort(-(values[cells]-out[cells]),kind='stable')
        out[cells[order[:n]]]+=1
    assert out.sum()==int(np.rint(values.sum()))
    assert (out[values==0]==0).all()
    return out


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    previous={r['id']:r for r in json.loads(LEDGER.read_text())} if LEDGER.exists() else {}
    g=grid();base=g[['route','date','hour']].merge(pd.read_csv(ANCHOR,sep=';'),on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    rows=[]
    for month in [11,12]:
        carrier_name='p12' if month==11 else 'p11';carrier=CARRIERS[carrier_name]
        for title,hours in [('morning',[7,8,9]),('evening',[16,17,18,19])]:
            spec=dict(routes=[17],months=[month],kind='wd',hours=hours)
            pred,selected=make_probe(g,base,spec,pd.read_csv(OLD/carrier['file'],sep=';'),carrier['spec'])
            name=f'{len(rows)+1:02d}_r17_{month}_{title}'
            path=OUT/f'{name}.csv';write(g,pred,path)
            rows.append(dict(id=name,file=path.name,spec=spec,carrier=carrier_name,
                carrier_score=carrier['score'],sum_h=int(pred[selected].sum()),
                prior_sum=int(base[selected].sum()),
                expected_score_if_r3_were_truth=carrier['score']+(2*base[selected].sum()-pred[selected].sum())/T,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),score=None))
    old={r['id']:r for r in load_ledger()}
    for number,identifier in [(5,'q14'),(6,'q15'),(7,'q26')]:
        source=old[identifier];name=f'{number:02d}_{identifier}_{source["name"]}'
        path=OUT/f'{name}.csv';shutil.copyfile(OLD/source['file'],path)
        rows.append(dict(id=name,file=path.name,spec=source['spec'],source_id=identifier,
            carrier='p11+p12',carrier_score=sum(c['score'] for c in CARRIERS.values()),
            sum_h=source['sum_h'],prior_sum=source['base_sum'],
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),score=source.get('score')))
    for row in rows:
        if row['id'] in previous:
            prior=previous[row['id']]
            if prior.get('score') is not None and prior['sha256']!=row['sha256']:
                raise ValueError('Cannot reuse score after changing probe bytes')
            row['score']=prior.get('score')
    LEDGER.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print('\n'.join(f"{r['file']}: score={r['score']}" for r in rows))


def apply(output):
    rows=json.loads(LEDGER.read_text())
    g=grid(); measured=decoded(load_ledger()); cons=margins(g,measured)
    used={r['id'] for r in measured};new=[]
    for row in rows:
        if row.get('score') is None or row.get('source_id') in used:
            continue
        path=OUT/row['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        value=decode_sum(row['sum_h'],row['score'],row['carrier_score'])
        if value<0:raise ValueError('Negative decoded target: check file/score matching')
        cons.append((mask(g,row['spec']),value,row['id']))
        new.append(dict(id=row['id'],score=row['score'],estimated_sum=value))
    if not new:raise ValueError('No new scored probes; candidate would add no information.')
    base=g[['route','date','hour']].merge(pd.read_csv(ANCHOR,sep=';'),on=['route','date','hour'],validate='one_to_one').prediction.to_numpy()
    pred=balanced_round(rake(g,cons,base),cons)
    path=ROOT/'forecasts'/output
    if path.exists():raise FileExistsError(path)
    write(g,pred,path)
    meta=dict(status='unscored',anchor=ANCHOR.name,measurements=new,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        max_constraint_error=max(abs(pred[m].sum()-y) for m,y,_ in cons))
    path.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(path)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('build')
    score=sub.add_parser('score');score.add_argument('id');score.add_argument('value',type=float)
    a=sub.add_parser('apply');a.add_argument('--out',default='submission_r17_measured_v13.csv')
    args=p.parse_args()
    if args.command=='build':build()
    elif args.command=='apply':apply(args.out)
    else:
        rows=json.loads(LEDGER.read_text())
        row=next(r for r in rows if r['id']==args.id or r['id'].split('_')[0]==args.id)
        decode_sum(row['sum_h'],args.value,row['carrier_score'])
        row['score']=args.value
        LEDGER.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        print(row['id'],args.value)


if __name__=='__main__':main()
