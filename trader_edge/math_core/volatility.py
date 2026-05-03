"""Realized volatility estimators.

Three estimators from cheapest-to-best signal:
    close_to_close — classical, uses only daily closes.
    parkinson      — uses daily high-low range, ~5x more efficient.
    garman_klass   — uses OHLC, ~7x more efficient than close-to-close.

All return *annualized* sigma assuming `trading_days_per_year` (default 252).
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from ..config import TRADING_DAYS_PER_YEAR


def close_to_close(closes: Sequence[float], periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    closes = np.asarray(closes, dtype=float)
    if len(closes) < 2:
        raise ValueError("Need at least 2 closes")
    log_returns = np.diff(np.log(closes))
    return float(np.std(log_returns, ddof=1) * math.sqrt(periods_per_year))


def parkinson(highs: Sequence[float], lows: Sequence[float],
              periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    if len(highs) != len(lows) or len(highs) == 0:
        raise ValueError("Highs and lows must align and be non-empty")
    log_hl = np.log(highs / lows)
    sigma2_daily = (log_hl ** 2).mean() / (4.0 * math.log(2.0))
    return float(math.sqrt(sigma2_daily * periods_per_year))


def garman_klass(opens: Sequence[float], highs: Sequence[float],
                 lows: Sequence[float], closes: Sequence[float],
                 periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    o = np.asarray(opens, dtype=float)
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    if not (len(o) == len(h) == len(l) == len(c)) or len(o) == 0:
        raise ValueError("OHLC arrays must align and be non-empty")
    log_hl = np.log(h / l)
    log_co = np.log(c / o)
    sigma2 = (0.5 * log_hl ** 2 - (2 * math.log(2) - 1) * log_co ** 2).mean()
    return float(math.sqrt(sigma2 * periods_per_year))


def ewma(closes: Sequence[float], lam: float = 0.94,
         periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """RiskMetrics-style EWMA of squared log-returns. lam=0.94 is the standard daily."""
    closes = np.asarray(closes, dtype=float)
    if len(closes) < 2:
        raise ValueError("Need at least 2 closes")
    r = np.diff(np.log(closes))
    weights = (1 - lam) * lam ** np.arange(len(r))[::-1]
    weights /= weights.sum()
    sigma2 = (weights * r ** 2).sum()
    return float(math.sqrt(sigma2 * periods_per_year))
