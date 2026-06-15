"""Endpoints pour les données de marché."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from src.config import config
from src.utils.security.validator import default_validator
from src.utils.singleton import get_all_live_market_data, get_live_market_data

router = APIRouter(prefix="/api/v1/market", tags=["market"])


async def validate_symbol_param(symbol: str = Path(..., min_length=2, max_length=20, pattern=r"^[A-Z0-9-/_]{2,20}")):
    """Valide le symbole via InputValidator."""
    result = default_validator.validate_symbol(symbol)
    if not result.is_valid:
        error_msg = "; ".join(result.errors)
        raise HTTPException(status_code=422, detail=f"Invalid symbol: {error_msg}")
    return symbol


@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str = Depends(validate_symbol_param)):
    """Récupère le ticker temps réel pour un symbole."""
    try:
        from src.utils.database import db
        key = f"market:ticker:{symbol.lower().replace('/', '_')}"
        data = await db.redis.hgetall(key)
        if not data:
            raise HTTPException(status_code=404, detail="Ticker non disponible")
        return {"symbol": symbol, "data": data, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/orderbook/{symbol}")
async def get_orderbook(symbol: str = Depends(validate_symbol_param)):
    """Récupère le carnet d'ordres pour un symbole."""
    try:
        from src.utils.database import db
        key = f"market:orderbook:{symbol.lower().replace('/', '_')}"
        data = await db.redis.hgetall(key)
        if not data:
            raise HTTPException(status_code=404, detail="Order book non disponible")
        return {"symbol": symbol, "data": data, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str = Depends(validate_symbol_param),
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Récupère les données OHLCV historiques."""
    try:
        from src.utils.database import db
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC
            LIMIT $3
        """
        rows = await db.execute_raw(query, symbol, timeframe, limit)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": [
                {
                    "timestamp": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
                for row in rows
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/live/{symbol}")
async def get_live_data(symbol: str = Depends(validate_symbol_param)):
    """Récupère les données en DIRECT depuis Binance (aucun cache)."""
    try:
        from src.data.market.provider import CCXTProvider
        provider = CCXTProvider(exchange_name="binance", testnet=False)

        ohlcv_df = await provider.fetch_ohlcv(symbol, timeframe="1h", limit=24)
        ticker = await provider.fetch_ticker(symbol)
        ob = await provider.fetch_order_book(symbol, limit=10)
        await provider.close()

        ohlcv_data = []
        for _, row in ohlcv_df.iterrows():
            ohlcv_data.append({
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": round(float(row["volume"]), 2),
            })

        bids = [{"price": round(float(b.price), 2), "amount": round(float(b.value_usd / b.price), 4)}
                for b in ob.bids[:5]]
        asks = [{"price": round(float(a.price), 2), "amount": round(float(a.value_usd / a.price), 4)}
                for a in ob.asks[:5]]

        return {
            "symbol": symbol,
            "source": "binance",
            "timestamp": datetime.now(UTC).isoformat(),
            "ticker": {
                "last": round(ticker.last, 2),
                "bid": round(ticker.bid, 2),
                "ask": round(ticker.ask, 2),
                "volume_24h": round(ticker.volume_24h, 2),
                "change_24h": round(ticker.change_24h, 2),
            },
            "orderbook": {"bids": bids[:3], "asks": asks[:3], "spread": round(ob.spread, 2)},
            "ohlcv": ohlcv_data[-1] if ohlcv_data else None,
            "trend": "bullish" if ohlcv_data and ohlcv_data[-1]["close"] > ohlcv_data[0]["close"] else "bearish",
            "range_24h": {
                "high": max(d["high"] for d in ohlcv_data) if ohlcv_data else 0,
                "low": min(d["low"] for d in ohlcv_data) if ohlcv_data else 0,
            } if ohlcv_data else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Binance: {str(e)}") from e


@router.get("/overview")
async def get_market_overview():
    """Vue d'ensemble du marché : tickers + analyses live pour tous les symboles watchlist."""
    live_data = get_all_live_market_data()
    overview = []
    for symbol in config.watchlist:
        data = live_data.get(symbol) or get_live_market_data(symbol)
        if data and "ticker" in data:
            entry = {
                "symbol": symbol,
                "ticker": data["ticker"],
                "last_ohlcv": data.get("last_ohlcv"),
                "updated_at": data.get("_updated_at", ""),
            }
        else:
            entry = {
                "symbol": symbol,
                "ticker": None,
                "last_ohlcv": None,
                "updated_at": None,
            }
        overview.append(entry)
    return {"symbols": overview, "count": len(overview), "timestamp": datetime.now(UTC).isoformat()}


@router.get("/watchlist")
async def get_watchlist():
    """Retourne la watchlist actuelle."""
    return {"watchlist": config.watchlist, "count": len(config.watchlist)}
