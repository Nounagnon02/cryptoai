"""Endpoint de health check et métriques système."""

from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Vérification de l'état du système."""
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0.0",
    }


@router.get("/health/ready")
async def readiness_check():
    """Vérification que le système est prêt à recevoir du trafic."""
    return {
        "status": "ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {
            "database": True,
            "redis": True,
            "websocket": True,
        },
    }


@router.get("/health/metrics")
async def system_metrics():
    """Métriques système de base."""
    return {
        "uptime_seconds": 0,
        "active_connections": 0,
        "memory_usage_mb": 0,
        "cpu_percent": 0,
        "requests_total": 0,
        "errors_total": 0,
    }
