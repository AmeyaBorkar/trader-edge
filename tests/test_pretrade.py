"""End-to-end: analyze a trade with the mock provider and check structure of the verdict."""
from datetime import date

import pytest

from trader_edge.analysis.pretrade import TradeRequest, analyze_trade
from trader_edge.analysis.suggestions import suggest_alternatives
from trader_edge.api.mock_provider import MockProvider


def test_reliance_long_bracket_runs():
    p = MockProvider(today=date(2026, 5, 4))
    req = TradeRequest(symbol="RELIANCE", entry=2850.0, target=3000.0,
                       stop=2800.0, horizon_days=5, quantity=10)
    v = analyze_trade(p, req)

    # Sanity: all probabilities in [0,1]
    assert 0 <= v.noise.p_stop_hit_noise <= 1
    assert 0 <= v.implied.p_touch_target <= 1
    assert 0 <= v.implied.p_touch_stop <= 1
    assert abs(v.joint.p_target_first + v.joint.p_stop_first + v.joint.p_neither - 1.0) < 1e-9
    # ATM IV should be in a sensible range
    assert 0.10 < v.implied.atm_iv < 0.50
    # Realized vol non-zero
    assert v.noise.sigma_realized_annual > 0


def test_validates_invalid_bracket():
    p = MockProvider(today=date(2026, 5, 4))
    req = TradeRequest(symbol="RELIANCE", entry=2850.0, target=2800.0,  # target < entry
                       stop=2700.0, horizon_days=5, quantity=10)
    with pytest.raises(ValueError):
        analyze_trade(p, req)


def test_tight_stop_triggers_widen_suggestion():
    p = MockProvider(today=date(2026, 5, 4))
    # Very tight stop => high noise hit prob => suggestion to widen
    req = TradeRequest(symbol="RELIANCE", entry=2850.0, target=3000.0,
                       stop=2845.0, horizon_days=5, quantity=10)
    v = analyze_trade(p, req)
    assert v.noise.p_stop_hit_noise > 0.5
    suggestions = suggest_alternatives(p, v)
    labels = " ".join(s.label for s in suggestions)
    assert "Widen stop" in labels
