"""
Routes for live trading control — emergency stop, status, and reconciliation.

⚠️ SECURITY: These endpoints control REAL MONEY trading.
All routes require FULL authentication (JWT token).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from src.utils.singleton import _instances

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/trading",
    tags=["trading"],
)


# ── Request/Response Models ───────────────────────────────────

class EmergencyStopRequest(BaseModel):
    """Request to trigger emergency stop."""
    level: str = Field(
        default="hard",
        description="Stop level: soft (no new orders), hard (close all), critical (liquidate)",
        pattern="^(soft|hard|critical)$",
    )
    reason: str = Field(
        default="Manual trigger via API",
        description="Reason for the emergency stop",
    )


class EmergencyStopResponse(BaseModel):
    """Emergency stop status after action."""
    success: bool
    message: str
    status: dict


class TradingStatusResponse(BaseModel):
    """Complete trading system status."""
    mode: str
    live_engine: dict | None
    paper_exchange: dict | None
    circuit_breaker: dict | None
    risk_manager: dict | None
    emergency_stop: dict


# ── Helpers ────────────────────────────────────────────────────

def _get_live_engine():
    """Get the live trading engine instance."""
    engine = _instances.get("live_trading_engine")
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Live trading engine not initialized. Switch to live mode.",
        )
    return engine


def _get_circuit_breaker():
    """Get the circuit breaker instance."""
    return _instances.get("circuit_breaker")


def _get_risk_manager():
    """Get the risk manager instance."""
    return _instances.get("risk_manager")


def _get_paper_exchange():
    """Get the paper exchange instance."""
    return _instances.get("paper_exchange")


# ── Routes ────────────────────────────────────────────────────

@router.post("/emergency-stop", response_model=EmergencyStopResponse)
async def trigger_emergency_stop(req: EmergencyStopRequest):
    """
    ⚠️ TRIGGER EMERGENCY STOP — Halts all trading immediately.

    - **soft**: No new orders, keeps existing positions
    - **hard**: No orders at all, closes all positions at market
    - **critical**: Immediate liquidation of everything, no confirmation

    This is IRREVERSIBLE without explicit admin reset via `/emergency-reset`.
    """
    engine = _get_live_engine()
    status = engine.trigger_emergency_stop(
        level=req.level,
        triggered_by="api",
        reason=req.reason,
    )

    logger.critical(
        "EMERGENCY STOP triggered via API: level=%s reason=%s",
        req.level, req.reason,
    )

    return EmergencyStopResponse(
        success=True,
        message=f"Emergency stop {req.level.upper()} triggered. All trading halted.",
        status=status,
    )


@router.post("/emergency-reset", response_model=EmergencyStopResponse)
async def reset_emergency_stop(
    admin_key: str = Query(..., description="Admin API key for reset"),
):
    """
    🔓 Reset emergency stop (ADMIN ONLY).

    Requires the admin API key. After reset, trading resumes on the next cycle.
    """
    from src.config import config

    # Validate admin key
    expected_key = config.admin_api_key or config.jwt_secret
    if not expected_key or admin_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin key",
        )

    engine = _get_live_engine()
    status = engine.reset_emergency_stop(reset_by="api_admin")

    logger.warning("EMERGENCY STOP RESET via API admin")

    return EmergencyStopResponse(
        success=True,
        message="Emergency stop reset. Trading will resume next cycle.",
        status=status,
    )


@router.get("/status", response_model=TradingStatusResponse)
async def get_trading_status():
    """
    Get complete trading system status — mode, engines, safety layers.
    """
    from src.config import config as app_config
    from src.utils.singleton import get_circuit_breaker as get_cb
    from src.utils.singleton import get_paper_exchange as get_pe
    from src.utils.singleton import get_risk_manager as get_rm

    mode = app_config.mode

    # Live engine status
    live_engine = _instances.get("live_trading_engine")
    live_status = live_engine.get_status() if live_engine else None

    # Paper exchange status
    paper = get_pe()
    paper_status = None
    if paper:
        state = paper.get_state()
        paper_status = {
            "initial_capital": state.initial_capital,
            "current_capital": round(state.current_capital, 2),
            "total_pnl": round(state.total_pnl, 2),
            "total_pnl_pct": round(state.total_pnl_pct, 2),
            "positions_open": state.positions_open,
            "trades_total": state.trades_total,
            "win_rate": round(state.win_rate, 2),
        }

    # Circuit breaker status
    cb = get_cb()
    cb_status = cb.get_status() if cb else None

    # Risk manager status
    rm = get_rm()
    rm_status = None
    if rm:
        rm_status = {
            "daily_pnl": round(rm.daily_pnl, 2) if hasattr(rm, "daily_pnl") else 0.0,
            "daily_loss_limit": rm.limits.daily_loss_limit if hasattr(rm, "limits") else 0.0,
            "positions_count": (
                len(rm._current_positions) if hasattr(rm, "_current_positions") else 0
            ),
        }

    # Emergency stop
    emergency = (
        live_engine.emergency_stop.status()
        if live_engine
        else {"is_active": False, "level": "none"}
    )

    return TradingStatusResponse(
        mode=mode,
        live_engine=live_status,
        paper_exchange=paper_status,
        circuit_breaker=cb_status,
        risk_manager=rm_status,
        emergency_stop=emergency,
    )


@router.get("/audit-log")
async def get_audit_log(
    limit: int = Query(default=50, ge=1, le=500, description="Number of entries to return"),
    symbol: str | None = Query(default=None, description="Filter by symbol"),
):
    """
    Get the live trading audit log (JSONL).
    """
    import json
    from pathlib import Path

    log_path = Path("data/live_trades.jsonl")
    if not log_path.exists():
        return {"entries": [], "total": 0}

    entries = []
    with open(log_path) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    if symbol and entry.get("symbol") != symbol:
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

    # Reverse — most recent first
    entries.reverse()
    paginated = entries[:limit]

    return {
        "entries": paginated,
        "total": len(entries),
        "returned": len(paginated),
    }
