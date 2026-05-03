"""Reflection-principle formula should match Monte Carlo for single-barrier hits."""
import math

import numpy as np
import pytest

from trader_edge.math_core.barrier import (
    joint_barrier_probs,
    prob_hit_single_barrier,
)


def _mc_single_barrier(spot, barrier, sigma, days, n=40000, seed=1):
    """Monte Carlo with Brownian-bridge correction so discretization doesn't bias results."""
    rng = np.random.default_rng(seed)
    t = days / 252
    n_steps = max(int(days * 48), 60)
    dt = t / n_steps
    sigma_dt = sigma * math.sqrt(dt)
    mu_dt = -0.5 * sigma ** 2 * dt
    z = rng.standard_normal((n, n_steps))
    log_increments = mu_dt + sigma_dt * z
    log_paths = np.cumsum(log_increments, axis=1)
    # Prepend the starting point (log 0)
    log_full = np.concatenate([np.zeros((n, 1)), log_paths], axis=1)
    log_b = math.log(barrier / spot)

    # Discrete hits (a step landed at or past the barrier)
    if barrier < spot:
        hit_discrete = (log_paths.min(axis=1) <= log_b)
    else:
        hit_discrete = (log_paths.max(axis=1) >= log_b)

    # Brownian-bridge crossing probability for paths that didn't hit discretely.
    # Between two same-side endpoints x1, x2, P(crossed barrier in interval) =
    #   exp(-2 * (x1 - b) * (x2 - b) / (sigma^2 * dt))   when both above b (lower barrier)
    #   exp(-2 * (b - x1) * (b - x2) / (sigma^2 * dt))   when both below b (upper barrier)
    survivors = ~hit_discrete
    if survivors.any():
        x1 = log_full[survivors, :-1]
        x2 = log_full[survivors, 1:]
        if barrier < spot:
            arg = -2.0 * (x1 - log_b) * (x2 - log_b) / (sigma ** 2 * dt)
        else:
            arg = -2.0 * (log_b - x1) * (log_b - x2) / (sigma ** 2 * dt)
        # Clip to keep numerics happy; exp(0) = 1 for impossible-cross cases
        cross_prob_per_step = np.exp(np.clip(arg, -50, 0))
        no_cross_prob = np.prod(1.0 - cross_prob_per_step, axis=1)
        bridged_hits = (1.0 - no_cross_prob).sum()
    else:
        bridged_hits = 0.0

    return float((hit_discrete.sum() + bridged_hits) / n)


@pytest.mark.parametrize("spot,barrier,sigma,days", [
    (100, 95, 0.20, 5),
    (100, 90, 0.20, 10),
    (100, 105, 0.20, 5),
    (100, 110, 0.30, 10),
    (100, 98, 0.40, 3),
])
def test_reflection_matches_mc(spot, barrier, sigma, days):
    closed = prob_hit_single_barrier(spot, barrier, sigma, days)
    mc = _mc_single_barrier(spot, barrier, sigma, days)
    assert abs(closed - mc) < 0.025, (
        f"closed={closed:.4f} mc={mc:.4f} for spot={spot} barrier={barrier} "
        f"sigma={sigma} days={days}"
    )


def test_joint_barrier_probabilities_sum_to_one():
    res = joint_barrier_probs(100, 105, 95, 0.25, 5)
    total = res.p_target_first + res.p_stop_first + res.p_neither
    assert abs(total - 1.0) < 1e-9


def test_joint_target_more_likely_when_closer():
    near_target = joint_barrier_probs(100, 102, 95, 0.25, 5)
    far_target = joint_barrier_probs(100, 110, 95, 0.25, 5)
    assert near_target.p_target_first > far_target.p_target_first


def test_joint_validates_input():
    with pytest.raises(ValueError):
        joint_barrier_probs(100, 90, 95, 0.25, 5)  # target < spot — not a long bracket
