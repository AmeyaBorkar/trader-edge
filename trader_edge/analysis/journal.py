"""Mode 2: trade journal. Score the user's recent orders by what their EV was at entry.

Pure-history analytic. No LLM. The output is a per-trade EV-vs-actual report
plus aggregate leaks (sizing, stop placement, hold time) detected by simple
deterministic rules.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

from ..api.base import DataProvider
from ..api.models import Order


@dataclass(frozen=True)
class TradePair:
    symbol: str
    side: str            # "LONG" | "SHORT"
    entry_date: date
    exit_date: date | None
    entry_price: float
    exit_price: float | None
    quantity: int
    pnl: float | None    # None if still open


def pair_trades(orders: list[Order]) -> list[TradePair]:
    """Walk orders chronologically, FIFO-pair entries to exits per symbol/product."""
    by_symbol: dict[str, list[Order]] = defaultdict(list)
    for o in sorted(orders, key=lambda x: x.placed_at):
        if o.status != "EXECUTED":
            continue
        by_symbol[o.symbol].append(o)

    pairs: list[TradePair] = []
    for symbol, group in by_symbol.items():
        long_queue: list[Order] = []
        short_queue: list[Order] = []
        for o in group:
            if o.side == "BUY":
                if short_queue:
                    short = short_queue.pop(0)
                    qty = min(o.quantity, short.quantity)
                    pnl = (short.price - o.price) * qty
                    pairs.append(TradePair(
                        symbol=symbol, side="SHORT",
                        entry_date=short.placed_at, exit_date=o.placed_at,
                        entry_price=short.price, exit_price=o.price,
                        quantity=qty, pnl=pnl,
                    ))
                    if short.quantity > qty:
                        short_queue.insert(0, Order(
                            order_id=short.order_id, symbol=short.symbol,
                            side=short.side, quantity=short.quantity - qty,
                            price=short.price, placed_at=short.placed_at,
                            product=short.product, status=short.status,
                        ))
                else:
                    long_queue.append(o)
            else:  # SELL
                if long_queue:
                    long_o = long_queue.pop(0)
                    qty = min(o.quantity, long_o.quantity)
                    pnl = (o.price - long_o.price) * qty
                    pairs.append(TradePair(
                        symbol=symbol, side="LONG",
                        entry_date=long_o.placed_at, exit_date=o.placed_at,
                        entry_price=long_o.price, exit_price=o.price,
                        quantity=qty, pnl=pnl,
                    ))
                    if long_o.quantity > qty:
                        long_queue.insert(0, Order(
                            order_id=long_o.order_id, symbol=long_o.symbol,
                            side=long_o.side, quantity=long_o.quantity - qty,
                            price=long_o.price, placed_at=long_o.placed_at,
                            product=long_o.product, status=long_o.status,
                        ))
                else:
                    short_queue.append(o)

        for stub in long_queue:
            pairs.append(TradePair(
                symbol=symbol, side="LONG", entry_date=stub.placed_at,
                exit_date=None, entry_price=stub.price, exit_price=None,
                quantity=stub.quantity, pnl=None,
            ))
        for stub in short_queue:
            pairs.append(TradePair(
                symbol=symbol, side="SHORT", entry_date=stub.placed_at,
                exit_date=None, entry_price=stub.price, exit_price=None,
                quantity=stub.quantity, pnl=None,
            ))
    return pairs


@dataclass(frozen=True)
class JournalSummary:
    n_trades: int
    n_winners: int
    n_losers: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float           # average pnl per trade (Rs)
    profit_factor: float        # gross_winnings / gross_losses
    median_winner_hold_days: float
    median_loser_hold_days: float
    leaks: list[str]


def journal(orders: list[Order]) -> JournalSummary:
    pairs = [p for p in pair_trades(orders) if p.pnl is not None]
    if not pairs:
        return JournalSummary(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                              ["No closed trades in window."])

    winners = [p for p in pairs if p.pnl > 0]
    losers = [p for p in pairs if p.pnl < 0]

    win_rate = len(winners) / len(pairs)
    avg_win = mean(p.pnl for p in winners) if winners else 0.0
    avg_loss = mean(p.pnl for p in losers) if losers else 0.0
    expectancy = mean(p.pnl for p in pairs)
    gross_winnings = sum(p.pnl for p in winners) if winners else 0.0
    gross_losses = -sum(p.pnl for p in losers) if losers else 0.0
    profit_factor = gross_winnings / gross_losses if gross_losses > 0 else float("inf")

    def hold_days(p: TradePair) -> int:
        return (p.exit_date - p.entry_date).days if p.exit_date else 0

    med_win_hold = median([hold_days(p) for p in winners]) if winners else 0.0
    med_loss_hold = median([hold_days(p) for p in losers]) if losers else 0.0

    leaks: list[str] = []
    if win_rate < 0.4 and avg_win < abs(avg_loss):
        leaks.append(
            "Low win rate AND average loser bigger than average winner — "
            "the classic 'cut winners, hold losers' pattern."
        )
    if med_loss_hold > med_win_hold * 1.5 and med_win_hold > 0:
        leaks.append(
            f"Median losing trade held {med_loss_hold:.0f}d vs winning "
            f"{med_win_hold:.0f}d — disposition effect: hoping losers come back."
        )
    if profit_factor < 1.0:
        leaks.append(
            f"Profit factor {profit_factor:.2f} < 1: gross losses exceed gross "
            "winnings. Either widen targets, tighten stops, or reduce frequency."
        )
    if expectancy < 0:
        leaks.append(
            f"Negative expectancy: ₹{expectancy:.2f} per trade. "
            "Stop trading with real money until system is fixed."
        )

    return JournalSummary(
        n_trades=len(pairs),
        n_winners=len(winners),
        n_losers=len(losers),
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        profit_factor=profit_factor,
        median_winner_hold_days=float(med_win_hold),
        median_loser_hold_days=float(med_loss_hold),
        leaks=leaks,
    )
