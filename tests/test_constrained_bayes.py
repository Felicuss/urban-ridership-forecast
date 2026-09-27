import numpy as np
from s99_constrained_bayes import bayes_action


def test_symmetric_equal_cells_share_fixed_total():
    support=np.tile([0.,50.,100.,150.,200.],(2,1))
    probability=np.tile([.05,.2,.5,.2,.05],(2,1))
    p,meta=bayes_action(support,probability,np.ones((1,2)),np.array([240.]))
    np.testing.assert_allclose(p,[120.,120.],atol=.001)
    assert meta['margin_error']<.001
