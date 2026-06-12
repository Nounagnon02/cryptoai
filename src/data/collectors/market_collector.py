"""
Collecteur de données temps réel.

Orchestre la collecte des données de marché depuis les exchanges
et les stocke dans TimescaleDB/Redis.
"""

from __future__ import annotations

import asyncio

from src.config import config
from src.data.market.provider import CCXTProvider
from src.data.market.schema import OHLCV, OrderBook, Ticker
from src.data.market.websocket import WebSocketManager
from src.utils.database import db
from src.utils.logging import LoggerMixin


class MarketCollector(LoggerMixin):
    """
    Collecteur de données marché temps réel.

    Combine WebSocket (temps réel) et REST API (historique, snapshot).
    Stocke dans Redis (temps réel) et TimescaleDB (persistant).
    """

    def __init__(self) -> None:
        self._ws_manager = WebSocketManager()
        self._providers: dict[str, CCXTProvider] = {}
        self._active_symbols: set[str] = set()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Buffer Redis pour les données temps réel
        self.REDIS_OHLCV_KEY = "market:ohlcv:{symbol}:{timeframe}"
        self.REDIS_TICKER_KEY = "market:ticker:{symbol}"
        self.REDIS_ORDERBOOK_KEY = "market:orderbook:{symbol}"

    async def start(self, symbols: list[str] | None = None) -> None:
        """Démarre la collecte pour les symboles donnés."""
        if symbols is None:
            symbols = config.watchlist

        self._active_symbols = set(symbols)
        self._running = True

        # 1. Démarrer les connexions WebSocket pour les données temps réel
        await self._ws_manager.start(symbols)

        # 2. Enregistrer les handlers de stockage
        self._ws_manager.on_ohlcv(self._store_ohlcv)
        self._ws_manager.on_ticker(self._store_ticker)
        self._ws_manager.on_orderbook(self._store_orderbook)

        # 3. Démarrer les collecteurs périodiques REST
        self._tasks.extend([
            asyncio.create_task(self._periodic_collect(symbols)),
            asyncio.create_task(self._periodic_health_check()),
        ])

        self.logger.info(
            "MarketCollector démarré",
            extra={"symbols": symbols},
        )

    async def stop(self) -> None:
        """Arrête proprement la collecte."""
        self._running = False

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        await self._ws_manager.stop()

        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()

        self.logger.info("MarketCollector arrêté")

    async def get_provider(self, exchange: str = "binance") -> CCXTProvider:
        """Retourne un provider REST pour l'exchange (création paresseuse)."""
        if exchange not in self._providers:
            self._providers[exchange] = CCXTProvider(
                exchange_name=exchange,
                testnet=config.mode != "live",
            )
        return self._providers[exchange]

    # ─── Collecteurs périodiques REST ────────────────────

    async def _periodic_collect(self, symbols: list[str]) -> None:
        """Collecte périodique des données via REST API."""
        while self._running:
            try:
                provider = await self.get_provider()

                for symbol in symbols:
                    try:
                        # Collecter OHLCV pour tous les timeframes
                        for tf in config.timeframes:
                            df = await provider.fetch_ohlcv(symbol, timeframe=tf, limit=1)
                            if not df.empty:
                                await self._store_ohlcv_batch(symbol, tf, df)

                        # Collecter le carnet d'ordres
                        ob = await provider.fetch_order_book(symbol, limit=20)
                        await self._store_orderbook(ob)

                    except Exception as e:
                        self.logger.error(
                            "Erreur collecte",
                            extra={"symbol": symbol, "error": str(e)},
                        )

                # Intervalle de collecte
                await asyncio.sleep(60)

            except Exception as e:
                self.logger.error("Erreur collecte périodique", extra={"error": str(e)})
                await asyncio.sleep(30)

    async def _periodic_health_check(self) -> None:
        """Vérification périodique de la santé des connexions."""
        while self._running:
            await asyncio.sleep(300)  # 5 minutes

            for exchange, provider in self._providers.items():
                healthy = await provider.health_check()
                if not healthy:
                    self.logger.warning(
                        "Provider non disponible",
                        extra={"exchange": exchange},
                    )

    # ─── Stockage des données ───────────────────────────

    async def _store_ohlcv(self, ohlcv: OHLCV) -> None:
        """Stocke une bougie OHLCV en temps réel (Redis + TimescaleDB)."""
        key = self.REDIS_OHLCV_KEY.format(
            symbol=ohlcv.symbol.replace("/", "_").lower(),
            timeframe=ohlcv.timeframe,
        )
        try:
            await db.redis.hset(key, mapping={
                "timestamp": ohlcv.timestamp.isoformat(),
                "open": ohlcv.open,
                "high": ohlcv.high,
                "low": ohlcv.low,
                "close": ohlcv.close,
                "volume": ohlcv.volume,
                "trades": ohlcv.trades or 0,
            })
            await db.redis.expire(key, 3600)  # TTL 1h
        except Exception as e:
            self.logger.error("Erreur stockage OHLCV", extra={"error": str(e)})

    async def _store_ohlcv_batch(self, symbol: str, timeframe: str, df) -> None:
        """Stocke un lot de données OHLCV."""
        try:
            # Implémentation TimescaleDB via execute_raw
            for idx, row in df.iterrows():
                query = """
                    INSERT INTO ohlcv (symbol, timeframe, timestamp, open, high, low, close, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
                """
                await db.execute_raw(
                    query,
                    symbol,
                    timeframe,
                    idx.to_pydatetime(),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                )
        except Exception as e:
            self.logger.warning("Erreur stockage batch", extra={"error": str(e)})

    async def _store_ticker(self, ticker: Ticker) -> None:
        """Stocke un ticker temps réel."""
        key = self.REDIS_TICKER_KEY.format(
            symbol=ticker.symbol.replace("/", "_").lower(),
        )
        try:
            await db.redis.hset(key, mapping={
                "last": ticker.last,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "volume_24h": ticker.volume_24h,
                "change_24h": ticker.change_24h,
                "timestamp": ticker.timestamp.isoformat(),
            })
            await db.redis.expire(key, 300)  # TTL 5 min
        except Exception as e:
            self.logger.error("Erreur stockage ticker", extra={"error": str(e)})

    async def _store_orderbook(self, ob: OrderBook) -> None:
        """Stocke un snapshot du carnet d'ordres."""
        key = self.REDIS_ORDERBOOK_KEY.format(
            symbol=ob.symbol.replace("/", "_").lower(),
        )
        try:
            snapshot = {
                "timestamp": ob.timestamp.isoformat(),
                "spread": ob.spread,
                "imbalance": ob.imbalance,
                "bid_volume": ob.total_bid_volume,
                "ask_volume": ob.total_ask_volume,
                "bid_price": ob.bids[0].price if ob.bids else 0,
                "ask_price": ob.asks[0].price if ob.asks else 0,
            }
            await db.redis.hset(key, mapping=snapshot)
            await db.redis.expire(key, 120)  # TTL 2 min
        except Exception as e:
            self.logger.error("Erreur stockage orderbook", extra={"error": str(e)})
