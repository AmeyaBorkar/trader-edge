"""BS pricing -> IV inversion round-trip should be near-exact."""
import math

import pytest

from trader_edge.math_core.black_scholes import Quote, implied_vol, price, vega


@pytest.mark.parametrize("strike,is_call,sigma", [
    (100, True, 0.20),
    (100, False, 0.20),
    (90, True, 0.30),
    (110, False, 0.15),
    (120, True, 0.25),
    (80, False, 0.40),
])
def test_iv_round_trip(strike, is_call, sigma):
    q = Quote(spot=100.0, strike=strike, t_years=0.5, is_call=is_call)
    p = price(q, sigma)
    iv = implied_vol(q, p)
    assert abs(iv - sigma) < 1e-4, f"round-trip failed: in={sigma}, out={iv}"


def test_vega_positive_for_atm():
    q = Quote(spot=100.0, strike=100.0, t_years=0.5)
    assert vega(q, 0.20) > 0


def test_iv_rejects_below_intrinsic():
    q = Quote(spot=100.0, strike=80.0, t_years=0.25, is_call=True)
    with pytest.raises(ValueError):
        implied_vol(q, 5.0)  # intrinsic is 20, this is below
