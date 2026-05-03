"""Trade log writer/reader and calibration math."""
from datetime import date

from trader_edge.analysis.pretrade import TradeRequest, analyze_trade
from trader_edge.analysis.trade_log import (
    append_verdict,
    calibration,
    read_log,
)
from trader_edge.api.mock_provider import MockProvider


def _make_verdict():
    p = MockProvider(today=date(2026, 5, 4))
    req = TradeRequest(symbol="RELIANCE", entry=2850.0, target=3000.0,
                       stop=2800.0, horizon_days=5, quantity=10)
    return analyze_trade(p, req)


def test_append_writes_header_and_row(tmp_path):
    log_path = tmp_path / "log.csv"
    v = _make_verdict()
    append_verdict(v, log_path=log_path, tag="test")
    assert log_path.exists()
    rows = read_log(log_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "RELIANCE"
    assert float(r["entry"]) == 2850.0
    assert r["tag"] == "test"
    assert r["actual_outcome"] == ""  # empty until user fills it


def test_append_creates_parent_dir(tmp_path):
    log_path = tmp_path / "nested" / "deep" / "log.csv"
    v = _make_verdict()
    append_verdict(v, log_path=log_path)
    assert log_path.exists()


def test_multiple_appends_share_one_header(tmp_path):
    log_path = tmp_path / "log.csv"
    v = _make_verdict()
    append_verdict(v, log_path=log_path)
    append_verdict(v, log_path=log_path)
    append_verdict(v, log_path=log_path)
    text = log_path.read_text(encoding="utf-8")
    assert text.count("timestamp,symbol") == 1
    assert len(read_log(log_path)) == 3


def test_calibration_with_no_outcomes(tmp_path):
    log_path = tmp_path / "log.csv"
    v = _make_verdict()
    append_verdict(v, log_path=log_path)
    s = calibration(read_log(log_path))
    assert s.n_total == 1
    assert s.n_taken == 0
    assert s.correlation is None


def test_calibration_with_outcomes_correlates():
    rows = []
    for i, (pred, actual_per_share) in enumerate([
        (5.0, 7.0), (3.0, 4.0), (-2.0, -3.0), (-8.0, -6.0),
        (1.0, 2.0), (4.0, 5.0), (-1.0, 0.5),
    ]):
        rows.append({
            "timestamp": f"2026-05-{i+1:02d}T10:00:00",
            "symbol": "TEST",
            "entry": "100", "target": "110", "stop": "95",
            "horizon_days": "5", "quantity": "1",
            "ev_rw_per_share": str(pred),
            "actual_outcome": "win" if actual_per_share > 0 else "loss",
            "actual_pnl": str(actual_per_share),  # qty=1 so per-share == total
        })
    s = calibration(rows)
    assert s.n_total == 7
    assert s.n_taken == 7
    assert s.correlation is not None
    assert s.correlation > 0.9
    assert s.n_correct_direction >= 6


def test_calibration_skipped_excluded():
    rows = [
        {"actual_outcome": "skipped", "actual_pnl": "", "ev_rw_per_share": "-5",
         "quantity": "1"},
        {"actual_outcome": "win", "actual_pnl": "10", "ev_rw_per_share": "3",
         "quantity": "1"},
    ]
    s = calibration(rows)
    assert s.n_total == 2
    assert s.n_taken == 1
    assert s.n_with_outcome == 2
