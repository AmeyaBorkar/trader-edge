"""Pre-trade analysis endpoint."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from ...analysis.pretrade import TradeRequest, analyze_trade
from ...analysis.suggestions import suggest_alternatives
from ...api.base import DataProvider
from ..dependencies import get_provider
from ..schemas import (
    AnalyzeResponse,
    EVOut,
    ImpliedOut,
    JointOut,
    NoiseStopOut,
    SuggestionOut,
    TradeRequestIn,
)

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=AnalyzeResponse)
def analyze(req: TradeRequestIn, provider: DataProvider = Depends(get_provider)) -> AnalyzeResponse:
    if not (req.stop < req.entry < req.target):
        raise HTTPException(
            status_code=400,
            detail=f"Need stop ({req.stop}) < entry ({req.entry}) < target ({req.target}) "
                   "for a long bracket.",
        )
    domain_req = TradeRequest(
        symbol=req.symbol, entry=req.entry, target=req.target,
        stop=req.stop, horizon_days=req.horizon_days, quantity=req.quantity,
    )
    try:
        verdict = analyze_trade(provider, domain_req)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    suggestions = suggest_alternatives(provider, verdict)

    return AnalyzeResponse(
        request=req,
        noise=NoiseStopOut(**asdict(verdict.noise)),
        implied=ImpliedOut(**asdict(verdict.implied)),
        joint=JointOut(**asdict(verdict.joint)),
        ev_riskneutral=EVOut(**asdict(verdict.ev_riskneutral)),
        ev_realworld=EVOut(**asdict(verdict.ev_realworld)),
        notes=verdict.notes,
        suggestions=[
            SuggestionOut(
                label=s.label,
                detail=s.detail,
                new_request=TradeRequestIn(
                    symbol=s.new_request.symbol, entry=s.new_request.entry,
                    target=s.new_request.target, stop=s.new_request.stop,
                    horizon_days=s.new_request.horizon_days,
                    quantity=s.new_request.quantity,
                ) if s.new_request else None,
                new_net_ev_per_share=(
                    s.new_verdict.ev_realworld.net_ev_per_share
                    if s.new_verdict else None
                ),
            )
            for s in suggestions
        ],
    )
