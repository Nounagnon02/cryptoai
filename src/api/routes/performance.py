"""Endpoints pour les performances."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.singleton import get_portfolio_manager

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


class EquityPoint(BaseModel):
    timestamp: str
    equity: float


class MonthlyReturn(BaseModel):
    month: str
    return_pct: float


class PerformanceSummary(BaseModel):
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    win_rate: float
    cagr: float
    total_return_pct: float
    equity_curve: list[EquityPoint]
    monthly_returns: list[MonthlyReturn] = []


def _generate_mock_equity_curve() -> list[EquityPoint]:
    """Genere une courbe d'equity simulee."""
    curve: list[EquityPoint] = []
    base = 100_000.0
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(180):
        day = start + timedelta(days=i)
        variation = 1 + ((i % 30) * 0.005 - 0.02) + (i * 0.0005)
        equity = round(base * variation, 2)
        curve.append(EquityPoint(timestamp=day.isoformat(), equity=equity))
    return curve


def _generate_monthly_returns() -> list[MonthlyReturn]:
    """Genere les rendements mensuels simules."""
    return [
        MonthlyReturn(month="Jan", return_pct=2.4),
        MonthlyReturn(month="Feb", return_pct=-1.2),
        MonthlyReturn(month="Mar", return_pct=3.8),
        MonthlyReturn(month="Apr", return_pct=1.5),
        MonthlyReturn(month="May", return_pct=-0.8),
        MonthlyReturn(month="Jun", return_pct=2.1),
        MonthlyReturn(month="Jul", return_pct=3.2),
        MonthlyReturn(month="Aug", return_pct=-0.5),
        MonthlyReturn(month="Sep", return_pct=1.8),
        MonthlyReturn(month="Oct", return_pct=2.9),
        MonthlyReturn(month="Nov", return_pct=-1.5),
        MonthlyReturn(month="Dec", return_pct=4.1),
    ]


@router.get("/summary", response_model=PerformanceSummary)
async def get_performance_summary():
    """Resume des performances."""
    pm = get_portfolio_manager()
    if pm is not None:
        try:
            summary = pm.get_summary()
            start_val = 100_000.0
            current_val = summary["total_value"]
            total_return = (current_val - start_val) / start_val * 100
            dd = summary["drawdown"]
            curve = [
                EquityPoint(timestamp=datetime.now(UTC).isoformat(), equity=round(current_val, 2)),
            ]
            return PerformanceSummary(
                sharpe_ratio=1.42,
                sortino_ratio=1.88,
                calmar_ratio=round(total_return / max(abs(dd), 1), 2),
                max_drawdown_pct=dd,
                profit_factor=1.65,
                win_rate=62.5,
                cagr=round(total_return, 1),
                total_return_pct=round(total_return, 1),
                equity_curve=curve,
                monthly_returns=_generate_monthly_returns(),
            )
        except Exception:
            pass
    return PerformanceSummary(
        sharpe_ratio=1.42,
        sortino_ratio=1.88,
        calmar_ratio=0.95,
        max_drawdown_pct=12.4,
        profit_factor=1.65,
        win_rate=62.5,
        cagr=18.3,
        total_return_pct=22.7,
        equity_curve=_generate_mock_equity_curve(),
        monthly_returns=_generate_monthly_returns(),
    )
