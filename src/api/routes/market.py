"""Endpoints pour les données de marché."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from src.config import config
from src.utils.security.validator import default_validator

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


@router.get("/watchlist")
async def get_watchlist():
    """Retourne la watchlist actuelle."""
    return {"watchlist": config.watchlist, "count": len(config.watchlist)}
