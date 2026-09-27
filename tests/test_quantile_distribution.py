import numpy as np
import pytest
from s108_quantile_distribution import quantile_prior, LEVELS
from s93_entropy_scores import posterior, prior_grid


def test_quantile_support_preserves_zeros_order_and_known_error():
    anchor = np.array([0., 100., 500., 1000.])
    q = np.tile(np.linspace(-.3, .5, len(LEVELS)), (4, 1))
    support, prior = quantile_prior(anchor, 150., q, np.ones(4), .5)
    assert np.isfinite(support).all() and (support >= 0).all()
    assert (np.diff(support, axis=1) >= 0).all()
    np.testing.assert_array_equal(support[0], 0)
    np.testing.assert_allclose(np.einsum('nk,k->', abs(support-anchor[:, None]), prior), 150., atol=1e-6)


def test_explicit_default_prior_reproduces_original_posterior():
    anchor = np.array([0., 100., 500., 1000.])
    pool = np.array([anchor, anchor * .95])
    truth = np.array([0., 120., 450., 1050.])
    total = truth.sum()
    scores = 1-abs(pool-truth).sum(axis=1)/total
    A = np.ones((1, 4)); b = np.array([total])
    support, prior, _ = prior_grid(anchor, (1-scores[0])*total)
    default, _ = posterior(anchor, pool, scores, A, b, total)
    explicit, _ = posterior(anchor, pool, scores, A, b, total, custom_prior=(support, prior), entropy_power=1.)
    np.testing.assert_allclose(default['mean'], explicit['mean'], atol=1e-9)
    with pytest.raises(ValueError):
        posterior(anchor, pool, scores, A, b, total, custom_prior=(support[:, ::-1], prior))
