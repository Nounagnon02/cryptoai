"""
Gestionnaire de connexions WebSocket.

Maintient des connexions persistantes aux streams temps réel
des exchanges. Gère la reconnexion automatique et le rate limiting.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import aiohttp

from src.data.market.schema import OHLCV, OrderBook, Ticker, Trade
from src.utils.exceptions import WebSocketError
from src.utils.logging import LoggerMixin


class WebSocketConnection(LoggerMixin):
    """Connexion WebSocket individuelle à un stream exchange."""

    def __init__(
        self,
        url: str,
        subscriptions: list[dict[str, Any]],
        on_message: Callable[[dict[str, Any]], None],
        reconnect_delay: int = 5,
        max_retries: int = 10,
    ) -> None:
        self.url = url
        self.subscriptions = subscriptions
        self.on_message = on_message
        self.reconnect_delay = reconnect_delay
        self.max_retries = max_retries

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._retry_count = 0

    async def connect(self) -> None:
        """Établit la connexion WebSocket et s'abonne aux streams."""
        self._running = True
        self._session = aiohttp.ClientSession()

        while self._running and self._retry_count < self.max_retries:
            try:
                async with self._session.ws_connect(
                    self.url,
                    heartbeat=30,
                    receive_timeout=60,
                ) as ws:
                    self._ws = ws
                    self._retry_count = 0
                    self.logger.info(
                        "WebSocket connecté",
                        extra={"url": self.url},
                    )

                    # S'abonner aux streams
                    for sub in self.subscriptions:
                        await ws.send_json(sub)

                    # Boucle de réception
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            self.on_message(data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            raise WebSocketError(
                                f"Erreur WebSocket: {ws.exception()}",
                                endpoint=self.url,
                            )
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            break

            except (TimeoutError, aiohttp.ClientError) as e:
                self._retry_count += 1
                wait = min(self.reconnect_delay * (2 ** (self._retry_count - 1)), 60)
                self.logger.warning(
                    "WebSocket déconnecté, reconnexion",
                    extra={"retry": self._retry_count, "wait_seconds": wait, "error": str(e)},
                )
                await asyncio.sleep(wait)

    async def disconnect(self) -> None:
        """Ferme proprement la connexion WebSocket."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
        self.logger.info("WebSocket déconnecté", extra={"url": self.url})


class WebSocketManager(LoggerMixin):
    """
    Gestionnaire central de connexions WebSocket.

    Maintient les connexions persistantes aux exchanges,
    distribue les messages aux handlers enregistrés.
    """

    # Endpoints WebSocket publics des principaux exchanges
    ENDPOINTS = {
        "binance": "wss://stream.binance.com:9443/ws",
        "bybit": "wss://stream.bybit.com/v5/public/spot",
        "okx": "wss://ws.okx.com:8443/ws/v5/public",
    }

    def __init__(self) -> None:
        self._connections: list[WebSocketConnection] = []
        self._tasks: list[asyncio.Task] = []
        self._handlers: dict[str, list[Callable]] = {
            "trade": [],
            "ticker": [],
            "orderbook": [],
            "ohlcv": [],
        }

    # ─── Gestion des handlers ────────────────────────────

    def on_trade(self, callback: Callable[[Trade], None]) -> None:
        """Enregistre un handler pour les trades temps réel."""
        self._handlers["trade"].append(callback)

    def on_ticker(self, callback: Callable[[Ticker], None]) -> None:
        """Enregistre un handler pour les tickers temps réel."""
        self._handlers["ticker"].append(callback)

    def on_orderbook(self, callback: Callable[[OrderBook], None]) -> None:
        """Enregistre un handler pour les mises à jour du carnet d'ordres."""
        self._handlers["orderbook"].append(callback)

    def on_ohlcv(self, callback: Callable[[OHLCV], None]) -> None:
        """Enregistre un handler pour les bougies OHLCV temps réel."""
        self._handlers["ohlcv"].append(callback)

    # ─── Connexion aux streams ──────────────────────────

    async def connect_binance(
        self,
        symbols: list[str],
        channels: list[str] | None = None,
    ) -> None:
        """Connecte aux streams Binance pour les symboles donnés."""
        if channels is None:
            channels = ["trade", "ticker", "depth20", "kline_1m"]

        params = []
        for symbol in symbols:
            s = symbol.lower().replace("/", "")
            for ch in channels:
                if ch.startswith("kline_"):
                    params.append(f"{s}@kline_{ch.split('_')[1]}")
                elif ch == "depth20":
                    params.append(f"{s}@depth20")
                else:
                    params.append(f"{s}@{ch}")

        url = self.ENDPOINTS["binance"]
        sub = {
            "method": "SUBSCRIBE",
            "params": params,
            "id": 1,
        }

        conn = WebSocketConnection(
            url=url,
            subscriptions=[sub],
            on_message=self._handle_binance_message,
        )
        self._connections.append(conn)

        task = asyncio.create_task(conn.connect())
        self._tasks.append(task)
        self.logger.info(
            "Stream Binance démarré",
            extra={"symbols": symbols, "channels": channels},
        )

    def _handle_binance_message(self, data: dict[str, Any]) -> None:
        """Route les messages Binance vers les handlers appropriés."""
        event_type = data.get("e", "")

        if event_type == "trade":
            trade = Trade(
                id=str(data.get("t", "")),
                symbol=data.get("s", "").replace("/", "").upper(),
                price=float(data.get("p", 0)),
                amount=float(data.get("q", 0)),
                cost=float(data.get("p", 0)) * float(data.get("q", 0)),
                side="buy" if data.get("m") else "sell",
                timestamp=datetime.fromtimestamp(
                    data.get("T", 0) / 1000,
                    tz=UTC,
                ),
                exchange="binance",
            )
            for handler in self._handlers["trade"]:
                try:
                    handler(trade)
                except Exception as e:
                    self.logger.error("Handler trade error", extra={"error": str(e)})

        elif event_type == "24hrTicker":
            ticker = Ticker(
                symbol=data.get("s", ""),
                bid=float(data.get("b", 0)),
                ask=float(data.get("a", 0)),
                last=float(data.get("c", 0)),
                volume_24h=float(data.get("v", 0)),
                high_24h=float(data.get("h", 0)),
                low_24h=float(data.get("l", 0)),
                change_24h=float(data.get("P", 0)),
            )
            for handler in self._handlers["ticker"]:
                try:
                    handler(ticker)
                except Exception as e:
                    self.logger.error("Handler ticker error", extra={"error": str(e)})

        elif event_type == "depthUpdate":
            ob = OrderBook(
                symbol=data.get("s", ""),
                timestamp=datetime.now(UTC),
                bids=[{"price": float(p[0]), "amount": float(p[1]), "total": float(p[0]) * float(p[1])}
                      for p in data.get("b", [])],
                asks=[{"price": float(p[0]), "amount": float(p[1]), "total": float(p[0]) * float(p[1])}
                      for p in data.get("a", [])],
                exchange="binance",
            )
            for handler in self._handlers["orderbook"]:
                try:
                    handler(ob)
                except Exception as e:
                    self.logger.error("Handler orderbook error", extra={"error": str(e)})

        elif event_type == "kline":
            k = data.get("k", {})
            ohlcv = OHLCV(
                symbol=data.get("s", ""),
                timeframe=k.get("i", "1m"),
                timestamp=datetime.fromtimestamp(k.get("t", 0) / 1000, tz=UTC),
                open=float(k.get("o", 0)),
                high=float(k.get("h", 0)),
                low=float(k.get("l", 0)),
                close=float(k.get("c", 0)),
                volume=float(k.get("v", 0)),
                trades=int(k.get("n", 0)),
            )
            for handler in self._handlers["ohlcv"]:
                try:
                    handler(ohlcv)
                except Exception as e:
                    self.logger.error("Handler ohlcv error", extra={"error": str(e)})

    # ─── Contrôle du cycle de vie ───────────────────────

    async def start(self, symbols: list[str] | None = None) -> None:
        """Démarre toutes les connexions WebSocket."""
        if symbols is None:
            from src.config import config
            symbols = config.watchlist

        # Démarrer Binance
        await self.connect_binance(symbols)
        self.logger.info(
            "WebSocket Manager démarré",
            extra={"symbols_count": len(symbols)},
        )

    async def stop(self) -> None:
        """Arrête toutes les connexions WebSocket proprement."""
        for conn in self._connections:
            await conn.disconnect()

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._connections.clear()
        self._tasks.clear()
        self.logger.info("WebSocket Manager arrêté")

    @property
    def is_connected(self) -> bool:
        """Vérifie si au moins une connexion est active."""
        return any(
            conn._ws is not None and not conn._ws.closed
            for conn in self._connections
            if hasattr(conn, "_ws") and conn._ws
        )
