"""Journal pairs entries to exits and computes coherent stats."""
from datetime import date

from trader_edge.analysis.journal import journal, pair_trades
from trader_edge.api.models import Order


def _o(oid, sym, side, qty, price, day):
    return Order(order_id=oid, symbol=sym, side=side, quantity=qty,
                 price=price, placed_at=date(2026, 5, day),
                 product="CNC", status="EXECUTED")


def test_pair_simple_round_trip():
    orders = [
        _o("1", "TCS", "BUY", 10, 4000.0, 1),
        _o("2", "TCS", "SELL", 10, 4100.0, 3),
    ]
    pairs = pair_trades(orders)
    assert len(pairs) == 1
    p = pairs[0]
    assert p.side == "LONG"
    assert p.pnl == 1000.0
    assert p.entry_date == date(2026, 5, 1)
    assert p.exit_date == date(2026, 5, 3)


def test_pair_partial_exits():
    orders = [
        _o("1", "TCS", "BUY", 10, 4000.0, 1),
        _o("2", "TCS", "SELL", 4, 4100.0, 2),
        _o("3", "TCS", "SELL", 6, 4050.0, 3),
    ]
    pairs = pair_trades(orders)
    assert len(pairs) == 2
    # 4 @ +100 = 400, 6 @ +50 = 300, total = 700
    total_pnl = sum(p.pnl or 0 for p in pairs)
    assert total_pnl == 700.0


def test_journal_summary_coherent():
    orders = [
        _o("1", "TCS", "BUY", 10, 4000, 1),
        _o("2", "TCS", "SELL", 10, 4100, 3),   # +1000 winner
        _o("3", "RELIANCE", "BUY", 5, 2800, 5),
        _o("4", "RELIANCE", "SELL", 5, 2750, 8),  # -250 loser
        _o("5", "NIFTY", "BUY", 1, 24500, 10),
        _o("6", "NIFTY", "SELL", 1, 24300, 12),  # -200 loser
    ]
    s = journal(orders)
    assert s.n_trades == 3
    assert s.n_winners == 1
    assert s.n_losers == 2
    assert abs(s.win_rate - 1/3) < 1e-9
    # gross winnings 1000, gross losses 450
    assert abs(s.profit_factor - 1000 / 450) < 1e-9
