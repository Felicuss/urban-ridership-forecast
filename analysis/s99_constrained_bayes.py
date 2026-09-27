"""Joint Bayes action: minimize smoothed posterior absolute error under margins."""
import numpy as np
from scipy.optimize import minimize


def bayes_action(support,probability,A,b):
    # Midpoint CDF interpolation matches the existing interpolated median.
    F=probability.cumsum(1)-probability/2
    slopes=2*F-1
    dx=np.diff(support,axis=1)
    integral=np.c_[np.zeros(len(support)),np.cumsum(dx*(slopes[:,:-1]+slopes[:,1:])/2,axis=1)]
    idx=np.arange(len(support));total=b[0]
    def objective(lam,return_x=False):
        field=np.einsum('gn,g->n',A,lam)
        quantile=np.clip((1-field)/2,0,1)
        j=np.minimum(np.maximum((F<=quantile[:,None]).sum(1)-1,0),support.shape[1]-2)
        left=support[idx,j];right=support[idx,j+1]
        rate=np.clip((quantile-F[idx,j])/np.maximum(F[idx,j+1]-F[idx,j],1e-15),0,1)
        x=left+rate*(right-left)
        if return_x:return x
        area=integral[idx,j]+(x-left)*(slopes[idx,j]+rate*(slopes[idx,j+1]-slopes[idx,j])/2)
        value=(np.dot(lam,b)-(area+field*x).sum())/total
        gradient=(b-np.einsum('gn,n->g',A,x))/total
        return value,gradient
    fit=minimize(objective,np.zeros(len(b)),jac=True,method='L-BFGS-B',options=dict(maxiter=1500,ftol=1e-14,gtol=1e-9,maxcor=30))
    pred=objective(fit.x,True)
    return pred,dict(converged=bool(fit.success),iterations=int(fit.nit),margin_error=float(abs(np.einsum('gn,n->g',A,pred)-b).max()))
