"""Append-only CSV log of pre-trade analyses, for personal calibration.

Each call to `analyze` writes one row. After your trade closes, manually edit
the CSV to fill in `actual_outcome` (win/loss/flat/skipped) and `actual_pnl`
(realized P&L for the trade). Then run `trader-edge log --stats` to see how
well the engine's predictions calibrate against your real outcomes.

Default location: ~/.trader_edge/log.csv  (override with TRADER_EDGE_LOG_PATH).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .pretrade import PreTradeVerdict

FIELDS = [
    "timestamp",
    "symbol", "entry", "target", "stop", "horizon_days", "quantity",
    "sigma_realized", "p_stop_noise", "noise_safe_stop",
    "atm_iv", "iv_target", "iv_stop",
    "p_touch_target_rn", "p_touch_stop_rn",
    "p_target_first", "p_stop_first", "p_neither",
    "headline_rr", "true_rr",
    "ev_rn_per_share", "ev_rw_per_share", "total_ev_rw",
    "actual_outcome",  # blank — fill manually: "win" / "loss" / "flat" / "skipped"
    "actual_pnl",      # blank — fill manually with realized P&L (rupees, signed)
    "tag",
]


def default_log_path() -> Path:
    explicit = os.environ.get("TRADER_EDGE_LOG_PATH")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".trader_edge" / "log.csv"


def append_verdict(verdict: PreTradeVerdict, *,
                   log_path: Path | None = None,
                   tag: str = "") -> Path:
    path = log_path or default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(_row(verdict, tag))
    return path


def _row(v: PreTradeVerdict, tag: str) -> dict:
    req = v.request
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbol": req.symbol,
        "entry": f"{req.entry:.4f}",
        "target": f"{req.target:.4f}",
        "stop": f"{req.stop:.4f}",
        "horizon_days": req.horizon_days,
        "quantity": req.quantity,
        "sigma_realized": f"{v.noise.sigma_realized_annual:.6f}",
        "p_stop_noise": f"{v.noise.p_stop_hit_noise:.6f}",
        "noise_safe_stop": f"{v.noise.min_safe_stop:.4f}",
        "atm_iv": f"{v.implied.atm_iv:.6f}",
        "iv_target": f"{v.implied.iv_at_target:.6f}",
        "iv_stop": f"{v.implied.iv_at_stop:.6f}",
        "p_touch_target_rn": f"{v.implied.p_touch_target:.6f}",
        "p_touch_stop_rn": f"{v.implied.p_touch_stop:.6f}",
        "p_target_first": f"{v.joint.p_target_first:.6f}",
        "p_stop_first": f"{v.joint.p_stop_first:.6f}",
        "p_neither": f"{v.joint.p_neither:.6f}",
        "headline_rr": f"{v.ev_riskneutral.headline_rr:.4f}",
        "true_rr": f"{v.ev_riskneutral.true_rr:.4f}",
        "ev_rn_per_share": f"{v.ev_riskneutral.net_ev_per_share:.4f}",
        "ev_rw_per_share": f"{v.ev_realworld.net_ev_per_share:.4f}",
        "total_ev_rw": f"{v.ev_realworld.net_ev_per_share * req.quantity:.4f}",
        "actual_outcome": "",
        "actual_pnl": "",
        "tag": tag,
    }


def read_log(log_path: Path | None = None) -> list[dict]:
    path = log_path or default_log_path()
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class CalibrationSummary:
    n_total: int
    n_with_outcome: int
    n_taken: int                  # filled outcome and != "skipped"
    avg_predicted_ev: float
    avg_actual_pnl_per_share: float
    correlation: float | None     # Pearson(predicted EV/sh, actual P&L/sh)
    n_correct_direction: int
    n_wrong_direction: int


def calibration(rows: Iterable[dict]) -> CalibrationSummary:
    rows = list(rows)
    n_total = len(rows)
    n_with_outcome = sum(1 for r in rows if (r.get("actual_outcome") or "").strip())
    closed = [r for r in rows
              if (r.get("actual_outcome") or "").strip()
              and r["actual_outcome"].strip().lower() != "skipped"
              and (r.get("actual_pnl") or "").strip()]
    n_taken = len(closed)

    if n_taken == 0:
        return CalibrationSummary(n_total, n_with_outcome, 0, 0.0, 0.0, None, 0, 0)

    preds = [float(r["ev_rw_per_share"]) for r in closed]
    actuals: list[float] = []
    for r in closed:
        try:
            qty = max(int(r["quantity"]), 1)
            actuals.append(float(r["actual_pnl"]) / qty)
        except (ValueError, KeyError, ZeroDivisionError):
            actuals.append(0.0)

    avg_pred = sum(preds) / n_taken
    avg_actual = sum(actuals) / n_taken

    correlation: float | None = None
    if n_taken >= 5:
        mean_p, mean_a = avg_pred, avg_actual
        num = sum((p - mean_p) * (a - mean_a) for p, a in zip(preds, actuals))
        denom_p = (sum((p - mean_p) ** 2 for p in preds)) ** 0.5
        denom_a = (sum((a - mean_a) ** 2 for a in actuals)) ** 0.5
        if denom_p > 0 and denom_a > 0:
            correlation = num / (denom_p * denom_a)

    n_correct = sum(1 for p, a in zip(preds, actuals)
                    if (p > 0) == (a > 0))
    n_wrong = n_taken - n_correct

    return CalibrationSummary(
        n_total=n_total,
        n_with_outcome=n_with_outcome,
        n_taken=n_taken,
        avg_predicted_ev=avg_pred,
        avg_actual_pnl_per_share=avg_actual,
        correlation=correlation,
        n_correct_direction=n_correct,
        n_wrong_direction=n_wrong,
    )
