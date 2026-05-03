"""Smoke tests for the HTTP layer using FastAPI's TestClient."""
from fastapi.testclient import TestClient

from trader_edge.server.dependencies import reset_provider_cache
from trader_edge.server.main import app

client = TestClient(app)


def setup_function(_):
    reset_provider_cache()


def test_health_ok():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] in ("mock", "groww")


def test_symbols_returns_list():
    r = client.get("/api/v1/symbols")
    assert r.status_code == 200
    assert "RELIANCE" in r.json()["symbols"]


def test_analyze_endpoint_full_flow():
    r = client.post("/api/v1/analyze", json={
        "symbol": "RELIANCE", "entry": 2850, "target": 3000,
        "stop": 2800, "horizon_days": 5, "quantity": 10,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "noise" in body
    assert "implied" in body
    assert "ev_realworld" in body
    assert 0 <= body["noise"]["p_stop_hit_noise"] <= 1
    assert isinstance(body["suggestions"], list)


def test_analyze_rejects_invalid_bracket():
    r = client.post("/api/v1/analyze", json={
        "symbol": "RELIANCE", "entry": 2850, "target": 2800,
        "stop": 2700, "horizon_days": 5, "quantity": 1,
    })
    assert r.status_code == 400


def test_chain_endpoint():
    r = client.get("/api/v1/chain/RELIANCE")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE"
    assert len(body["rows"]) > 5


def test_journal_endpoint():
    r = client.get("/api/v1/journal?days=30")
    assert r.status_code == 200
    body = r.json()
    assert "n_trades" in body
    assert "leaks" in body
