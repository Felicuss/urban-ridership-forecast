"""Exact forward-backward inference for score-conditioned hourly Markov chains."""
import numpy as np
from scipy.special import ndtri,logsumexp
from scipy.optimize import minimize
from s93_entropy_scores import prior_grid


def chain_posterior(anchor,pool,scores,A,b,total,multiplier,factor,strength=.5,block=6,maxiter=500):
    n=len(anchor);d=n//block
    support,prior,noise=prior_grid(anchor,(1-scores[np.argmin(abs(pool-anchor).sum(1))])*total,multiplier,distribution='mixture')
    k=len(prior);reference=np.argmin(abs(pool-anchor).sum(1));keep=[i for i in range(len(pool)) if i!=reference]
    weights=(anchor.reshape(d,block)+30).sum(1);weights/=weights.sum()
    z=ndtri(prior.cumsum()-prior/2)
    corr=np.einsum('is,js->ij',factor,factor)
    channels=factor.shape[0];rho=[]
    for i in range(n):
        if i%block!=block-1:rho.append(np.clip(corr[i%channels,(i+1)%channels]*strength,-.75,.85))
    rho=np.round(np.array(rho).reshape(d,block-1)/.05)*.05
    transitions=np.empty((d,block-1,k,k))
    for r in np.unique(rho):
        kernel=np.exp(np.clip((2*r*z[:,None]*z[None]-r*r*(z[:,None]**2+z[None]**2))/(2*(1-r*r)),-50,50))
        coupling=kernel*prior[:,None]*prior[None]
        for _ in range(300):
            coupling*= (prior/coupling.sum(1))[:,None]
            coupling*= (prior/coupling.sum(0))[None]
        transitions[rho==r]=np.log(np.maximum(coupling/prior[:,None],1e-300))
    cost0=abs(support-anchor[:,None])
    costs=np.stack([abs(support-pool[i,:,None])-cost0 for i in keep]+[cost0])
    group=A[:,:,None]*support[None]
    features=np.concatenate([costs,group]).reshape(-1,d,block,k)/(total*weights[None,:,None,None])
    targets=np.r_[scores[reference]-scores[keep],1-scores[reference],b/total]
    # Reparameterization only: retain the same entropy objective.
    centered=features-np.einsum('gdhk,k->gdh',features,prior)[:,:,:,None]
    flat=centered.reshape(len(targets),-1)
    rng=np.random.default_rng(90210)
    groups=rng.choice(d,32768,p=weights);hours=rng.integers(block,size=32768);states=rng.choice(k,32768,p=prior)
    sample=centered[:,groups,hours,states]
    gram=np.einsum('gi,hi->gh',sample,sample)*block/sample.shape[1]
    ev,vec=np.linalg.eigh(gram);transform=(vec/np.sqrt(np.maximum(ev,1e-9))[None]).T
    del flat,centered,sample,group,costs
    def infer(parameters):
        field=np.einsum('g,gdhk->dhk',parameters,features)
        alpha=np.empty((d,block,k));alpha[:,0]=np.log(prior)[None]-field[:,0]
        for h in range(1,block):alpha[:,h]=logsumexp(alpha[:,h-1,:,None]+transitions[:,h-1],axis=1)-field[:,h]
        norm=logsumexp(alpha[:,-1],axis=1)
        beta=np.zeros_like(alpha)
        for h in range(block-2,-1,-1):beta[:,h]=logsumexp(transitions[:,h]-field[:,h+1,None,:]+beta[:,h+1,None,:],axis=2)
        return np.exp(alpha+beta-norm[:,None,None]),norm
    penalty=1e-10
    def objective(theta):
        parameters=np.einsum('gh,g->h',transform,theta)
        probability,norm=infer(parameters)
        value=np.dot(weights,norm)+np.dot(parameters,targets)+penalty*np.dot(parameters,parameters)/2
        grad=targets-np.einsum('gdhk,dhk,d->g',features,probability,weights)+penalty*parameters
        return value,np.einsum('gh,h->g',transform,grad)
    fit=minimize(objective,np.zeros(len(targets)),jac=True,method='L-BFGS-B',options=dict(maxiter=maxiter,ftol=1e-12,gtol=1e-8,maxcor=30))
    probability,_=infer(np.einsum('gh,g->h',transform,fit.x));probability=probability.reshape(n,k)
    mean=np.einsum('nk,nk->n',support,probability)
    fitted=np.array([1-np.einsum('nk,nk->',abs(support-p[:,None]),probability)/total for p in pool])
    return mean,dict(converged=bool(fit.success),iterations=int(fit.nit),score_rmse=float(np.sqrt(np.mean((fitted-scores)**2))),max_group_error=float(abs(np.einsum('gn,n->g',A,mean)-b).max()),strength=strength,block=block)
