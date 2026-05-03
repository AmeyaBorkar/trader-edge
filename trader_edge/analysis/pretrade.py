"""The pre-trade engine: take a long-bracket trade, return a deterministic verdict.

Combines:
  * Realized vol (history) -> noise-stop probability via reflection principle.
  * Implied vol (option chain) -> first-passage via barrier math.
  * Joint Monte Carlo -> who hits first.
  * Expected value with brokerage/slippage.

All computations are pure functions of public market data. No LLM in the loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..api.base import DataProvider
from ..api.models import OptionChain
from ..config import (
    INDEX_VRP_VOL_POINTS,
    SINGLE_NAME_VRP_VOL_POINTS,
    TRADING_DAYS_PER_YEAR,
)
from ..math_core.barrier import joint_barrier_probs, prob_hit_single_barrier
from ..math_core.ev import EVResult, expected_value
from ..math_core.implied_pdf import (
    ChainSlice,
    iv_at_strike,
    prob_above_at_expiry,
    prob_below_at_expiry,
)
from ..math_core.volatility import close_to_close, garman_klass

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"}


@dataclass(frozen=True)
class TradeRequest:
    symbol: str
    entry: float
    target: float
    stop: float
    horizon_days: int
    quantity: int = 1


@dataclass(frozen=True)
class NoiseStopReport:
    """Probability the stop is hit by realized-vol noise alone within horizon."""
    sigma_realized_annual: float
    p_stop_hit_noise: float
    min_safe_stop: float       # stop level that would drop noise hit prob to ~30%
    horizon_days: int


@dataclass(frozen=True)
class ImpliedReport:
    """Probabilities derived from the option chain."""
    expiry: date
    atm_iv: float
    iv_at_target: float
    iv_at_stop: float
    p_touch_target: float
    p_touch_stop: float
    p_touch_target_realworld: float  # VRP-adjusted
    p_touch_stop_realworld: float
    p_above_target_at_expiry: float
    p_below_stop_at_expiry: float


@dataclass(frozen=True)
class JointReport:
    p_target_first: float
    p_stop_first: float
    p_neither: float
    expected_exit_days: float


@dataclass(frozen=True)
class PreTradeVerdict:
    request: TradeRequest
    noise: NoiseStopReport
    implied: ImpliedReport
    joint: JointReport
    ev_riskneutral: EVResult
    ev_realworld: EVResult
    notes: list[str]


SAFE_NOISE_HIT_THRESHOLD = 0.30


def _binary_search_safe_stop(spot: float, sigma: float, horizon_days: int,
                             target_prob: float = SAFE_NOISE_HIT_THRESHOLD) -> float:
    """Find stop distance such that single-barrier hit probability ~ target_prob."""
    lo, hi = spot * 0.50, spot * 0.999
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        p = prob_hit_single_barrier(spot, mid, sigma, horizon_days)
        if p > target_prob:
            hi = mid  # stop too close — push lower
        else:
            lo = mid
    return 0.5 * (lo + hi)


def analyze_trade(
    provider: DataProvider,
    request: TradeRequest,
    *,
    history_days: int = 60,
    chain_expiry: date | None = None,
) -> PreTradeVerdict:
    if not (request.stop < request.entry < request.target):
        raise ValueError("Need stop < entry < target for a long bracket")
    notes: list[str] = []

    # 1. Realized vol from recent history
    today = date.today()
    candles = provider.get_candles(
        request.symbol, today - timedelta(days=history_days * 2), today
    )
    if len(candles) < 10:
        raise RuntimeError(f"Insufficient history for {request.symbol}: {len(candles)} candles")
    closes = [c.close for c in candles]
    try:
        sigma_real = garman_klass(
            [c.open for c in candles],
            [c.high for c in candles],
            [c.low for c in candles],
            closes,
        )
    except Exception:
        sigma_real = close_to_close(closes)
        notes.append("Fell back to close-to-close vol (OHLC degenerate)")

    p_stop_noise = prob_hit_single_barrier(
        request.entry, request.stop, sigma_real, request.horizon_days
    )
    safe_stop = _binary_search_safe_stop(request.entry, sigma_real, request.horizon_days)
    noise = NoiseStopReport(
        sigma_realized_annual=sigma_real,
        p_stop_hit_noise=p_stop_noise,
        min_safe_stop=safe_stop,
        horizon_days=request.horizon_days,
    )

    # 2. Option chain — fit smile, extract IVs, compute first-passage probs
    chain = provider.get_option_chain(request.symbol, expiry=chain_expiry)
    implied = _build_implied_report(chain, request)

    # 3. Joint barrier (Monte Carlo) using option-implied ATM vol — the
    #    market's own forecast of what's about to happen.
    joint = joint_barrier_probs(
        spot=request.entry,
        target=request.target,
        stop=request.stop,
        sigma_annual=implied.atm_iv,
        horizon_days=min(request.horizon_days, (chain.expiry - today).days or 1),
    )
    joint_report = JointReport(
        p_target_first=joint.p_target_first,
        p_stop_first=joint.p_stop_first,
        p_neither=joint.p_neither,
        expected_exit_days=joint.expected_exit_days,
    )

    # 4. EV: risk-neutral and real-world (VRP-adjusted)
    ev_rn = expected_value(
        entry=request.entry, target=request.target, stop=request.stop,
        p_target=joint_report.p_target_first, p_stop=joint_report.p_stop_first,
    )

    # Real-world EV approximation: scale the implied probabilities
    # back to physical measure using VRP, then renormalize.
    vrp = INDEX_VRP_VOL_POINTS if request.symbol.upper() in INDEX_SYMBOLS \
        else SINGLE_NAME_VRP_VOL_POINTS
    rw_iv = max(0.05, implied.atm_iv - vrp / 100.0)
    rw_joint = joint_barrier_probs(
        spot=request.entry, target=request.target, stop=request.stop,
        sigma_annual=rw_iv,
        horizon_days=min(request.horizon_days, (chain.expiry - today).days or 1),
        seed=43,
    )
    ev_rw = expected_value(
        entry=request.entry, target=request.target, stop=request.stop,
        p_target=rw_joint.p_target_first, p_stop=rw_joint.p_stop_first,
    )

    # Diagnostics
    if implied.atm_iv > sigma_real * 1.3:
        notes.append(
            f"Implied ATM vol {implied.atm_iv:.1%} >> realized {sigma_real:.1%}: "
            "options market expects a bigger move than recent history."
        )
    elif implied.atm_iv < sigma_real * 0.8:
        notes.append(
            f"Implied ATM vol {implied.atm_iv:.1%} << realized {sigma_real:.1%}: "
            "options are cheap vs recent moves — directional bias may be underpriced."
        )
    if noise.p_stop_hit_noise > 0.55:
        notes.append(
            f"Stop has {noise.p_stop_hit_noise:.0%} chance of being hit by noise alone — "
            f"consider widening to ₹{noise.min_safe_stop:.2f} (drops to ~30%)."
        )
    if ev_rw.net_ev_per_share <= 0:
        notes.append(
            "Real-world net EV <= 0 after costs. Edge is not present at these levels."
        )

    return PreTradeVerdict(
        request=request,
        noise=noise,
        implied=implied,
        joint=joint_report,
        ev_riskneutral=ev_rn,
        ev_realworld=ev_rw,
        notes=notes,
    )


def _build_implied_report(chain: OptionChain, request: TradeRequest) -> ImpliedReport:
    today = date.today()
    t_years = max((chain.expiry - today).days / 365.0, 1 / 365.0)
    import numpy as np
    slice_ = ChainSlice(
        spot=chain.spot,
        t_years=t_years,
        strikes=np.array([r.strike for r in chain.rows]),
        call_prices=np.array([r.call_mid for r in chain.rows]),
        put_prices=np.array([r.put_mid for r in chain.rows]),
    )

    atm_iv = iv_at_strike(slice_, chain.spot)
    iv_target = iv_at_strike(slice_, request.target)
    iv_stop = iv_at_strike(slice_, request.stop)

    # First-passage with implied vol at the relevant strike
    horizon = min(request.horizon_days, (chain.expiry - today).days or 1)
    p_touch_target_rn = prob_hit_single_barrier(request.entry, request.target,
                                                iv_target, horizon)
    p_touch_stop_rn = prob_hit_single_barrier(request.entry, request.stop,
                                              iv_stop, horizon)

    vrp = (INDEX_VRP_VOL_POINTS / 100.0
           if request.symbol.upper() in INDEX_SYMBOLS
           else SINGLE_NAME_VRP_VOL_POINTS / 100.0)
    p_touch_target_rw = prob_hit_single_barrier(request.entry, request.target,
                                                max(0.05, iv_target - vrp), horizon)
    p_touch_stop_rw = prob_hit_single_barrier(request.entry, request.stop,
                                              max(0.05, iv_stop - vrp), horizon)

    return ImpliedReport(
        expiry=chain.expiry,
        atm_iv=atm_iv,
        iv_at_target=iv_target,
        iv_at_stop=iv_stop,
        p_touch_target=p_touch_target_rn,
        p_touch_stop=p_touch_stop_rn,
        p_touch_target_realworld=p_touch_target_rw,
        p_touch_stop_realworld=p_touch_stop_rw,
        p_above_target_at_expiry=prob_above_at_expiry(slice_, request.target),
        p_below_stop_at_expiry=prob_below_at_expiry(slice_, request.stop),
    )
