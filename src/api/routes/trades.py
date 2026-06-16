"""Endpoints pour l'historique des trades."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.utils.logging import get_logger
from src.utils.singleton import get_paper_exchange

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


class TradeEntry(BaseModel):
    """Entrée de trade pour l'API."""

    trade_id: str
    symbol: str
    side: str  # buy | sell
    quantity: float
    price: float
    value_usd: float
    fee: float
    pnl: float
    pnl_pct: float
    timestamp: str
    strategy: str
    status: str  # open | closed


class TradeHistoryResponse(BaseModel):
    """Réponse pour l'historique des trades."""

    trades: list[TradeEntry]
    total: int


@router.get("/history", response_model=TradeHistoryResponse)
async def get_trade_history(
    limit: int = Query(default=50, ge=1, le=200),
    symbol: str | None = Query(default=None),
):
    """Récupère l'historique des trades (ouverts et fermés)."""
    pe = get_paper_exchange()
    if pe is None:
        return TradeHistoryResponse(trades=[], total=0)

    # Récupérer les trades via la méthode dédiée
    all_trades = pe.get_trade_history(limit=200)

    # Filtrer par symbole si nécessaire
    if symbol:
        all_trades = [t for t in all_trades if t["symbol"] == symbol]

    # Limiter
    all_trades = all_trades[:limit]

    entries = [
        TradeEntry(
            trade_id=t["trade_id"],
            symbol=t["symbol"],
            side=t["side"],
            quantity=round(t["quantity"], 6),
            price=round(t["price"], 2),
            value_usd=round(t["value_usd"], 2),
            fee=round(t["fee"], 4),
            pnl=round(t["pnl"], 2),
            pnl_pct=round(t["pnl_pct"], 2),
            timestamp=t.get("timestamp_formatted", ""),
            strategy=t.get("strategy", "default"),
            status=t["status"],
        )
        for t in all_trades
    ]

    return TradeHistoryResponse(trades=entries, total=len(entries))


@router.get("/export")
async def export_trades(
    symbol: str | None = Query(default=None),
    fmt: str = Query(default="csv", alias="format"),
):
    """Exporte l'historique des trades au format CSV."""
    pe = get_paper_exchange()
    if pe is None:
        return StreamingResponse(
            iter(["trade_id,symbol,side,quantity,price,value_usd,fee,pnl,pnl_pct,timestamp,strategy,status\n"]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=trades.csv"},
        )

    all_trades = pe.get_trade_history(limit=1000)
    if symbol:
        all_trades = [t for t in all_trades if t["symbol"] == symbol]

    def generate_csv():
        yield "trade_id,symbol,side,quantity,price,value_usd,fee,pnl,pnl_pct,timestamp,strategy,status\n"
        for t in all_trades:
            yield (
                f"{t['trade_id']},{t['symbol']},{t['side']},"
                f"{t['quantity']},{t['price']},{t['value_usd']},"
                f"{t['fee']},{t['pnl']},{t['pnl_pct']},"
                f"{t.get('timestamp_formatted', '')},{t.get('strategy', 'default')},{t['status']}\n"
            )

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=trades.csv",
        },
    )
