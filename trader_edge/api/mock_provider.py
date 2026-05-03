"""Offline data provider with realistic-looking RELIANCE / NIFTY chains.

Lets the engine be exercised end-to-end without Groww credentials. Built so the
chain is internally consistent: prices come from Black-Scholes with a
plausible smile, so implied vol extraction round-trips cleanly.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from ..math_core.black_scholes import Quote, price as bs_price
from .base import DataProvider
from .models import Candle, OptionChain, OptionRow, Order


def _smile(strike: float, spot: float, atm_iv: float, skew: float = -0.20,
           curv: float = 0.6) -> float:
    """A plausible equity-style IV smile: negative skew + curvature."""
    x = math.log(strike / spot)
    return max(0.05, atm_iv + skew * x + curv * x * x)


def _build_chain(symbol: str, spot: float, t_years: float, atm_iv: float,
                 expiry: date, n_strikes: int = 21, strike_step: float | None = None) -> OptionChain:
    if strike_step is None:
        strike_step = round(spot * 0.01 / 5) * 5 or 5
    half = n_strikes // 2
    rows: list[OptionRow] = []
    for i in range(-half, half + 1):
        k = round((spot + i * strike_step) / strike_step) * strike_step
        iv = _smile(k, spot, atm_iv)
        c_quote = Quote(spot, k, t_years, is_call=True)
        p_quote = Quote(spot, k, t_years, is_call=False)
        c_mid = bs_price(c_quote, iv)
        p_mid = bs_price(p_quote, iv)
        # Add a 1% spread around mid as a stand-in for bid/ask
        spread_c = max(0.05, c_mid * 0.01)
        spread_p = max(0.05, p_mid * 0.01)
        rows.append(OptionRow(
            strike=float(k),
            call_bid=max(0.05, c_mid - spread_c),
            call_ask=c_mid + spread_c,
            call_oi=int(50000 * math.exp(-((i / 5) ** 2))),
            put_bid=max(0.05, p_mid - spread_p),
            put_ask=p_mid + spread_p,
            put_oi=int(50000 * math.exp(-((i / 5) ** 2))),
        ))
    return OptionChain(symbol=symbol, spot=spot, expiry=expiry, rows=rows)


def _simulate_candles(end: date, n_days: int, start_price: float,
                      sigma_annual: float, drift: float = 0.05,
                      seed: int = 7) -> list[Candle]:
    rng = np.random.default_rng(seed)
    sigma_d = sigma_annual / math.sqrt(252)
    mu_d = drift / 252 - 0.5 * sigma_d ** 2
    log_returns = rng.normal(mu_d, sigma_d, size=n_days)
    closes = start_price * np.exp(np.cumsum(log_returns))
    out: list[Candle] = []
    day = end - timedelta(days=n_days - 1)
    for i, close in enumerate(closes):
        prev_close = start_price if i == 0 else closes[i - 1]
        opn = prev_close * (1 + rng.normal(0, sigma_d * 0.3))
        hi = max(opn, close) * (1 + abs(rng.normal(0, sigma_d * 0.5)))
        lo = min(opn, close) * (1 - abs(rng.normal(0, sigma_d * 0.5)))
        out.append(Candle(day + timedelta(days=i), float(opn), float(hi),
                          float(lo), float(close), int(rng.integers(1e6, 1e7))))
    return out


_MOCK_PROFILES = {
    "RELIANCE": {"spot": 2850.0, "iv": 0.22, "drift": 0.06, "step": 20.0},
    "NIFTY": {"spot": 24500.0, "iv": 0.13, "drift": 0.10, "step": 50.0},
    "BANKNIFTY": {"spot": 52000.0, "iv": 0.15, "drift": 0.10, "step": 100.0},
    "TCS": {"spot": 4100.0, "iv": 0.20, "drift": 0.05, "step": 25.0},
    "HDFCBANK": {"spot": 1620.0, "iv": 0.18, "drift": 0.07, "step": 10.0},
}


class MockProvider(DataProvider):
    """Returns deterministic, internally consistent fake data for any of the symbols above."""

    def __init__(self, today: date | None = None, expiry_offset_days: int = 30):
        self.today = today or date.today()
        self.expiry_offset_days = expiry_offset_days

    def _profile(self, symbol: str) -> dict:
        profile = _MOCK_PROFILES.get(symbol.upper())
        if not profile:
            raise KeyError(
                f"Mock provider has no profile for {symbol!r}. "
                f"Known: {sorted(_MOCK_PROFILES)}"
            )
        return profile

    def get_ltp(self, symbol: str) -> float:
        return self._profile(symbol)["spot"]

    def get_candles(self, symbol: str, start: date, end: date) -> list[Candle]:
        prof = self._profile(symbol)
        n_days = (end - start).days + 1
        return _simulate_candles(end, n_days, prof["spot"], prof["iv"], prof["drift"])

    def get_option_chain(self, underlying: str, expiry: date | None = None) -> OptionChain:
        prof = self._profile(underlying)
        exp = expiry or (self.today + timedelta(days=self.expiry_offset_days))
        t_years = max((exp - self.today).days / 365.0, 1 / 365.0)
        n_strikes = 31 if underlying.upper() in ("NIFTY", "BANKNIFTY") else 21
        return _build_chain(underlying.upper(), prof["spot"], t_years, prof["iv"],
                            exp, n_strikes=n_strikes, strike_step=prof["step"])

    def get_recent_orders(self, days: int = 30) -> list[Order]:
        # A small synthetic history for journaling demo purposes.
        rng = np.random.default_rng(11)
        symbols = list(_MOCK_PROFILES.keys())
        out: list[Order] = []
        for i in range(20):
            sym = symbols[int(rng.integers(0, len(symbols)))]
            spot = _MOCK_PROFILES[sym]["spot"]
            side = "BUY" if rng.random() < 0.55 else "SELL"
            placed = self.today - timedelta(days=int(rng.integers(1, days)))
            out.append(Order(
                order_id=f"MOCK{i:04d}",
                symbol=sym,
                side=side,
                quantity=int(rng.integers(1, 50)),
                price=float(spot * (1 + rng.normal(0, 0.01))),
                placed_at=placed,
                product="CNC" if rng.random() < 0.6 else "MIS",
                status="EXECUTED",
            ))
        return out
