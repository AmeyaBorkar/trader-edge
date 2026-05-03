"""Volatility estimators should recover ground-truth sigma from simulated paths."""
import math

import numpy as np

from trader_edge.math_core.volatility import (
    close_to_close,
    ewma,
    garman_klass,
    parkinson,
)


def _simulate_ohlc(sigma_annual: float, n_days: int, seed: int = 5):
    rng = np.random.default_rng(seed)
    sigma_d = sigma_annual / math.sqrt(252)
    log_returns = rng.normal(-0.5 * sigma_d ** 2, sigma_d, size=n_days)
    closes = 100 * np.exp(np.cumsum(log_returns))
    opens = closes / np.exp(log_returns)
    intraday_sigma = sigma_d * 0.6
    n_per_day = 50
    high = closes.copy()
    low = closes.copy()
    for i in range(n_days):
        path = opens[i] * np.exp(np.cumsum(rng.normal(0, intraday_sigma / math.sqrt(n_per_day),
                                                     size=n_per_day)))
        high[i] = max(opens[i], closes[i], path.max())
        low[i] = min(opens[i], closes[i], path.min())
    return opens, high, low, closes


def test_close_to_close_recovers_sigma():
    sigma = 0.25
    _, _, _, closes = _simulate_ohlc(sigma, 5000)
    estimate = close_to_close(closes)
    assert abs(estimate - sigma) < 0.015, f"got {estimate}, expected {sigma}"


def test_parkinson_recovers_sigma():
    sigma = 0.25
    _, h, l, _ = _simulate_ohlc(sigma, 5000)
    est = parkinson(h, l)
    # Parkinson ignores intraday drift; should be in the ballpark.
    assert 0.18 < est < 0.32, f"got {est}"


def test_garman_klass_recovers_sigma():
    sigma = 0.25
    o, h, l, c = _simulate_ohlc(sigma, 5000)
    est = garman_klass(o, h, l, c)
    assert 0.18 < est < 0.32, f"got {est}"


def test_ewma_returns_positive():
    _, _, _, c = _simulate_ohlc(0.20, 200)
    assert ewma(c) > 0
