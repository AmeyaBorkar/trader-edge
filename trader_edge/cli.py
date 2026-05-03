"""Command-line interface for trader-edge.

Examples:
  python -m trader_edge.cli analyze RELIANCE 2850 3000 2800 --days 3
  python -m trader_edge.cli analyze NIFTY 24500 25000 24300 --days 5 --provider mock
  python -m trader_edge.cli journal --days 30 --provider mock
  python -m trader_edge.cli chain RELIANCE --provider mock
"""
from __future__ import annotations

import os
import sys

# Make Windows consoles handle the ₹ symbol and box-drawing chars
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .env import load_env
load_env()

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .analysis.journal import journal as journal_run
from .analysis.pretrade import TradeRequest, analyze_trade
from .analysis.suggestions import suggest_alternatives
from .analysis.trade_log import (
    append_verdict,
    calibration,
    default_log_path,
    read_log,
)
from .api.base import DataProvider
from .api.mock_provider import MockProvider

console = Console()


def _resolve_provider(name: str) -> DataProvider:
    name = (name or "auto").lower()
    if name == "auto":
        # CLI flag has lowest precedence; env override wins so a user with a
        # configured .env doesn't have to pass --provider every invocation.
        env_choice = (os.environ.get("TRADER_EDGE_PROVIDER") or "").strip().lower()
        if env_choice in ("mock", "groww"):
            name = env_choice
    if name == "mock":
        return MockProvider()
    if name == "groww":
        from .api.groww_client import GrowwClient
        return GrowwClient()
    if os.environ.get("GROWW_ACCESS_TOKEN"):
        from .api.groww_client import GrowwClient
        return GrowwClient()
    console.print("[dim]No GROWW_ACCESS_TOKEN — using mock provider.[/dim]")
    return MockProvider()


@click.group()
def cli():
    """Deterministic pre-trade risk engine for Indian equities and F&O."""


@cli.command()
@click.argument("symbol")
@click.argument("entry", type=float)
@click.argument("target", type=float)
@click.argument("stop", type=float)
@click.option("--days", "horizon_days", type=int, default=5,
              help="Hold horizon in trading days")
@click.option("--qty", "quantity", type=int, default=1)
@click.option("--provider", default="auto",
              type=click.Choice(["auto", "mock", "groww"], case_sensitive=False))
@click.option("--no-log", is_flag=True,
              help="Skip appending this analysis to the trade log")
@click.option("--tag", default="",
              help="Optional label saved with this entry (e.g. setup name)")
def analyze(symbol: str, entry: float, target: float, stop: float,
            horizon_days: int, quantity: int, provider: str,
            no_log: bool, tag: str):
    """Analyze a long-bracket trade: ANALYZE SYMBOL ENTRY TARGET STOP."""
    p = _resolve_provider(provider)
    req = TradeRequest(symbol=symbol.upper(), entry=entry, target=target,
                       stop=stop, horizon_days=horizon_days, quantity=quantity)
    verdict = analyze_trade(p, req)
    suggestions = suggest_alternatives(p, verdict)
    _render_verdict(verdict)
    if suggestions:
        _render_suggestions(suggestions)
    if not no_log:
        path = append_verdict(verdict, tag=tag)
        console.print(f"[dim]Logged to {path}[/dim]")


@cli.command()
@click.option("--days", "lookback_days", type=int, default=30)
@click.option("--provider", default="auto",
              type=click.Choice(["auto", "mock", "groww"], case_sensitive=False))
def journal(lookback_days: int, provider: str):
    """Score recent trades and surface behavioral leaks."""
    p = _resolve_provider(provider)
    orders = p.get_recent_orders(days=lookback_days)
    summary = journal_run(orders)
    _render_journal(summary, lookback_days)


@cli.command()
@click.argument("symbol")
@click.option("--provider", default="auto",
              type=click.Choice(["auto", "mock", "groww"], case_sensitive=False))
def chain(symbol: str, provider: str):
    """Print the option chain (used for sanity-checking the data feed)."""
    p = _resolve_provider(provider)
    ch = p.get_option_chain(symbol.upper())
    table = Table(title=f"{symbol.upper()} chain — spot ₹{ch.spot:.2f}, expiry {ch.expiry}")
    table.add_column("Strike", justify="right")
    table.add_column("CE Bid", justify="right")
    table.add_column("CE Ask", justify="right")
    table.add_column("CE OI", justify="right")
    table.add_column("PE Bid", justify="right")
    table.add_column("PE Ask", justify="right")
    table.add_column("PE OI", justify="right")
    for r in ch.rows:
        atm = abs(r.strike - ch.spot) < (ch.spot * 0.005)
        style = "bold yellow" if atm else None
        table.add_row(
            f"{r.strike:.2f}", f"{r.call_bid:.2f}", f"{r.call_ask:.2f}",
            f"{r.call_oi:,}", f"{r.put_bid:.2f}", f"{r.put_ask:.2f}",
            f"{r.put_oi:,}", style=style,
        )
    console.print(table)


