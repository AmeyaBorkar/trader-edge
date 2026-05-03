"""Risk-neutral implied probability density via the option chain.

Two routes from the chain to a probability:

A. Breeden-Litzenberger (terminal density)
   The risk-neutral PDF at strike K and time T is:
       f(K) = e^{rT} * d^2 C(K) / dK^2
   so the probability that S_T >= L at expiry is the integral of f from L to inf.

B. Implied-vol smile + barrier math (first-passage probability)
   Fit IV(K) from the chain, evaluate IV at the barrier strike, then plug into
   the reflection-principle first-passage formula. This is what we want for a
   target/stop that triggers the moment the price *touches* the level.

Both routes are deterministic. Smile fitting uses a quadratic in log-moneyness
which is enough for screen-size precision; SVI is a drop-in upgrade later.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.interpolate import CubicSpline

from .black_scholes import Quote, implied_vol, price
from ..config import RISK_FREE_RATE


@dataclass(frozen=True)
class ChainSlice:
    """A single-expiry slice of an option chain."""
    spot: float
    t_years: float
    strikes: np.ndarray            # shape (n,)
    call_prices: np.ndarray        # shape (n,) — mids
    put_prices: np.ndarray         # shape (n,) — mids
    rate: float = RISK_FREE_RATE

    def __post_init__(self):
        # Defensive: arrays must be sorted and aligned
        order = np.argsort(self.strikes)
        object.__setattr__(self, "strikes", self.strikes[order])
        object.__setattr__(self, "call_prices", self.call_prices[order])
        object.__setattr__(self, "put_prices", self.put_prices[order])


def implied_vol_smile(slice_: ChainSlice) -> tuple[np.ndarray, np.ndarray]:
    """Return (strikes, ivs) using the OTM side of the chain (more reliable bid/ask).

    Calls are used for K > spot (OTM calls), puts for K < spot (OTM puts).
    Skips strikes where price is below intrinsic (data error) or below 0.05 (noise).
    """
    strikes_out, ivs_out = [], []
    for k, c, p in zip(slice_.strikes, slice_.call_prices, slice_.put_prices):
        is_call = k >= slice_.spot
        market = c if is_call else p
        if market < 0.05:
            continue
        q = Quote(spot=slice_.spot, strike=float(k), t_years=slice_.t_years,
                  rate=slice_.rate, is_call=is_call)
        try:
            iv = implied_vol(q, market)
        except ValueError:
            continue
        if 0.01 < iv < 4.0:
            strikes_out.append(float(k))
            ivs_out.append(iv)
    return np.array(strikes_out), np.array(ivs_out)


def fit_smile(strikes: np.ndarray, ivs: np.ndarray, spot: float):
    """Fit IV(K) = a + b*x + c*x^2 in log-moneyness x = log(K/spot).

    Returns a callable smile(K) -> IV. Quadratic captures curvature (smile/skew)
    without overfitting sparse strike grids; replace with SVI when you need
    extrapolation beyond the listed range.
    """
    if len(strikes) < 3:
        raise ValueError("Need at least 3 strikes to fit a smile")
    x = np.log(np.asarray(strikes) / spot)
    coefs = np.polyfit(x, np.asarray(ivs), 2)

    def smile(strike: float) -> float:
        return float(np.polyval(coefs, math.log(strike / spot)))

    return smile


def terminal_pdf(slice_: ChainSlice, n_grid: int = 401) -> tuple[np.ndarray, np.ndarray]:
    """Breeden-Litzenberger terminal-price PDF.

    Returns (price_grid, density). Density integrates to ~1 over the grid range.

    Algorithm:
      1. Fit IV smile from the chain.
      2. Reprice calls on a dense, even-spaced strike grid using the smile.
      3. Numerical 2nd derivative * exp(rT) -> PDF.
      4. Clip negatives (numerical noise) and renormalize.
    """
    strikes, ivs = implied_vol_smile(slice_)
    smile = fit_smile(strikes, ivs, slice_.spot)

    k_min = max(0.4 * slice_.spot, float(strikes.min()))
    k_max = min(2.5 * slice_.spot, float(strikes.max()))
    k_grid = np.linspace(k_min, k_max, n_grid)
    dk = k_grid[1] - k_grid[0]

    call_grid = np.empty_like(k_grid)
    for i, k in enumerate(k_grid):
        iv = smile(float(k))
        q = Quote(spot=slice_.spot, strike=float(k), t_years=slice_.t_years,
                  rate=slice_.rate, is_call=True)
        call_grid[i] = price(q, iv)

    # Central difference 2nd derivative
    second_deriv = np.zeros_like(call_grid)
    second_deriv[1:-1] = (call_grid[2:] - 2 * call_grid[1:-1] + call_grid[:-2]) / (dk ** 2)
    second_deriv[0] = second_deriv[1]
    second_deriv[-1] = second_deriv[-2]

    pdf = np.exp(slice_.rate * slice_.t_years) * second_deriv
    pdf = np.clip(pdf, 0.0, None)
    integral = np.trapezoid(pdf, k_grid)
    if integral > 0:
        pdf = pdf / integral
    return k_grid, pdf


def prob_above_at_expiry(slice_: ChainSlice, level: float) -> float:
    """Risk-neutral P(S_T >= level) at expiry, from the terminal PDF."""
    k_grid, pdf = terminal_pdf(slice_)
    mask = k_grid >= level
    if not mask.any():
        return 0.0
    return float(np.trapezoid(pdf[mask], k_grid[mask]))


def prob_below_at_expiry(slice_: ChainSlice, level: float) -> float:
    return 1.0 - prob_above_at_expiry(slice_, level)


def iv_at_strike(slice_: ChainSlice, strike: float) -> float:
    """Convenience: fit smile and return IV at an arbitrary strike."""
    strikes, ivs = implied_vol_smile(slice_)
    smile = fit_smile(strikes, ivs, slice_.spot)
    return smile(strike)
