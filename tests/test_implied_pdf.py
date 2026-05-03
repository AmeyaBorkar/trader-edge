"""Implied PDF should integrate to ~1 and recover the input vol on a flat-smile chain."""
import math

import numpy as np

from trader_edge.math_core.black_scholes import Quote, price as bs_price
from trader_edge.math_core.implied_pdf import (
    ChainSlice,
    fit_smile,
    implied_vol_smile,
    iv_at_strike,
    prob_above_at_expiry,
    terminal_pdf,
)


def _flat_chain(spot=100.0, sigma=0.25, t=0.25, n=21, step=2.5):
    strikes = np.array([spot + (i - n // 2) * step for i in range(n)])
    calls = np.array([bs_price(Quote(spot, k, t, is_call=True), sigma) for k in strikes])
    puts = np.array([bs_price(Quote(spot, k, t, is_call=False), sigma) for k in strikes])
    return ChainSlice(spot=spot, t_years=t, strikes=strikes,
                      call_prices=calls, put_prices=puts)


def test_smile_fitting_recovers_flat_vol():
    chain = _flat_chain(sigma=0.25)
    strikes, ivs = implied_vol_smile(chain)
    assert len(strikes) > 5
    # Flat smile, all IVs should be near 0.25
    assert all(abs(iv - 0.25) < 0.005 for iv in ivs)


def test_iv_at_strike_interpolates():
    chain = _flat_chain(sigma=0.25)
    iv = iv_at_strike(chain, 102.0)
    assert abs(iv - 0.25) < 0.01


def test_terminal_pdf_integrates_to_one():
    chain = _flat_chain(sigma=0.25)
    grid, pdf = terminal_pdf(chain)
    integral = float(np.trapezoid(pdf, grid))
    assert abs(integral - 1.0) < 0.05


def test_prob_above_target_decreasing():
    chain = _flat_chain(sigma=0.25)
    p_low = prob_above_at_expiry(chain, 100.0)
    p_high = prob_above_at_expiry(chain, 110.0)
    assert p_low > p_high
    assert 0 < p_high < p_low < 1


def test_atm_above_prob_near_half():
    chain = _flat_chain(sigma=0.25)
    p = prob_above_at_expiry(chain, chain.spot)
    # With small drift over 3 months, ATM should be roughly 50/50
    assert 0.40 < p < 0.60
