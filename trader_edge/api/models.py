"""Provider-agnostic data shapes the analysis layer consumes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Candle:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class OptionRow:
    strike: float
    call_bid: float
    call_ask: float
    call_oi: int
    put_bid: float
    put_ask: float
    put_oi: int

    @property
    def call_mid(self) -> float:
        if self.call_bid <= 0 or self.call_ask <= 0:
            return max(self.call_bid, self.call_ask)
        return 0.5 * (self.call_bid + self.call_ask)

    @property
    def put_mid(self) -> float:
        if self.put_bid <= 0 or self.put_ask <= 0:
            return max(self.put_bid, self.put_ask)
        return 0.5 * (self.put_bid + self.put_ask)


@dataclass(frozen=True)
class OptionChain:
    symbol: str
    spot: float
    expiry: date
    rows: list[OptionRow] = field(default_factory=list)


@dataclass(frozen=True)
class Order:
    """Minimal shape of a historical order, normalized across providers."""
    order_id: str
    symbol: str
    side: str            # "BUY" | "SELL"
    quantity: int
    price: float
    placed_at: date
    product: str         # "CNC" | "MIS" | "NRML"
    status: str          # "EXECUTED" | "CANCELLED" | "REJECTED"