def _render_verdict(v) -> None:
    req = v.request
    title = f"{req.symbol} long bracket — ₹{req.entry:.2f} -> target ₹{req.target:.2f}, stop ₹{req.stop:.2f}, {req.horizon_days}d"

    body = []
    body.append(f"[bold]NOISE STOP CHECK[/bold]")
    body.append(f"  Realized vol (ann.):   {v.noise.sigma_realized_annual:.1%}")
    color = "red" if v.noise.p_stop_hit_noise > 0.55 else \
            "yellow" if v.noise.p_stop_hit_noise > 0.35 else "green"
    body.append(
        f"  P(stop hit by noise):  [{color}]{v.noise.p_stop_hit_noise:.0%}[/{color}]"
    )
    body.append(f"  Noise-safe stop:       ₹{v.noise.min_safe_stop:.2f} (~30% noise hit)")

    body.append("")
    body.append(f"[bold]OPTIONS-CHAIN ORACLE  (expiry {v.implied.expiry})[/bold]")
    body.append(f"  ATM IV:                {v.implied.atm_iv:.1%}")
    body.append(f"  IV @ target:           {v.implied.iv_at_target:.1%}")
    body.append(f"  IV @ stop:             {v.implied.iv_at_stop:.1%}")
    body.append(
        f"  P(touch target):       {v.implied.p_touch_target:.0%} "
        f"(real-world ~{v.implied.p_touch_target_realworld:.0%})"
    )
    body.append(
        f"  P(touch stop):         {v.implied.p_touch_stop:.0%} "
        f"(real-world ~{v.implied.p_touch_stop_realworld:.0%})"
    )

    body.append("")
    body.append("[bold]WHO HITS FIRST  (Monte Carlo at implied vol)[/bold]")
    body.append(f"  P(target first):       {v.joint.p_target_first:.0%}")
    body.append(f"  P(stop first):         {v.joint.p_stop_first:.0%}")
    body.append(f"  P(neither in horizon): {v.joint.p_neither:.0%}")
    body.append(f"  Expected exit:         day {v.joint.expected_exit_days:.1f}")

    body.append("")
    body.append("[bold]EXPECTED VALUE[/bold]")
    body.append(f"  Headline R:R:          {v.ev_riskneutral.headline_rr:.2f}:1")
    body.append(f"  True R:R (joint):      {v.ev_riskneutral.true_rr:.2f}:1")
    rn_color = "green" if v.ev_riskneutral.net_ev_per_share > 0 else "red"
    rw_color = "green" if v.ev_realworld.net_ev_per_share > 0 else "red"
    body.append(
        f"  Net EV (risk-neutral): [{rn_color}]₹{v.ev_riskneutral.net_ev_per_share:+.2f}/share[/{rn_color}]"
    )
    body.append(
        f"  Net EV (real-world):   [{rw_color}]₹{v.ev_realworld.net_ev_per_share:+.2f}/share[/{rw_color}]"
    )
    body.append(
        f"  Per-trade total ({req.quantity}q): "
        f"[{rw_color}]₹{v.ev_realworld.net_ev_per_share * req.quantity:+.2f}[/{rw_color}]"
    )

    if v.notes:
        body.append("")
        body.append("[bold]NOTES[/bold]")
        for n in v.notes:
            body.append(f"  • {n}")

    console.print(Panel("\n".join(body), title=title, border_style="cyan"))


def _render_suggestions(suggestions) -> None:
    body = []
    for i, s in enumerate(suggestions, 1):
        body.append(f"[bold]{i}. {s.label}[/bold]")
        body.append(f"   {s.detail}")
        body.append("")
    console.print(Panel("\n".join(body).rstrip(), title="ALTERNATIVES",
                        border_style="magenta"))


def _render_journal(s, days: int) -> None:
    title = f"Trade journal — last {days}d"
    body = []
    body.append(f"  Trades:           {s.n_trades}  ({s.n_winners}W / {s.n_losers}L)")
    if s.n_trades > 0:
        wr_color = "green" if s.win_rate >= 0.5 else "red"
        body.append(f"  Win rate:         [{wr_color}]{s.win_rate:.0%}[/{wr_color}]")
        body.append(f"  Avg winner:       ₹{s.avg_win:+.2f}")
        body.append(f"  Avg loser:        ₹{s.avg_loss:+.2f}")
        exp_color = "green" if s.expectancy > 0 else "red"
        body.append(
            f"  Expectancy/trade: [{exp_color}]₹{s.expectancy:+.2f}[/{exp_color}]"
        )
        pf_color = "green" if s.profit_factor > 1.0 else "red"
        body.append(
            f"  Profit factor:    [{pf_color}]{s.profit_factor:.2f}[/{pf_color}]"
        )
        body.append(f"  Median hold:      winners {s.median_winner_hold_days:.0f}d, "
                    f"losers {s.median_loser_hold_days:.0f}d")
    if s.leaks:
        body.append("")
        body.append("[bold red]LEAKS DETECTED[/bold red]")
        for leak in s.leaks:
            body.append(f"  • {leak}")
    console.print(Panel("\n".join(body), title=title, border_style="cyan"))


if __name__ == "__main__":
    cli()
