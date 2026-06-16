"""Endpoints pour lancer et consulter des backtests."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/backtest", tags=["backtesting"])

# Stockage en mémoire des résultats de backtest
_backtest_results: dict[str, dict[str, Any]] = {}


class BacktestRunRequest(BaseModel):
    strategy: str = Field(default="trend_following", description="Strategy name")
    symbol: str = Field(default="BTC/USDT", min_length=1, max_length=20)
    timeframe: str = Field(default="1h", description="1m|5m|15m|1h|4h|1d")
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    initial_capital: float = Field(default=10_000.0, ge=100, le=1_000_000)


class BacktestStatusResponse(BaseModel):
    run_id: str
    status: str  # running | completed | failed
    progress_pct: float = 0.0
    started_at: str
    completed_at: str | None = None


class TradeLogEntry(BaseModel):
    timestamp: str
    symbol: str
    side: str
    quantity: float
    price: float
    pnl: float
    pnl_pct: float


class BacktestResultResponse(BaseModel):
    run_id: str
    status: str
    config: BacktestRunRequest
    metrics: dict[str, float] | None = None
    equity_curve: list[dict[str, Any]] = []
    trades: list[TradeLogEntry] = []
    benchmark_return_pct: float = 0.0
    started_at: str
    completed_at: str | None = None


# ─── Endpoints ──────────────────────────────────────────────────


@router.post("/run", response_model=BacktestStatusResponse)
async def run_backtest(req: BacktestRunRequest):
    """Lance un backtest avec les paramètres spécifiés."""
    run_id = f"bt_{uuid.uuid4().hex[:12]}"
    started = datetime.now(UTC).isoformat()

    _backtest_results[run_id] = {
        "status": "running",
        "progress_pct": 0.0,
        "config": req.model_dump(),
        "metrics": None,
        "equity_curve": [],
        "trades": [],
        "started_at": started,
        "completed_at": None,
    }

    logger.info("Backtest %s started: %s %s %s", run_id, req.strategy, req.symbol, req.timeframe)

    # Lancer le backtest de manière asynchrone
    import asyncio
    asyncio.create_task(_run_backtest_async(run_id, req))

    return BacktestStatusResponse(
        run_id=run_id,
        status="running",
        progress_pct=0.0,
        started_at=started,
    )


@router.get("/result/{run_id}", response_model=BacktestResultResponse)
async def get_backtest_result(run_id: str):
    """Récupère le résultat d'un backtest par son ID."""
    result = _backtest_results.get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Backtest {run_id} not found")

    return BacktestResultResponse(
        run_id=run_id,
        status=result["status"],
        config=BacktestRunRequest(**result["config"]),
        metrics=result.get("metrics"),
        equity_curve=result.get("equity_curve", []),
        trades=result.get("trades", []),
        benchmark_return_pct=result.get("benchmark_return_pct", 0.0),
        started_at=result["started_at"],
        completed_at=result.get("completed_at"),
    )


@router.get("/results", response_model=list[BacktestStatusResponse])
async def list_backtest_results(limit: int = Query(default=10, ge=1, le=50)):
    """Liste les derniers backtests exécutés."""
    items = list(_backtest_results.values())
    items.sort(key=lambda x: x["started_at"], reverse=True)
    return [
        BacktestStatusResponse(
            run_id=k,
            status=v["status"],
            progress_pct=v.get("progress_pct", 0.0),
            started_at=v["started_at"],
            completed_at=v.get("completed_at"),
        )
        for k, v in list(_backtest_results.items())[:limit]
    ]


# ─── Background Runner ──────────────────────────────────────────


