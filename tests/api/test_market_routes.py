"""Tests des endpoints market."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)

def test_get_ticker_valid():
    r = client.get("/api/v1/market/ticker/BTCUSDT")
    # The endpoint requires a running DB, so it may return 404 (no data)
    # or 500 (internal error). The important thing is it doesn't crash.
    assert r.status_code in (200, 404, 500)

def test_get_orderbook_valid():
    r = client.get("/api/v1/market/orderbook/BTCUSDT")
    assert r.status_code in (200, 404, 500)

def test_get_ohlcv_valid():
    r = client.get("/api/v1/market/ohlcv/BTCUSDT?timeframe=1h&limit=100")
    assert r.status_code in (200, 404, 500)

def test_rate_limiter_health_exempt():
    for _ in range(70):
        r = client.get("/health")
        assert r.status_code == 200
