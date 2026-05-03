"""Groww REST client.

Reference: https://groww.in/trade-api/docs (verify endpoints/payloads against
latest docs — Groww's API is young and may rev fields).

Authentication: pass an access token issued from your Groww developer console.
Set env var GROWW_ACCESS_TOKEN, or pass `access_token=` to the constructor.

This client implements only the read endpoints needed for the analysis engine
(LTP, historical candles, option chain, order history). Order placement is
intentionally not exposed here — the engine is read-only by design.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import requests

from .base import DataProvider
from .models import Candle, OptionChain, OptionRow, Order

DEFAULT_BASE_URL = "https://api.groww.in"


class GrowwClient(DataProvider):
    def __init__(self, access_token: str | None = None, timeout: float = 10.0,
                 base_url: str | None = None):
        token = access_token or os.environ.get("GROWW_ACCESS_TOKEN")
        if not token:
            raise RuntimeError(
                "No access token. Set GROWW_ACCESS_TOKEN env var or pass access_token=."
            )
        self.base_url = (base_url
                         or os.environ.get("GROWW_API_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-API-VERSION": "1.0",
        })
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_ltp(self, symbol: str) -> float:
        # GET /v1/live-data/ltp?exchange=NSE&segment=CASH&trading_symbol=RELIANCE
        data = self._get("/v1/live-data/ltp", {
            "exchange": "NSE",
            "segment": "CASH",
            "trading_symbol": symbol,
        })
        # Groww returns {"status":"SUCCESS","payload":{"NSE_RELIANCE":{"ltp":2850.4,...}}}
        payload = data.get("payload", {})
        for v in payload.values():
            if isinstance(v, dict) and "ltp" in v:
                return float(v["ltp"])
        raise RuntimeError(f"Unexpected LTP payload: {data}")

    def get_candles(self, symbol: str, start: date, end: date) -> list[Candle]:
        # GET /v1/historical/candle/range
        data = self._get("/v1/historical/candle/range", {
            "exchange": "NSE",
            "segment": "CASH",
            "trading_symbol": symbol,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "interval_in_minutes": 1440,  # daily
        })
        candles = data.get("payload", {}).get("candles", [])
        out: list[Candle] = []
        for c in candles:
            # Format: [epoch_ms, open, high, low, close, volume]
            ts = datetime.fromtimestamp(c[0] / 1000).date()
            out.append(Candle(ts, float(c[1]), float(c[2]), float(c[3]),
                              float(c[4]), int(c[5])))
        return out

    def get_option_chain(self, underlying: str, expiry: date | None = None) -> OptionChain:
        # GET /v1/live-data/option-chain?trading_symbol=NIFTY&expiry=YYYY-MM-DD
        params = {"trading_symbol": underlying}
        if expiry:
            params["expiry"] = expiry.isoformat()
        data = self._get("/v1/live-data/option-chain", params)
        payload = data.get("payload", {})
        spot = float(payload.get("underlying_value") or payload.get("spot") or 0.0)
        exp_str = payload.get("expiry") or (expiry.isoformat() if expiry else None)
        if exp_str is None:
            raise RuntimeError("Chain payload missing expiry")
        exp_date = date.fromisoformat(exp_str)
        rows: list[OptionRow] = []
        for r in payload.get("strikes", []):
            ce = r.get("CE", {})
            pe = r.get("PE", {})
            rows.append(OptionRow(
                strike=float(r["strike"]),
                call_bid=float(ce.get("bid", 0) or 0),
                call_ask=float(ce.get("ask", 0) or 0),
                call_oi=int(ce.get("oi", 0) or 0),
                put_bid=float(pe.get("bid", 0) or 0),
                put_ask=float(pe.get("ask", 0) or 0),
                put_oi=int(pe.get("oi", 0) or 0),
            ))
        return OptionChain(symbol=underlying, spot=spot, expiry=exp_date, rows=rows)

    def get_recent_orders(self, days: int = 30) -> list[Order]:
        # GET /v1/order/list?from=YYYY-MM-DD&to=YYYY-MM-DD
        end = date.today()
        start = end - timedelta(days=days)
        data = self._get("/v1/order/list", {
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
        })
        out: list[Order] = []
        for o in data.get("payload", {}).get("orders", []):
            try:
                placed = date.fromisoformat(o["created_at"][:10])
            except (KeyError, ValueError):
                continue
            out.append(Order(
                order_id=str(o.get("order_id", "")),
                symbol=str(o.get("trading_symbol", "")),
                side=str(o.get("transaction_type", "")).upper(),
                quantity=int(o.get("quantity", 0)),
                price=float(o.get("price") or o.get("average_price") or 0.0),
                placed_at=placed,
                product=str(o.get("product", "")),
                status=str(o.get("order_status", "")).upper(),
            ))
        return out
