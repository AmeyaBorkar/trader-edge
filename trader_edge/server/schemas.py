"""Pydantic schemas for request bodies and response payloads.

Mirrors the dataclasses in `analysis/pretrade.py` and `analysis/journal.py`
but keeps the wire format independent so we can evolve internals without
breaking the API.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class TradeRequestIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20, examples=["RELIANCE"])
    entry: float = Field(..., gt=0, examples=[2850.0])
    target: float = Field(..., gt=0, examples=[3000.0])
    stop: float = Field(..., gt=0, examples=[2800.0])
    horizon_days: int = Field(5, ge=1, le=90)
    quantity: int = Field(1, ge=1)

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class NoiseStopOut(BaseModel):
    sigma_realized_annual: float
    p_stop_hit_noise: float
    min_safe_stop: float
    horizon_days: int


class ImpliedOut(BaseModel):
    expiry: date
    atm_iv: float
    iv_at_target: float
    iv_at_stop: float
    p_touch_target: float
    p_touch_stop: float
    p_touch_target_realworld: float
    p_touch_stop_realworld: float
    p_above_target_at_expiry: float
    p_below_stop_at_expiry: float


class JointOut(BaseModel):
    p_target_first: float
    p_stop_first: float
    p_neither: float
    expected_exit_days: float


class EVOut(BaseModel):
    p_target: float
    p_stop: float
    p_neither: float
    gross_ev_per_share: float
    costs_per_share: float
    net_ev_per_share: float
    headline_rr: float
    true_rr: float


class SuggestionOut(BaseModel):
    label: str
    detail: str
    new_request: TradeRequestIn | None = None
    new_net_ev_per_share: float | None = None


class AnalyzeResponse(BaseModel):
    request: TradeRequestIn
    noise: NoiseStopOut
    implied: ImpliedOut
    joint: JointOut
    ev_riskneutral: EVOut
    ev_realworld: EVOut
    notes: list[str]
    suggestions: list[SuggestionOut]


class OptionRowOut(BaseModel):
    strike: float
    call_bid: float
    call_ask: float
    call_oi: int
    put_bid: float
    put_ask: float
    put_oi: int


class OptionChainOut(BaseModel):
    symbol: str
    spot: float
    expiry: date
    rows: list[OptionRowOut]


class TradePairOut(BaseModel):
    symbol: str
    side: str
    entry_date: date
    exit_date: date | None
    entry_price: float
    exit_price: float | None
    quantity: int
    pnl: float | None


class JournalResponse(BaseModel):
    n_trades: int
    n_winners: int
    n_losers: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float
    profit_factor: float
    median_winner_hold_days: float
    median_loser_hold_days: float
    leaks: list[str]
    trades: list[TradePairOut]


class HealthResponse(BaseModel):
    status: str
    provider: str
    version: str


class SymbolsResponse(BaseModel):
    symbols: list[str]
    provider: str
