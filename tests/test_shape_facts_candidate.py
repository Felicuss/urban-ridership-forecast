"""Guard mass conservation and deployment rules when replacing hourly shapes."""
import unittest
import numpy as np
import pandas as pd
from s62_hourly_shape import features
from s64_package_shape_facts import transfer_shape, round_daily, protected_cells


class ShapeFactsChecks(unittest.TestCase):
    def setUp(self):
        self.a = {'route':np.repeat([1, 5, 7, 50, 7], 24),
                  'kind':np.repeat([0, 0, 1, 2, 0], 24)}
        self.current = np.tile(np.arange(24, dtype=float), 5)
        self.anchor = np.tile(np.arange(24, dtype=float)[::-1], 5)
        self.anchor[::24] = 0
        self.share = np.tile(np.linspace(1, 2, 24), 5)
        self.share = (self.share.reshape(-1, 24)/self.share.reshape(-1, 24).sum(axis=1)[:, None]).reshape(-1)

    def test_transfer_keeps_deployed_totals_zeros_and_protections(self):
        p = transfer_shape(self.anchor, self.current, self.share, self.a)
        np.testing.assert_allclose(p.reshape(-1, 24).sum(axis=1), self.anchor.reshape(-1, 24).sum(axis=1))
        np.testing.assert_array_equal(p[self.anchor == 0], 0)
        protected = protected_cells(self.a)
        np.testing.assert_array_equal(p[protected], self.anchor[protected])
        self.assertGreater(abs(p[~protected]-self.anchor[~protected]).sum(), 0)

    def test_rounding_conserves_totals_and_does_not_open_closed_hours(self):
        p = transfer_shape(self.anchor, self.current, self.share, self.a)
        totals = np.array([300, 253, 253, 253, 280])
        q = round_daily(p, totals).reshape(-1, 24)
        np.testing.assert_array_equal(q.sum(axis=1), totals)
        np.testing.assert_array_equal(q[p.reshape(-1, 24) == 0], 0)
        self.assertTrue((q >= 0).all())
        np.testing.assert_array_equal(round_daily(np.zeros(24), [0]), 0)
        with self.assertRaises(ValueError):
            round_daily(np.zeros(24), [1])

    def test_features_do_not_read_target_labels(self):
        frame = pd.DataFrame({'base':np.arange(24, dtype=float), 'target_day':np.repeat(304, 24),
            'origin':np.repeat(303, 24), 'route':np.repeat(17, 24), 'hour':np.arange(24),
            'temperature_2m':np.arange(24, dtype=float), 'precipitation':np.zeros(24),
            'y':np.arange(24, dtype=float)})
        before = features(frame)
        frame['y'] = 999999
        pd.testing.assert_frame_equal(before, features(frame))
        self.assertNotIn('y', before)


if __name__ == '__main__':
    unittest.main()
