"""Tests de tous les endpoints API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)

def test_portfolio_summary():
    r = client.get("/api/v1/portfolio/summary")
    assert r.status_code == 200
    data = r.json()
    assert "total_usd" in data

def test_portfolio_state():
    r = client.get("/api/v1/portfolio/state")
    assert r.status_code == 200
    data = r.json()
    assert "positions" in data

def test_risk_status():
    r = client.get("/api/v1/risk/status")
    assert r.status_code == 200
    data = r.json()
    assert "circuit_breaker_active" in data

def test_ai_scores():
    r = client.get("/api/v1/ai/scores?symbol=BTC")
    assert r.status_code == 200
    data = r.json()
    assert "overall_score" in data

def test_ai_decisions():
    r = client.get("/api/v1/ai/decisions?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_performance_summary():
    r = client.get("/api/v1/performance/summary")
    assert r.status_code == 200
    data = r.json()
    assert "sharpe_ratio" in data

def test_execution_stats():
    r = client.get("/api/v1/execution/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_orders" in data

def test_route_not_found():
    r = client.get("/api/v1/market/nonexistent_endpoint_xyz")
    assert r.status_code == 404

def test_cors_headers():
    r = client.get("/health")
    assert r.status_code == 200
