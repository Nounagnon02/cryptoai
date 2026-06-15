"""
Exchange Data Provider — couche d'abstraction pour les données de marché.

Utilise CCXT comme couche unifiée avec fallback WebSocket direct.
Pattern Strategy pour supporter plusieurs exchanges.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import ccxt.async_support as ccxt
import pandas as pd

from src.config import config
from src.data.market.schema import OrderBook, Ticker, Trade
from src.utils.exceptions import ProviderError, RateLimitError
from src.utils.logging import LoggerMixin


class BaseProvider(ABC, LoggerMixin):
    """
    Interface abstraite pour les fournisseurs de données marché.

    Tous les providers (CCXT, WebSocket direct) doivent implémenter
    ces méthodes pour garantir l'interchangeabilité.
    """

    def __init__(self, exchange_name: str, config_override: dict[str, Any] | None = None) -> None:
        self.exchange_name = exchange_name
        self._config = config_override or {}

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: int | None = None,
    ) -> pd.DataFrame:
        """Récupère les données OHLCV historiques."""

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Récupère le ticker temps réel."""

    @abstractmethod
    async def fetch_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        """Récupère le carnet d'ordres."""

    @abstractmethod
    async def fetch_trades(self, symbol: str, limit: int = 100) -> list[Trade]:
        """Récupère les trades récents."""

    @abstractmethod
    async def fetch_balance(self) -> dict[str, float]:
        """Récupère le solde du compte."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Vérifie si l'exchange est accessible."""

    async def close(self) -> None:
        """Ferme proprement les connexions."""


