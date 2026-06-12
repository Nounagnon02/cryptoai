"""Tests des endpoints health."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)

def test_health_root():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"

def test_health_ready():
    r = client.get("/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"

def test_health_metrics():
    r = client.get("/health/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "uptime_seconds" in data
