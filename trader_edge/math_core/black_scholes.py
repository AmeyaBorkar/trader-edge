"""Black-Scholes pricing, greeks, and implied volatility inversion.

European options on a non-dividend-paying underlying. For Indian index options
(NIFTY, BANKNIFTY, FINNIFTY) this is fine; for single-stock options, ignore the
small bias from any expected dividends in the holding window.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm

from ..config import RISK_FREE_RATE


@dataclass(frozen=True)
class Quote:
    spot: float
    strike: float
    t_years: float       # time to expiry in years
    rate: float = RISK_FREE_RATE
    is_call: bool = True


def _d1_d2(q: Quote, sigma: float) -> tuple[float, float]:
    if sigma <= 0 or q.t_years <= 0:
        raise ValueError("sigma and t_years must be positive")
    sqrt_t = math.sqrt(q.t_years)
    d1 = (math.log(q.spot / q.strike) + (q.rate + 0.5 * sigma ** 2) * q.t_years) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def price(q: Quote, sigma: float) -> float:
    """BS price of European call/put."""
    d1, d2 = _d1_d2(q, sigma)
    disc = math.exp(-q.rate * q.t_years)
    if q.is_call:
        return q.spot * norm.cdf(d1) - q.strike * disc * norm.cdf(d2)
    return q.strike * disc * norm.cdf(-d2) - q.spot * norm.cdf(-d1)


def vega(q: Quote, sigma: float) -> float:
    """dPrice/dSigma. Same for call and put."""
    d1, _ = _d1_d2(q, sigma)
    return q.spot * norm.pdf(d1) * math.sqrt(q.t_years)


def delta(q: Quote, sigma: float) -> float:
    d1, _ = _d1_d2(q, sigma)
    return norm.cdf(d1) if q.is_call else norm.cdf(d1) - 1.0


def gamma(q: Quote, sigma: float) -> float:
    d1, _ = _d1_d2(q, sigma)
    return norm.pdf(d1) / (q.spot * sigma * math.sqrt(q.t_years))


def theta_per_day(q: Quote, sigma: float) -> float:
    d1, d2 = _d1_d2(q, sigma)
    disc = math.exp(-q.rate * q.t_years)
    common = -q.spot * norm.pdf(d1) * sigma / (2 * math.sqrt(q.t_years))
    if q.is_call:
        annual = common - q.rate * q.strike * disc * norm.cdf(d2)
    else:
        annual = common + q.rate * q.strike * disc * norm.cdf(-d2)
    return annual / 365.0


def implied_vol(q: Quote, market_price: float, *, tol: float = 1e-6,
                max_iter: int = 100) -> float:
    """Invert BS via Newton with bisection fallback. Returns sigma in annualized units.

    Raises ValueError if market_price violates no-arbitrage bounds.
    """
    if market_price <= 0:
        raise ValueError("Market price must be positive")
    disc_strike = q.strike * math.exp(-q.rate * q.t_years)
    # European-option no-arbitrage bounds
    if q.is_call:
        lower_bound = max(0.0, q.spot - disc_strike)
        upper_bound = q.spot
    else:
        lower_bound = max(0.0, disc_strike - q.spot)
        upper_bound = disc_strike
    if market_price < lower_bound - 1e-6 or market_price > upper_bound + 1e-6:
        raise ValueError(
            f"Price {market_price} outside arbitrage bounds [{lower_bound}, {upper_bound}]"
        )

    # Newton's method seeded near 30% vol
    sigma = 0.3
    for _ in range(max_iter):
        try:
            diff = price(q, sigma) - market_price
        except ValueError:
            break
        if abs(diff) < tol:
            return sigma
        v = vega(q, sigma)
        if v < 1e-10:
            break
        step = diff / v
        new_sigma = sigma - step
        if new_sigma <= 0 or new_sigma > 5.0:
            break
        sigma = new_sigma

    # Bisection fallback
    lo, hi = 1e-4, 5.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        diff = price(q, mid) - market_price
        if abs(diff) < tol:
            return mid
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
