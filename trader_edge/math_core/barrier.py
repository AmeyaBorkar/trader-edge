"""First-passage / barrier-hitting probabilities for geometric Brownian motion.

The reflection principle gives a closed form for the probability that a GBM
crosses a single barrier within [0, T]. For two-sided (target AND stop) we
fall back to a small Monte Carlo because the closed form involves an infinite
theta-function series and is finicky to truncate.

Conventions:
    sigma_annual is the annualized lognormal volatility (e.g., 0.22 = 22%).
    horizon_days is calendar trading days; converted via TRADING_DAYS_PER_YEAR.
    drift is the annualized continuous drift on the underlying. Default 0
      because over short horizons the drift contribution is dominated by sigma.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from ..config import TRADING_DAYS_PER_YEAR


def prob_hit_single_barrier(
    spot: float,
    barrier: float,
    sigma_annual: float,
    horizon_days: float,
    drift: float = 0.0,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """P(min_{0<=t<=T} S_t <= barrier) if barrier < spot,
    else P(max_{0<=t<=T} S_t >= barrier).

    Uses the reflection principle for arithmetic Brownian motion on log(S/S_0).
    """
    if spot <= 0 or barrier <= 0:
        raise ValueError("Prices must be positive")
    if sigma_annual <= 0 or horizon_days <= 0:
        raise ValueError("Volatility and horizon must be positive")
    if abs(barrier - spot) < 1e-12:
        return 1.0

    t_years = horizon_days / trading_days_per_year
    sigma_sqrt_t = sigma_annual * math.sqrt(t_years)
    mu_x = (drift - 0.5 * sigma_annual ** 2)  # drift of log-return process
    b = math.log(barrier / spot)              # signed log-distance to barrier

    # Reflection-principle formula for first passage of arithmetic BM.
    # For a barrier at level `b` away from start (signed), with drift mu_x and
    # vol sigma_annual over horizon t_years:
    #   if b < 0 (lower barrier):
    #     P = N((b - mu_x*T)/sigma_sqrt_t) + exp(2*mu_x*b/sigma^2) * N((b + mu_x*T)/sigma_sqrt_t)
    #   if b > 0 (upper barrier): mirror image — flip signs of b and mu_x
    if b < 0:
        d_minus = (b - mu_x * t_years) / sigma_sqrt_t
        d_plus = (b + mu_x * t_years) / sigma_sqrt_t
        adj = math.exp(2 * mu_x * b / (sigma_annual ** 2))
        prob = norm.cdf(d_minus) + adj * norm.cdf(d_plus)
    else:
        d_minus = (-b - mu_x * t_years) / sigma_sqrt_t
        d_plus = (-b + mu_x * t_years) / sigma_sqrt_t
        adj = math.exp(-2 * mu_x * b / (sigma_annual ** 2))
        prob = norm.cdf(d_minus) + adj * norm.cdf(d_plus)

    return float(min(max(prob, 0.0), 1.0))


@dataclass(frozen=True)
class JointBarrierResult:
    p_target_first: float
    p_stop_first: float
    p_neither: float
    expected_exit_days: float  # expected exit time conditional on early exit
    n_paths: int
    n_steps: int


def joint_barrier_probs(
    spot: float,
    target: float,
    stop: float,
    sigma_annual: float,
    horizon_days: float,
    drift: float = 0.0,
    n_paths: int = 25_000,
    steps_per_day: int = 8,
    seed: int = 42,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> JointBarrierResult:
    """Monte Carlo joint first-passage for a long position with target above and stop below.

    Deterministic given a fixed seed. ~10ms for n_paths=25k.
    """
    if not (stop < spot < target):
        raise ValueError(
            f"Need stop ({stop}) < spot ({spot}) < target ({target}) for a long bracket"
        )
    if sigma_annual <= 0 or horizon_days <= 0:
        raise ValueError("Volatility and horizon must be positive")

    rng = np.random.default_rng(seed)
    t_years = horizon_days / trading_days_per_year
    n_steps = max(int(horizon_days * steps_per_day), 50)
    dt = t_years / n_steps
    sigma_dt = sigma_annual * math.sqrt(dt)
    mu_dt = (drift - 0.5 * sigma_annual ** 2) * dt

    # Simulate log-paths in float32 to keep memory in check for large n_paths.
    z = rng.standard_normal((n_paths, n_steps)).astype(np.float32)
    log_increments = (mu_dt + sigma_dt * z).astype(np.float32)
    log_paths = np.cumsum(log_increments, axis=1)
    paths = spot * np.exp(log_paths)

    log_target = math.log(target / spot)
    log_stop = math.log(stop / spot)

    # First step where each barrier is hit (n_steps if never hit)
    target_hit_mask = log_paths >= log_target
    stop_hit_mask = log_paths <= log_stop

    target_first = np.where(target_hit_mask.any(axis=1),
                            target_hit_mask.argmax(axis=1),
                            n_steps + 1)
    stop_first = np.where(stop_hit_mask.any(axis=1),
                          stop_hit_mask.argmax(axis=1),
                          n_steps + 1)

    target_won = (target_first < stop_first) & (target_first <= n_steps)
    stop_won = (stop_first < target_first) & (stop_first <= n_steps)
    neither = ~(target_won | stop_won)

    early_exit = ~neither
    if early_exit.any():
        exit_step = np.minimum(target_first, stop_first)[early_exit]
        expected_exit_days = float(exit_step.mean() / steps_per_day)
    else:
        expected_exit_days = float(horizon_days)

    return JointBarrierResult(
        p_target_first=float(target_won.mean()),
        p_stop_first=float(stop_won.mean()),
        p_neither=float(neither.mean()),
        expected_exit_days=expected_exit_days,
        n_paths=n_paths,
        n_steps=n_steps,
    )
