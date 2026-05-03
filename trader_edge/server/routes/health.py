"""Health and capability discovery endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ... import __version__
from ...api.base import DataProvider
from ...api.mock_provider import MockProvider, _MOCK_PROFILES
from ..dependencies import get_provider
from ..schemas import HealthResponse, SymbolsResponse

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def health(provider: DataProvider = Depends(get_provider)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider="mock" if isinstance(provider, MockProvider) else "groww",
        version=__version__,
    )


@router.get("/symbols", response_model=SymbolsResponse)
def symbols(provider: DataProvider = Depends(get_provider)) -> SymbolsResponse:
    """List supported symbols. For the mock provider this is a fixed set;
    for the live Groww provider any F&O symbol will work — this list is just
    a convenience for the UI dropdown."""
    if isinstance(provider, MockProvider):
        return SymbolsResponse(symbols=sorted(_MOCK_PROFILES.keys()), provider="mock")
    common = ["NIFTY", "BANKNIFTY", "FINNIFTY", "RELIANCE", "TCS", "HDFCBANK",
             "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC", "LT"]
    return SymbolsResponse(symbols=common, provider="groww")
