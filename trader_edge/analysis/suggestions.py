"""Generate alternative trade structures that improve EV."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..api.base import DataProvider
from .pretrade import (
    PreTradeVerdict,
    TradeRequest,
    analyze_trade,
)


@dataclass(frozen=True)
class Suggestion:
    label: str
    detail: str
    new_request: TradeRequest | None
    new_verdict: PreTradeVerdict | None


def suggest_alternatives(
    provider: DataProvider,
    verdict: PreTradeVerdict,
    *,
    chain_expiry: date | None = None,
) -> list[Suggestion]:
    out: list[Suggestion] = []
    req = verdict.request

    # 1. Widen the stop to the noise-safe level if current stop is risky
    if verdict.noise.p_stop_hit_noise > 0.40:
        new_stop = round(verdict.noise.min_safe_stop / 0.5) * 0.5
        if new_stop < req.entry and new_stop != req.stop:
            new_req = TradeRequest(
                symbol=req.symbol, entry=req.entry, target=req.target,
                stop=new_stop, horizon_days=req.horizon_days, quantity=req.quantity,
            )
            try:
                new_v = analyze_trade(provider, new_req, chain_expiry=chain_expiry)
                out.append(Suggestion(
                    label=f"Widen stop to ₹{new_stop:.2f}",
                    detail=(
                        f"Drops noise-hit prob {verdict.noise.p_stop_hit_noise:.0%} "
                        f"-> {new_v.noise.p_stop_hit_noise:.0%}. "
                        f"EV: ₹{verdict.ev_realworld.net_ev_per_share:.2f} "
                        f"-> ₹{new_v.ev_realworld.net_ev_per_share:.2f} per share."
                    ),
                    new_request=new_req,
                    new_verdict=new_v,
                ))
            except Exception:
                pass

    # 2. Tighter target if implied target prob is low
    if verdict.implied.p_touch_target < 0.20 and req.target > req.entry:
        midpoint = (req.entry + req.target) / 2
        new_target = round(midpoint / 0.5) * 0.5
        new_req = TradeRequest(
            symbol=req.symbol, entry=req.entry, target=new_target,
            stop=req.stop, horizon_days=req.horizon_days, quantity=req.quantity,
        )
        try:
            new_v = analyze_trade(provider, new_req, chain_expiry=chain_expiry)
            out.append(Suggestion(
                label=f"Realistic target ₹{new_target:.2f}",
                detail=(
                    f"Original target probability was only "
                    f"{verdict.implied.p_touch_target:.0%}. "
                    f"At ₹{new_target:.2f} it's "
                    f"{new_v.implied.p_touch_target:.0%}. "
                    f"EV: ₹{verdict.ev_realworld.net_ev_per_share:.2f} "
                    f"-> ₹{new_v.ev_realworld.net_ev_per_share:.2f}."
                ),
                new_request=new_req,
                new_verdict=new_v,
            ))
        except Exception:
            pass

    # 3. Skip
    if verdict.ev_realworld.net_ev_per_share <= 0:
        out.append(Suggestion(
            label="Skip the trade",
            detail=(
                "Real-world EV is non-positive after costs. "
                "Either the move is overpriced by the chain or your stop is "
                "in the noise zone — there is no statistical edge to capture."
            ),
            new_request=None,
            new_verdict=None,
        ))

    return out
