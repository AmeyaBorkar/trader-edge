"""Option chain inspection endpoint."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ...api.base import DataProvider
from ..dependencies import get_provider
from ..schemas import OptionChainOut, OptionRowOut

router = APIRouter(prefix="/chain", tags=["chain"])


@router.get("/{symbol}", response_model=OptionChainOut)
def get_chain(
    symbol: str,
    expiry: date | None = None,
    provider: DataProvider = Depends(get_provider),
) -> OptionChainOut:
    try:
        chain = provider.get_option_chain(symbol.upper(), expiry=expiry)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return OptionChainOut(
        symbol=chain.symbol,
        spot=chain.spot,
        expiry=chain.expiry,
        rows=[
            OptionRowOut(
                strike=r.strike,
                call_bid=r.call_bid, call_ask=r.call_ask, call_oi=r.call_oi,
                put_bid=r.put_bid, put_ask=r.put_ask, put_oi=r.put_oi,
            )
            for r in chain.rows
        ],
    )
