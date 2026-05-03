"""Expected value of a bracketed long trade given hit probabilities.

A "bracketed" trade: enter at `entry`, exit at `target` if hit first, exit at
`stop` if hit first, or exit at expected drift-implied price if neither hits
within horizon.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import DEFAULT_BROKERAGE_PER_SHARE, DEFAULT_SLIPPAGE_BPS


@dataclass(frozen=True)
class EVResult:
    p_target: float
    p_stop: float
    p_neither: float
    gross_ev_per_share: float
    costs_per_share: float
    net_ev_per_share: float
    headline_rr: float
    true_rr: float           # gross EV positive moves / abs(EV negative moves)


def expected_value(
    entry: float,
    target: float,
    stop: float,
    p_target: float,
    p_stop: float,
    *,
    spot_at_no_hit: float | None = None,
    brokerage_per_share: float = DEFAULT_BROKERAGE_PER_SHARE,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> EVResult:
    """Compute net expected value per share assuming a long trade.

    spot_at_no_hit defaults to `entry` (i.e., assume flat exit if neither barrier
    is hit). Pass an alternative if you have a forecast.
    """
    if not (stop < entry < target):
        raise ValueError(f"Need stop ({stop}) < entry ({entry}) < target ({target})")
    p_target = max(0.0, min(1.0, p_target))
    p_stop = max(0.0, min(1.0, p_stop))
    p_neither = max(0.0, 1.0 - p_target - p_stop)
    spot_at_no_hit = entry if spot_at_no_hit is None else spot_at_no_hit

    win = target - entry
    loss = stop - entry  # negative
    flat = spot_at_no_hit - entry

    gross = p_target * win + p_stop * loss + p_neither * flat
    slippage = (slippage_bps / 10_000.0) * entry * 2  # entry + exit
    costs = 2 * brokerage_per_share + slippage
    net = gross - costs

    headline_rr = win / abs(loss) if loss != 0 else float("inf")
    pos_part = p_target * win + max(p_neither * flat, 0)
    neg_part = abs(p_stop * loss) + max(-p_neither * flat, 0)
    true_rr = pos_part / neg_part if neg_part > 0 else float("inf")

    return EVResult(
        p_target=p_target,
        p_stop=p_stop,
        p_neither=p_neither,
        gross_ev_per_share=gross,
        costs_per_share=costs,
        net_ev_per_share=net,
        headline_rr=headline_rr,
        true_rr=true_rr,
    )