async def _run_backtest_async(run_id: str, req: BacktestRunRequest) -> None:
    """Exécute un backtest en arrière-plan."""
    result = _backtest_results.get(run_id)
    if not result:
        return

    try:
        from datetime import timedelta

        # 1. Récupérer les données historiques
        from src.data.market.provider import CCXTProvider

        provider = CCXTProvider(exchange_name="binance", testnet=False)
        try:
            end = datetime.now(UTC) if not req.end_date else datetime.fromisoformat(req.end_date).replace(tzinfo=UTC)
            start = end - timedelta(days=90) if not req.start_date else datetime.fromisoformat(req.start_date).replace(tzinfo=UTC)

            since_ms = int(start.timestamp() * 1000)

            df = await provider.fetch_ohlcv(req.symbol, req.timeframe, since=since_ms, limit=1000)

            if df is None or df.empty:
                result["status"] = "failed"
                result["completed_at"] = datetime.now(UTC).isoformat()
                return

            # Filtrer par date
            if req.start_date:
                df = df[df.index >= req.start_date]
            if req.end_date:
                df = df[df.index <= req.end_date]

            result["progress_pct"] = 20.0

        finally:
            await provider.close()

        # 2. Initialiser le portfolio simulé
        capital = req.initial_capital
        position = 0.0
        entry_price = 0.0
        trades_log: list[dict] = []
        equity_curve: list[dict] = []
        benchmark_entry = float(df["close"].iloc[0])
        benchmark_exit = float(df["close"].iloc[-1])
        benchmark_return_pct = ((benchmark_exit - benchmark_entry) / benchmark_entry) * 100.0

        # 3. Stratégie: trend_following (EMA crossover)
        if req.strategy in ("trend_following",):
            ema_fast = df["close"].ewm(span=12).mean()
            ema_slow = df["close"].ewm(span=26).mean()

            in_position = False
            total_bars = len(df)
            bar_count = 0

            for i in range(26, total_bars):
                bar_count += 1
                result["progress_pct"] = 20.0 + (bar_count / total_bars) * 70.0

                price = float(df["close"].iloc[i])
                prev_fast = float(ema_fast.iloc[i - 1])
                prev_slow = float(ema_slow.iloc[i - 1])
                cur_fast = float(ema_fast.iloc[i])
                cur_slow = float(ema_slow.iloc[i])

                # Golden cross → Buy
                if not in_position and prev_fast <= prev_slow and cur_fast > cur_slow:
                    quantity = (capital * 0.95) / price
                    fee = (quantity * price) * 0.001
                    capital -= quantity * price + fee
                    position = quantity
                    entry_price = price
                    in_position = True
                    trades_log.append({
                        "timestamp": str(df.index[i]),
                        "symbol": req.symbol,
                        "side": "buy",
                        "quantity": round(quantity, 6),
                        "price": round(price, 2),
                        "pnl": 0.0,
                        "pnl_pct": 0.0,
                    })

                # Death cross → Sell
                elif in_position and prev_fast >= prev_slow and cur_fast < cur_slow:
                    value = position * price
                    fee = value * 0.001
                    pnl = (price - entry_price) * position - fee * 2
                    pnl_pct = ((price - entry_price) / entry_price) * 100
                    capital += value - fee
                    trades_log.append({
                        "timestamp": str(df.index[i]),
                        "symbol": req.symbol,
                        "side": "sell",
                        "quantity": round(position, 6),
                        "price": round(price, 2),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                    })
                    position = 0.0
                    entry_price = 0.0
                    in_position = False

                # Equity curve
                unrealized = position * price if in_position else 0.0
                equity_curve.append({
                    "timestamp": str(df.index[i]),
                    "equity": round(capital + unrealized, 2),
                })

        # 4. Clore la position s'il y en a une ouverte
        if in_position and position > 0:
            final_price = float(df["close"].iloc[-1])
            value = position * final_price
            pnl = (final_price - entry_price) * position
            capital += value
            trades_log.append({
                "timestamp": str(df.index[-1]),
                "symbol": req.symbol,
                "side": "sell",
                "quantity": round(position, 6),
                "price": round(final_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(((final_price - entry_price) / entry_price) * 100, 2),
            })
            position = 0.0

        # 5. Calculer les métriques
        total_return_pct = ((capital - req.initial_capital) / req.initial_capital) * 100
        winning_trades = [t for t in trades_log if t["pnl"] > 0 and t["side"] == "sell"]
        losing_trades = [t for t in trades_log if t["pnl"] <= 0 and t["side"] == "sell"]
        closed_trades = winning_trades + losing_trades
        win_rate = (len(winning_trades) / max(len(closed_trades), 1)) * 100
        total_pnl = sum(t["pnl"] for t in trades_log)
        profit_factor = (
            abs(sum(t["pnl"] for t in winning_trades) / max(abs(sum(t["pnl"] for t in losing_trades)), 0.01))
            if losing_trades else 999.0
        )

        # Max drawdown
        peak = req.initial_capital
        max_dd = 0.0
        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        metrics = {
            "total_return_pct": round(total_return_pct, 2),
            "total_pnl_usd": round(total_pnl, 2),
            "sharpe_ratio": round(_calc_sharpe(equity_curve, req.initial_capital), 2),
            "max_drawdown_pct": round(max_dd, 2),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "total_trades": len(closed_trades),
            "cagr": round(total_return_pct, 2),  # Simplified for short backtests
        }

        # 6. Finaliser
        result["status"] = "completed"
        result["progress_pct"] = 100.0
        result["metrics"] = metrics
        result["equity_curve"] = equity_curve
        result["trades"] = trades_log
        result["benchmark_return_pct"] = round(benchmark_return_pct, 2)
        result["completed_at"] = datetime.now(UTC).isoformat()

        logger.info("Backtest %s completed: return=%s%%, trades=%d", run_id, total_return_pct, len(closed_trades))

    except Exception as exc:
        logger.error("Backtest %s failed: %s", run_id, exc)
        result["status"] = "failed"
        result["completed_at"] = datetime.now(UTC).isoformat()


def _calc_sharpe(equity_curve: list[dict], initial_capital: float) -> float:
    """Calcule le Sharpe ratio simplifié."""
    if len(equity_curve) < 2:
        return 0.0
    returns = []
    prev = equity_curve[0]["equity"]
    for point in equity_curve[1:]:
        curr = point["equity"]
        returns.append((curr - prev) / prev * 100)
        prev = curr
    if not returns:
        return 0.0
    avg = sum(returns) / len(returns)
    std = (sum((r - avg) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 1.0
    return (avg / max(std, 0.01)) * (252**0.5)  # Annualized
