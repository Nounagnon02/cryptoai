"""Endpoints pour le market screener (top gagnants/perdants)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.utils.singleton import get_all_live_market_data

router = APIRouter(prefix="/api/v1/market/screener", tags=["screener"])


class ScreenerItem(BaseModel):
    """Un élément du screener."""

    symbol: str
    last_price: float
    change_24h_pct: float
    volume_24h: float
    bid: float
    ask: float


class ScreenerResponse(BaseModel):
    """Réponse du market screener."""

    top_gainers: list[ScreenerItem]
    top_losers: list[ScreenerItem]
    timestamp: str


def _build_screener_item(symbol: str, data: dict) -> ScreenerItem:
    ticker = data.get("ticker", {})
    return ScreenerItem(
        symbol=symbol,
        last_price=round(float(ticker.get("last", 0)), 2),
        change_24h_pct=round(float(ticker.get("change_24h", 0)), 2),
        volume_24h=round(float(ticker.get("volume_24h", 0)), 2),
        bid=round(float(ticker.get("bid", 0)), 2),
        ask=round(float(ticker.get("ask", 0)), 2),
    )


@router.get("", response_model=ScreenerResponse)
async def get_screener(
    min_volume: float = Query(default=0, ge=0, description="Volume 24h minimum"),
    sort_by: str = Query(default="change_24h", description="change_24h | volume"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Retourne les top gagnants et perdants du marché."""
    all_data = get_all_live_market_data()

    if not all_data:
        return ScreenerResponse(
            top_gainers=[],
            top_losers=[],
            timestamp=datetime.now(UTC).isoformat(),
        )

    items: list[ScreenerItem] = []
    for symbol, data in all_data.items():
        if data and data.get("ticker"):
            ticker = data["ticker"]
            if ticker.get("volume_24h", 0) >= min_volume:
                items.append(_build_screener_item(symbol, data))

    if sort_by == "volume":
        items.sort(key=lambda x: x.volume_24h, reverse=True)
        return ScreenerResponse(
            top_gainers=items[:limit],
            top_losers=items[:limit],
            timestamp=datetime.now(UTC).isoformat(),
        )

    # Default: sort by change_24h
    sorted_items = sorted(items, key=lambda x: x.change_24h_pct, reverse=True)
    top_gainers = sorted_items[:limit]
    top_losers = sorted(
        [i for i in sorted_items if i.change_24h_pct < 0],
        key=lambda x: x.change_24h_pct,
    )[:limit]

    return ScreenerResponse(
        top_gainers=top_gainers,
        top_losers=top_losers,
        timestamp=datetime.now(UTC).isoformat(),
    )
