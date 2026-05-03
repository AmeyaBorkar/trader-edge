"""Abstract data provider interface. Real Groww client and mock both implement this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .models import Candle, OptionChain, Order


class DataProvider(ABC):
    @abstractmethod
    def get_ltp(self, symbol: str) -> float:
        ...

    @abstractmethod
    def get_candles(self, symbol: str, start: date, end: date) -> list[Candle]:
        ...

    @abstractmethod
    def get_option_chain(self, underlying: str, expiry: date | None = None) -> OptionChain:
        ...

    @abstractmethod
    def get_recent_orders(self, days: int = 30) -> list[Order]:
        ...
