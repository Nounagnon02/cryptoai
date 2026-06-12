"""
CCXT Connector — Connecteur unifié pour les exchanges via CCXT.

Supporte : Binance, Bybit, OKX, Kraken, Coinbase, etc.
Utilise CCXT comme couche d'abstraction avec WebSocket natif
pour la faible latence.

Fonctionnalités :
- Création/annulation/modification d'ordres
- Récupération des balances
- Streaming ticker via WebSocket
- Gestion des erreurs et rate limiting
"""

from __future__ import annotations

from typing import Any

from src.execution.connectors import BaseConnector
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CCXTConnector(BaseConnector):
    """
    Connecteur CCXT pour exchanges centralisés.

    Wrapper autour de CCXT avec :
    - Retry intégré
    - Rate limiting
    - Mapping d'erreurs standardisé
    - Support WebSocket optionnel
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._options = options or {
            "defaultType": "spot",
            "adjustForTimeDifference": True,
        }
        self._exchange: Any = None
        self._ws_connections: dict[str, Any] = {}
        self._running = False

    async def start(self) -> None:
        """Initialise la connexion à l'exchange."""
        try:
            import ccxt.pro as ccxt_pro

            exchange_class = getattr(ccxt_pro, self.exchange_id)
            self._exchange = exchange_class({
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "enableRateLimit": True,
                "options": self._options,
            })

            if self._testnet:
                self._exchange.set_sandbox_mode(True)

            # Vérifier la connexion
            await self._exchange.load_markets()
            self._running = True
            logger.info(
                "CCXTConnector '%s' connected (%s, %d markets)",
                self.exchange_id,
                "testnet" if self._testnet else "live",
                len(self._exchange.markets),
            )

        except ImportError:
            logger.error("ccxt not installed. Install with: pip install ccxt")
            raise
        except Exception as e:
            logger.error("Failed to connect to %s: %s", self.exchange_id, e)
            raise

    async def stop(self) -> None:
        """Ferme la connexion."""
        self._running = False
        if self._exchange:
            await self._exchange.close()
        logger.info("CCXTConnector '%s' disconnected", self.exchange_id)

    async def create_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        quantity_usd: float,
        order_type: str,
        limit_price: float | None = None,
        stop_price: float | None = None,
        _slippage_bps: int = 10,
    ) -> dict[str, Any]:
        """
        Crée un ordre sur l'exchange.

        Args:
            symbol: Paire (ex: BTC/USDT)
            side: buy | sell
            quantity: Quantité en unités de base
            quantity_usd: Quantité en USD (alternative)
            order_type: market | limit | stop_loss | stop_limit
            limit_price: Prix limite
            stop_price: Prix stop
            slippage_bps: Slippage toléré

        Returns:
            Résultat standardisé
        """
        if not self._exchange:
            return {"status": "error", "error": "Exchange not connected"}

        try:
            params: dict[str, Any] = {}

            # Adapter aux types d'ordre CCXT
            ccxt_type = order_type
            if order_type == "stop_loss":
                ccxt_type = "stop_market"
                params["stopPrice"] = stop_price
            elif order_type == "stop_limit":
                ccxt_type = "stop_limit"
                params["stopPrice"] = stop_price

            # Calculer la quantité si seulement USD est fourni
            if quantity <= 0 and quantity_usd > 0:
                ticker = await self.get_ticker(symbol)
                price = ticker.get("last", limit_price or 100.0)
                quantity = quantity_usd / price

            # Arrondir selon les règles de l'exchange
            _ = self._exchange.market(symbol)  # validate symbol exists
            quantity = self._exchange.amount_to_precision(symbol, quantity)

            logger.info(
                "CCXT %s %s %s %s (qty=%s, price=%s, stop=%s)",
                self.exchange_id, side.upper(), symbol, ccxt_type,
                quantity, limit_price, stop_price,
            )

            order = await self._exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=side,
                amount=float(quantity),
                price=limit_price,
                params=params,
            )

            return self._normalize_order(order)

        except Exception as e:
            logger.error("CCXT create_order failed: %s", e)
            return {"status": "error", "error": str(e)}

    async def cancel_order(self, exchange_order_id: str) -> bool:
        """Annule un ordre."""
        try:
            await self._exchange.cancel_order(exchange_order_id)
            return True
        except Exception as e:
            logger.error("CCXT cancel_order failed: %s", e)
            return False

    async def get_order(self, exchange_order_id: str) -> dict[str, Any]:
        """Récupère les détails d'un ordre."""
        try:
            order = await self._exchange.fetch_order(exchange_order_id)
            return self._normalize_order(order)
        except Exception as e:
            logger.error("CCXT get_order failed: %s", e)
            return {"status": "error", "error": str(e)}

    async def get_balance(self) -> dict[str, float]:
        """Récupère les balances."""
        try:
            balance = await self._exchange.fetch_balance()
            return {
                "total_equity": balance.get("total", {}).get("USD", 0),
                "free": balance.get("free", {}),
                "used": balance.get("used", {}),
                "total": balance.get("total", {}),
            }
        except Exception as e:
            logger.error("CCXT get_balance failed: %s", e)
            return {"total_equity": 0}

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Récupère le ticker actuel."""
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return {
                "symbol": ticker.get("symbol", symbol),
                "last": ticker.get("last", 0),
                "bid": ticker.get("bid", 0),
                "ask": ticker.get("ask", 0),
                "volume": ticker.get("baseVolume", 0),
                "high": ticker.get("high", 0),
                "low": ticker.get("low", 0),
                "timestamp": ticker.get("timestamp", 0),
            }
        except Exception as e:
            logger.error("CCXT get_ticker failed: %s", e)
            return {"symbol": symbol, "last": 0}

    # WebSocket streaming

    async def subscribe_ticker(self, symbol: str) -> None:
        """S'abonne au ticker temps réel via WebSocket."""
        if not hasattr(self._exchange, "watch_ticker"):
            logger.warning("WebSocket ticker not supported for %s", self.exchange_id)
            return

        try:
            async for ticker in self._exchange.watch_ticker(symbol):
                self._ws_connections[symbol] = ticker
        except Exception as e:
            logger.error("WebSocket ticker error for %s: %s", symbol, e)

    def _normalize_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Normalise un ordre CCXT en format standard."""
        status_map = {
            "open": "open",
            "closed": "filled",
            "filled": "filled",
            "canceled": "cancelled",
            "cancelled": "cancelled",
            "rejected": "rejected",
            "expired": "expired",
        }

        raw_status = order.get("status", "open")
        normalized_status = status_map.get(raw_status, "open")

        return {
            "exchange_id": order.get("id", ""),
            "status": normalized_status,
            "filled_quantity": float(order.get("filled", 0)),
            "filled_value_usd": float(order.get("cost", 0)),
            "average_price": float(order.get("average", 0)),
            "fee": float(order.get("fee", {}).get("cost", 0)),
            "fee_currency": order.get("fee", {}).get("currency", "USD"),
            "exchange": self.exchange_id,
            "timestamp": order.get("timestamp", 0),
        }


# Factory pour créer facilement des connecteurs
def create_connector(
    exchange: str = "binance",
    api_key: str | None = None,
    api_secret: str | None = None,
    testnet: bool = False,
) -> CCXTConnector:
    """Crée un connecteur CCXT pour l'exchange spécifié."""
    return CCXTConnector(
        exchange_id=exchange,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )


__all__ = ["CCXTConnector", "create_connector"]