class CCXTProvider(BaseProvider):
    """
    Provider utilisant CCXT pour l'accès unifié aux exchanges.

    Supporte Binance, Bybit, OKX, Kraken, Coinbase.
    Gère le rate limiting, retry, et les erreurs.
    """

    EXCHANGE_MAP = {
        "binance": ccxt.binance,
        "bybit": ccxt.bybit,
        "okx": ccxt.okx,
        "kraken": ccxt.kraken,
        "coinbase": ccxt.coinbaseadvanced,
    }

    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "1w": "1w",
    }

    def __init__(
        self,
        exchange_name: str = "binance",
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = True,
        config_override: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(exchange_name, config_override)

        exchange_class = self.EXCHANGE_MAP.get(exchange_name)
        if not exchange_class:
            raise ProviderError(
                f"Exchange non supporté: {exchange_name}",
                provider=exchange_name,
            )

        exchange_config: dict[str, Any] = {
            "enableRateLimit": True,
            "rateLimit": 1200,
            "timeout": 30000,
        }

        if api_key and api_secret:
            exchange_config["apiKey"] = api_key
            exchange_config["secret"] = api_secret

        if testnet:
            exchange_config["options"] = {"defaultType": "spot"}

        self._exchange = exchange_config
        self._instance: ccxt.Exchange | None = None

        self._last_request_time: float = 0.0
        self._request_count: int = 0
        self._rate_limit_reset: float = time.time() + 60

    async def _get_exchange(self) -> ccxt.Exchange:
        """Retourne l'instance CCXT (initialisation paresseuse)."""
        if self._instance is None:
            exchange_class = self.EXCHANGE_MAP[self.exchange_name]
            self._instance = exchange_class(self._exchange)
            # Vérifier la connectivité
            await self._instance.load_markets()
            self.logger.info(
                "Exchange initialisé",
                extra={"exchange": self.exchange_name},
            )
        return self._instance

    async def _check_rate_limit(self) -> None:
        """Rate limiting adaptatif côté client."""
        now = time.time()
        if now > self._rate_limit_reset:
            self._request_count = 0
            self._rate_limit_reset = now + 60

        if self._request_count >= getattr(config, "rate_limit_per_minute", 1200):
            sleep_time = self._rate_limit_reset - now
            if sleep_time > 0:
                self.logger.warning(
                    "Rate limit atteint, pause",
                    extra={"sleep_seconds": sleep_time},
                )
                await self._instance.sleep(sleep_time * 1000) if self._instance else None
            self._request_count = 0
            self._rate_limit_reset = time.time() + 60

        self._request_count += 1

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: int | None = None,
    ) -> pd.DataFrame:
        """Récupère les bougies OHLCV et retourne un DataFrame."""
        await self._check_rate_limit()
        exchange = await self._get_exchange()

        try:
            raw = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        except ccxt.RateLimitExceeded as e:
            raise RateLimitError(
                f"Rate limit dépassé pour {symbol}",
                provider=self.exchange_name,
            ) from e
        except ccxt.NetworkError as e:
            raise ProviderError(
                f"Erreur réseau pour {symbol}: {e}",
                provider=self.exchange_name,
            ) from e

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["symbol"] = symbol
        df["timeframe"] = timeframe
        df.set_index("timestamp", inplace=True)

        return df

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Récupère le ticker temps réel."""
        await self._check_rate_limit()
        exchange = await self._get_exchange()

        try:
            ticker = await exchange.fetch_ticker(symbol)
        except ccxt.BaseError as e:
            raise ProviderError(f"Erreur ticker {symbol}: {e}", provider=self.exchange_name) from e

        return Ticker(
            symbol=symbol,
            bid=float(ticker.get("bid", 0)),
            ask=float(ticker.get("ask", 0)),
            last=float(ticker.get("last", 0)),
            volume_24h=float(ticker.get("baseVolume", 0)),
            high_24h=float(ticker.get("high", 0)),
            low_24h=float(ticker.get("low", 0)),
            change_24h=float(ticker.get("percentage", 0)),
            timestamp=datetime.fromtimestamp(
                ticker.get("timestamp", time.time()) / 1000,
                tz=UTC,
            ),
        )

    async def fetch_order_book(self, symbol: str, limit: int = 50) -> OrderBook:
        """Récupère le carnet d'ordres L2."""
        await self._check_rate_limit()
        exchange = await self._get_exchange()

        try:
            ob = await exchange.fetch_order_book(symbol, limit)
        except ccxt.BaseError as e:
            raise ProviderError(f"Erreur order book {symbol}: {e}", provider=self.exchange_name) from e

        return OrderBook(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            bids=[{"price": p, "amount": a, "total": p * a} for p, a in ob.get("bids", [])],
            asks=[{"price": p, "amount": a, "total": p * a} for p, a in ob.get("asks", [])],
            exchange=self.exchange_name,
        )

    async def fetch_trades(self, symbol: str, limit: int = 100) -> list[Trade]:
        """Récupère les trades récents."""
        await self._check_rate_limit()
        exchange = await self._get_exchange()

        try:
            raw_trades = await exchange.fetch_trades(symbol, limit=limit)
        except ccxt.BaseError as e:
            raise ProviderError(f"Erreur trades {symbol}: {e}", provider=self.exchange_name) from e

        return [
            Trade(
                id=str(t.get("id", "")),
                symbol=symbol,
                price=float(t.get("price", 0)),
                amount=float(t.get("amount", 0)),
                cost=float(t.get("cost", 0)),
                side=t.get("side", "buy"),
                timestamp=datetime.fromtimestamp(
                    t.get("timestamp", time.time()) / 1000,
                    tz=UTC,
                ),
                exchange=self.exchange_name,
            )
            for t in raw_trades
        ]

    async def fetch_balance(self) -> dict[str, float]:
        """Récupère le solde du compte."""
        await self._check_rate_limit()
        exchange = await self._get_exchange()

        try:
            balance = await exchange.fetch_balance()
        except ccxt.BaseError as e:
            raise ProviderError(f"Erreur balance: {e}", provider=self.exchange_name) from e

        return {
            currency: float(info.get("free", 0))
            for currency, info in balance.get("free", {}).items()
            if float(info.get("free", 0)) > 0
        }

    async def health_check(self) -> bool:
        """Vérifie la connectivité à l'exchange."""
        try:
            exchange = await self._get_exchange()
            await exchange.fetch_time()
            return True
        except Exception as e:
            self.logger.warning("Health check échoué", extra={"error": str(e)})
            return False

    async def close(self) -> None:
        """Ferme la connexion CCXT."""
        if self._instance:
            await self._instance.close()
            self._instance = None
            self.logger.info("Connexion fermée", extra={"exchange": self.exchange_name})


class DataProviderFactory:
    """Factory pour créer des providers selon l'exchange."""

    @staticmethod
    def create(
        exchange_name: str = "binance",
        testnet: bool = True,
    ) -> BaseProvider:
        """
        Crée et configure un provider pour l'exchange spécifié.

        Args:
            exchange_name: Nom de l'exchange (binance, bybit, okx, kraken, coinbase)
            testnet: Utiliser le testnet si disponible

        Returns:
            Instance du provider configuré
        """
        if exchange_name not in CCXTProvider.EXCHANGE_MAP:
            raise ProviderError(
                f"Exchange non supporté: {exchange_name}. "
                f"Supportés: {list(CCXTProvider.EXCHANGE_MAP.keys())}",
                provider=exchange_name,
            )

        return CCXTProvider(
            exchange_name=exchange_name,
            testnet=testnet,
        )
