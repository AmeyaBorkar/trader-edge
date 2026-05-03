"""Trade journal endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...analysis.journal import journal as journal_run, pair_trades
from ...api.base import DataProvider
from ..dependencies import get_provider
from ..schemas import JournalResponse, TradePairOut

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=JournalResponse)
def journal(
    days: int = Query(30, ge=1, le=365),
    provider: DataProvider = Depends(get_provider),
) -> JournalResponse:
    orders = provider.get_recent_orders(days=days)
    summary = journal_run(orders)
    pairs = pair_trades(orders)
    return JournalResponse(
        n_trades=summary.n_trades,
        n_winners=summary.n_winners,
        n_losers=summary.n_losers,
        win_rate=summary.win_rate,
        avg_win=summary.avg_win,
        avg_loss=summary.avg_loss,
        expectancy=summary.expectancy,
        profit_factor=summary.profit_factor if summary.profit_factor != float("inf") else 9999.0,
        median_winner_hold_days=summary.median_winner_hold_days,
        median_loser_hold_days=summary.median_loser_hold_days,
        leaks=summary.leaks,
        trades=[
            TradePairOut(
                symbol=p.symbol, side=p.side,
                entry_date=p.entry_date, exit_date=p.exit_date,
                entry_price=p.entry_price, exit_price=p.exit_price,
                quantity=p.quantity, pnl=p.pnl,
            )
            for p in pairs
        ],
    )
