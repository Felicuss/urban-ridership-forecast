"""Route/day-type stacking with purged earlier-period weight fitting.

The global and group weights fit normalized hourly MAE with shrinkage. For
each evaluated period, meta-training excludes every fold whose target dates
overlap that period. Separately report privileged aggregate reconciliation.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from s67_joint_day_net import ROOT, ROUTES, ALL_ROUTES, Data, v7_references
from s74_architecture_round import replacement,raw_predictions

OUT=ROOT/'data/architecture_round9'
MEMBERS=[('graph','shape'),('graph','level'),('chronos500','shape'),
         ('chronos500','level'),('stl_ets','level'),('varx','level')]


def fit_weights(X,error,weights,prior=None,penalty=.001):
    denominator=max(float(weights.sum()),1)
    X=X/1000.;error=error/1000.
    k=X.shape[1];prior=np.zeros(k) if prior is None else np.asarray(prior)
    def objective(w):
        residual=X@w-error
        # Smooth L1 only within one validation count; near-exact global MAE.
        smooth=np.sqrt(residual**2+1e-6)
        value=float((smooth*weights).sum()/denominator)+penalty*((w-prior)**2).sum()
        grad=X.T@(weights*residual/smooth)/denominator+2*penalty*(w-prior)
        return value,grad
    result=minimize(objective,prior,jac=True,method='SLSQP',bounds=[(0,.7)]*k,
         constraints=[dict(type='ineq',fun=lambda w:.8-w.sum(),jac=lambda w:-np.ones(k))],
         options=dict(maxiter=150,ftol=1e-10))
    if not result.success:raise RuntimeError(result.message)
    assert (result.x>=-1e-6).all() and result.x.sum()<=.800001
    return np.maximum(result.x,0)


def build_blocks(data):
    blocks={}
    for key,(a,ref) in v7_references().items():
        start=int(a['day'][0]);kind=data.kind[start:start+len(ref)]
        raw=raw_predictions(key)
        if not all(name in raw for name,_ in MEMBERS):
            raise ValueError(f'Missing model forecasts for {key}')
        deltas=np.stack([replacement(ref,raw[name],kind,mode)-ref for name,mode in MEMBERS],-1)
        routes=np.broadcast_to(np.asarray(ALL_ROUTES)[None,:,None],ref.shape)
        kinds=np.broadcast_to(kind[:,0,None,None],ref.shape)
        day=np.broadcast_to(np.arange(start,start+len(ref))[:,None,None],ref.shape)
        blocks[key]=dict(reference=ref,truth=a['y'].reshape(ref.shape),delta=deltas,
                         day=day,route=routes,kind=kinds,start=start,end=start+len(ref)-1)
    return blocks


def fit_stack(blocks,keys,cutoff):
    if not keys:return dict(global_weights=np.zeros(len(MEMBERS)).tolist(),group_weights={})
    X=np.concatenate([blocks[k]['delta'].reshape(-1,len(MEMBERS)) for k in keys])
    error=np.concatenate([(blocks[k]['truth']-blocks[k]['reference']).reshape(-1) for k in keys])
    day=np.concatenate([blocks[k]['day'].reshape(-1) for k in keys])
    route=np.concatenate([blocks[k]['route'].reshape(-1) for k in keys])
    kind=np.concatenate([blocks[k]['kind'].reshape(-1) for k in keys])
    # Every route/hour of a date repeats equally often across complete folds.
    counts=pd.Series(day).value_counts().to_dict()
    weight=np.array([240/counts[d] for d in day])*2.**(-(cutoff-day)/90)
    active=np.abs(X).sum(-1)>1e-6
    g=fit_weights(X[active],error[active],weight[active],penalty=.003)
    groups={}
    for r in ROUTES:
        for typ in range(3):
            mask=active&(route==r)&(kind==typ)
            if mask.sum()<240:continue
            w=fit_weights(X[mask],error[mask],weight[mask],prior=g,penalty=.03)
            groups[f'{r}_{typ}']=w.tolist()
    return dict(global_weights=g.tolist(),group_weights=groups,training_folds=keys,
                last_training_target=int(day.max()),cutoff=int(cutoff))


def apply_stack(block,parameters):
    weights=np.broadcast_to(parameters['global_weights'],block['delta'].shape).copy()
    for group,w in parameters['group_weights'].items():
        route,kind=map(int,group.split('_'))
        mask=(block['route']==route)&(block['kind']==kind)
        weights[mask]=w
    output=block['reference']+(block['delta']*weights).sum(-1)
    assert np.isfinite(output).all() and (output>=-1e-5).all()
    return np.maximum(output,0)


def reconcile(prediction,day,kind,targets,strength=1.):
    """Mass constraints: whole grid and route-17 workday months; protected fixed.

    Group targets from probes are capped totals, not assumed exact labels.
    Evaluation with true group totals is explicitly an oracle analogue.
    """
    p=prediction.copy();daily=p.sum(-1);flat=daily.reshape(-1)
    months=np.asarray(pd.date_range('2025-01-01',periods=365).month)[day[:,0,0]]
    protected=np.broadcast_to(np.isin(ALL_ROUTES,[5])[None,:],daily.shape).copy()
    protected|=np.isin(ALL_ROUTES,[7,50])[None,:]&(kind[:,0,0,None]!=0)
    free=(~protected)&(daily>0)
    masks=[np.ones(daily.shape,dtype=bool)]
    values=[targets['total']]
    for month,value in targets['route17_workday_month'].items():
        mask=(months[:,None]==int(month))&(np.asarray(ALL_ROUTES)[None,:]==17)&(kind[:,0,0,None]==0)
        if mask.any():masks.append(mask);values.append(value)
    A=np.stack([m.reshape(-1).astype(float) for m in masks])
    variance=(flat/max(float(flat.max()),1.))**2*free.reshape(-1)
    gap=np.asarray(values)-A@flat
    gram=np.einsum('ij,j,kj->ik',A,variance,A,optimize=False)
    coefficient=np.einsum('ij,j->i',np.linalg.pinv(gram),gap,optimize=False)
    shift=variance*np.einsum('ij,i->j',A,coefficient,optimize=False)
    assert np.isfinite(shift).all()
    # Safeguard inconsistent/excessive targets. These are soft constraints.
    shift=np.clip(shift,-.15*flat,.15*flat)*strength
    corrected=np.maximum(flat+shift,0).reshape(daily.shape)
    ratio=np.divide(corrected,daily,out=np.ones_like(daily),where=daily>0)
    p*=ratio[...,None]
    np.testing.assert_array_equal(p[protected],prediction[protected])
    return p


def oracle_targets(block):
    y=block['truth'];day=block['day'];kind=block['kind']
    months=np.asarray(pd.date_range('2025-01-01',periods=365).month)[day[:,0,0]]
    totals={}
    for month in np.unique(months):
        mask=(months[:,None,None]==month)&(block['route']==17)&(kind==0)
        totals[str(month)]=float(y[mask].sum())
    return dict(total=float(y.sum()),route17_workday_month=totals)


def main():
    OUT.mkdir(parents=True,exist_ok=True);data=Data();blocks=build_blocks(data);rows=[];route_rows=[];parameters={}
    for key,block in blocks.items():
        prior=[k for k,b in blocks.items() if b['end']<block['start']]
        fitted=fit_stack(blocks,prior,block['start']-1);parameters[key]=fitted
        prediction=apply_stack(block,fitted);np.save(OUT/f'stack_{key}.npy',prediction)
        variants={'purged_stack':prediction}
        # Aggressive fixed joint replacement is measured, not silently assumed good.
        variants['fixed_graph50_ets50']=block['reference']+.5*block['delta'][...,0]+.5*block['delta'][...,4]
        fixed=variants['fixed_graph50_ets50']
        for route in [0]+ROUTES:
            mask=np.ones_like(fixed,dtype=bool) if not route else block['route']==route
            truth=block['truth'][mask];reference=block['reference'][mask]
            route_rows.append(dict(fold=key,route=route,
                gain=(abs(reference-truth).sum()-abs(fixed[mask]-truth).sum())/truth.sum()))
        for name,p in list(variants.items()):
            variants[name+'_oracle_reconciled']=reconcile(p,block['day'],block['kind'],oracle_targets(block))
        for name,p in variants.items():
            den=block['truth'].sum();referr=abs(block['reference']-block['truth']).sum();err=abs(p-block['truth']).sum()
            rows.append(dict(fold=key,model=name,score=1-err/den,gain=(referr-err)/den,prior_folds=len(prior)))
        print('STACK',key,'prior',prior,'weights',np.round(fitted['global_weights'],3),flush=True)
    final=fit_stack(blocks,list(blocks),303);parameters['future']=final
    (OUT/'stack_weights.json').write_text(json.dumps(dict(members=MEMBERS,parameters=parameters),indent=2)+'\n')
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'stack_validation.csv',index=False)
    pd.DataFrame(route_rows).to_csv(OUT/'fixed_route_validation.csv',index=False)
    print(frame.pivot(index='model',columns='fold',values='gain').round(6).to_string(),flush=True)
    print('FINAL',np.round(final['global_weights'],4),flush=True)


if __name__=='__main__':main()
