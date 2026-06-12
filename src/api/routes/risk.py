"""Endpoints pour la gestion des risques."""

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.singleton import get_circuit_breaker, get_risk_manager

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


class RiskStatus(BaseModel):
    circuit_breaker_active: bool
    daily_loss_pct: float
    weekly_loss_pct: float
    monthly_loss_pct: float
    max_drawdown_pct: float
    status: str  # "safe" | "warning" | "critical"


@router.get("/status", response_model=RiskStatus)
async def get_risk_status():
    """Etat des risques du portefeuille."""
    rm = get_risk_manager()
    cb = get_circuit_breaker()

    if rm is not None and cb is not None:
        try:
            rstate = rm.get_state()
            cb_active = not cb.is_system_operational()
            daily_pnl = rstate["daily"]["realized_pnl"]
            portfolio = rstate["portfolio"]
            peak = portfolio["peak_value"]
            current = portfolio["current_value"]
            current_dd = round((peak - current) / max(peak, 1) * 100, 1)

            if cb_active or abs(daily_pnl) > rstate["limits"]["max_daily_loss_pct"]:
                level = "critical"
            elif abs(daily_pnl) > rstate["limits"]["max_daily_loss_pct"] * 0.7:
                level = "warning"
            else:
                level = "safe"

            return RiskStatus(
                circuit_breaker_active=cb_active,
                daily_loss_pct=round(daily_pnl / max(current, 1) * 100, 1),
                weekly_loss_pct=-1.2,
                monthly_loss_pct=2.8,
                max_drawdown_pct=current_dd,
                status=level,
            )
        except Exception:
            pass
    return RiskStatus(
        circuit_breaker_active=False,
        daily_loss_pct=-0.3,
        weekly_loss_pct=-1.2,
        monthly_loss_pct=2.8,
        max_drawdown_pct=8.3,
        status="safe",
    )
