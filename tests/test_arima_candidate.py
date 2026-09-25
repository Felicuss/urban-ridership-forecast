"""Guard forecast history boundaries, L1 daily targets and deployment protections."""
import unittest
import numpy as np
from s60_arima_experiment import Experiment, exogenous, regimes, prepare, optimal_mass, apply_level


class ArimaChecks(unittest.TestCase):
    def test_future_target_values_cannot_change_training(self):
        exp=Experiment();x=exogenous(exp);state=regimes(exp)
        for target in ['sum','optimal']:
            before=prepare(exp,x,state,180,61,17,target,168)
            original=exp.y[181:].copy()
            exp.y[181:]=999999
            after=prepare(exp,x,state,180,61,17,target,168)
            exp.y[181:]=original
            for a,b in zip(before[:-1],after[:-1]):np.testing.assert_array_equal(a,b)
            self.assertEqual(before[-1],after[-1])

    def test_closure_and_validator_anomaly_are_masked(self):
        exp=Experiment();x=exogenous(exp);state=regimes(exp)
        z,_,_,valid,_,_=prepare(exp,x,state,119,61,17,'sum',168)
        days=np.arange(len(z))
        self.assertFalse(valid[(days>=89)&(days<=95)].any())
        self.assertFalse(valid[state[days,5]!=0].any())

    def test_optimal_daily_target_minimizes_hourly_l1(self):
        shape=np.array([[1.,2.,0.,1.],[3.,1.,2.,0.]])
        y=np.array([[2.,9.,8.,1.],[8.,2.,1.,5.]])
        mass=optimal_mass(y,shape)
        fractions=shape/shape.sum(axis=1)[:,None]
        actual=abs(y-fractions*mass[:,None]).sum(axis=1)
        for candidate in np.linspace(0,30,301):
            self.assertTrue((actual<=abs(y-fractions*candidate).sum(axis=1)+1e-10).all())

    def test_protected_routes_and_zero_hours_survive(self):
        route=np.repeat([1,5,7,50,7],24);kind=np.repeat([0,0,1,2,0],24)
        current=np.full(120,100.);current[::24]=0
        a={'route':route,'kind':kind}
        pred=apply_level(a,current,np.full(5,4600.),.3)
        protected=(route==5)|((np.isin(route,[7,50]))&(kind!=0))
        np.testing.assert_array_equal(pred[protected],current[protected])
        np.testing.assert_array_equal(pred[current==0],0)
        self.assertTrue((pred[~protected]>=current[~protected]).all())


if __name__=='__main__':unittest.main()
