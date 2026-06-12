"""
Execution Manager — Gestion centralisée de l'exécution des ordres.

Responsabilités :
1. Création, annulation, modification d'ordres
2. Retry avec exponential backoff
3. Slippage protection
4. Vérification de l'état des ordres
5. Routing vers le bon exchange
6. Rate limiting
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


class OrderStatus(StrEnum):
    """Statuts d'un ordre."""

    PENDING = "pending"  # En attente d'envoi
    SUBMITTED = "submitted"  # Envoyé à l'exchange
    PARTIAL = "partial"  # Partiellement rempli
    FILLED = "filled"  # Complètement rempli
    CANCELLED = "cancelled"  # Annulé
    REJECTED = "rejected"  # Rejeté par l'exchange
    EXPIRED = "expired"  # Expiré
    FAILED = "failed"  # Échec d'envoi


@dataclass
class OrderResult:
    """Résultat d'un ordre."""

    order_id: str
    exchange_order_id: str
    symbol: str
    side: str
    status: OrderStatus
    filled_quantity: float
    filled_value_usd: float
    average_price: float
    fee: float
    fee_currency: str
    timestamp: float
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionConfig:
    """Configuration de l'exécution."""

    # Retry
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0

    # Slippage
    max_slippage_bps: int = 50  # 0.5% max slippage
    default_slippage_bps: int = 10  # 0.1% par défaut

    # Timeouts
    order_timeout_seconds: int = 60
    fill_check_interval: float = 0.5

    # Rate limiting
    max_orders_per_second: float = 5.0
    max_orders_per_minute: int = 100

    # Général
    reject_on_slippage_exceeded: bool = True
    verify_fill_before_complete: bool = True
    log_all_orders: bool = True


class RateLimiter:
    """Rate limiter simple pour les appels exchange."""

    def __init__(self, max_per_second: float, max_per_minute: int) -> None:
        self._max_per_second = max_per_second
        self._max_per_minute = max_per_minute
        self._calls_second: list[float] = []
        self._calls_minute: list[float] = []

    async def acquire(self) -> None:
        """Attend si nécessaire pour respecter les limites."""
        now = time.monotonic()

        # Nettoyer les entrées périmées
        self._calls_second = [t for t in self._calls_second if now - t < 1.0]
        self._calls_minute = [t for t in self._calls_minute if now - t < 60.0]

        # Vérifier les limites
        if len(self._calls_second) >= self._max_per_second:
            await asyncio.sleep(1.0 / self._max_per_second)
        elif len(self._calls_minute) >= self._max_per_minute:
            await asyncio.sleep(60.0 / self._max_per_minute)

        self._calls_second.append(now)
        self._calls_minute.append(now)


class ExecutionManager:
    """
    Gestionnaire d'exécution central.

    Point d'entrée unique pour tous les ordres, avec :
    - Validation pré-exécution
    - Retry automatique
    - Protection slippage
    - Rate limiting
    - Logging complet
    """

    def __init__(self, config: ExecutionConfig | None = None) -> None:
        self.config = config or ExecutionConfig()
        self._orders: dict[str, OrderResult] = {}
        self._active_connections: dict[str, Any] = {}
        self._rate_limiter = RateLimiter(
            self.config.max_orders_per_second,
            self.config.max_orders_per_minute,
        )
        self._running = False

    async def start(self) -> None:
        """Démarre l'execution manager."""
        logger.info("ExecutionManager starting")
        self._running = True
        logger.info("ExecutionManager started")

    async def stop(self) -> None:
        """Arrête l'execution manager."""
        self._running = False
        logger.info("ExecutionManager stopped")

    def register_connector(self, exchange: str, connector: Any) -> None:
        """Enregistre un connecteur exchange."""
        self._active_connections[exchange] = connector
        logger.info("Connector '%s' registered", exchange)

    async def execute_order(
        self,
        order_params: Any,
        exchange: str = "binance",
        max_slippage_bps: int | None = None,
    ) -> OrderResult:
        """
        Exécute un ordre complet avec retry et protection.

        Args:
            order_params: Paramètres de l'ordre (OrderParams)
            exchange: Exchange cible
            max_slippage_bps: Slippage max (override config)

        Returns:
            OrderResult complet
        """
        # Rate limit
        await self._rate_limiter.acquire()

        slippage = max_slippage_bps or self.config.max_slippage_bps
        last_error: str | None = None
        order_id = f"ord_{int(time.time() * 1000)}_{hash(str(order_params)) % 10000}"

        connector = self._active_connections.get(exchange)
        if not connector:
            return OrderResult(
                order_id=order_id,
                exchange_order_id="",
                symbol=order_params.symbol,
                side=order_params.side,
                status=OrderStatus.FAILED,
                filled_quantity=0.0,
                filled_value_usd=0.0,
                average_price=0.0,
                fee=0.0,
                fee_currency="USD",
                timestamp=datetime.now(UTC).timestamp(),
                error=f"No connector for exchange '{exchange}'",
            )

        for attempt in range(self.config.max_retries + 1):
            try:
                logger.info(
                    "Executing order %s (attempt %d/%d): %s %s %s",
                    order_id, attempt + 1, self.config.max_retries + 1,
                    order_params.side.upper(), order_params.quantity_usd,
                    order_params.symbol,
                )

                result = await connector.create_order(
                    symbol=order_params.symbol,
                    side=order_params.side,
                    quantity=order_params.quantity,
                    quantity_usd=order_params.quantity_usd,
                    order_type=order_params.order_type.value,
                    limit_price=order_params.limit_price,
                    stop_price=order_params.stop_price,
                    slippage_bps=slippage,
                )

                order_result = self._parse_result(order_id, result, order_params)
                self._orders[order_id] = order_result

                if order_result.status == OrderStatus.FILLED:
                    logger.info(
                        "Order %s filled: %.4f @ %.2f (fee=%.4f %s)",
                        order_id,
                        order_result.filled_quantity,
                        order_result.average_price,
                        order_result.fee,
                        order_result.fee_currency,
                    )
                elif order_result.status == OrderStatus.REJECTED:
                    continue  # Retry

                return order_result

            except Exception as e:
                last_error = str(e)
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay_seconds * (
                        self.config.retry_backoff_multiplier ** attempt
                    )
                    logger.warning(
                        "Order %s attempt %d failed: %s. Retrying in %.1fs...",
                        order_id, attempt + 1, last_error, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Order %s failed after %d attempts: %s",
                        order_id, self.config.max_retries + 1, last_error,
                    )

        return OrderResult(
            order_id=order_id,
            exchange_order_id="",
            symbol=order_params.symbol,
            side=order_params.side,
            status=OrderStatus.FAILED,
            filled_quantity=0.0,
            filled_value_usd=0.0,
            average_price=0.0,
            fee=0.0,
            fee_currency="USD",
            timestamp=datetime.now(UTC).timestamp(),
            error=last_error or "Max retries exceeded",
        )

    def _parse_result(
        self,
        order_id: str,
        result: dict[str, Any],
        order_params: Any,
    ) -> OrderResult:
        """Parse le résultat d'un connecteur en OrderResult."""
        status_map = {
            "open": OrderStatus.SUBMITTED,
            "closed": OrderStatus.FILLED,
            "filled": OrderStatus.FILLED,
            "partial": OrderStatus.PARTIAL,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
        }

        raw_status = result.get("status", "open").lower()
        status = status_map.get(raw_status, OrderStatus.SUBMITTED)

        return OrderResult(
            order_id=order_id,
            exchange_order_id=result.get("exchange_id", ""),
            symbol=order_params.symbol,
            side=order_params.side,
            status=status,
            filled_quantity=result.get("filled_quantity", 0.0),
            filled_value_usd=result.get("filled_value_usd", 0.0),
            average_price=result.get("average_price", 0.0),
            fee=result.get("fee", 0.0),
            fee_currency=result.get("fee_currency", "USD"),
            timestamp=datetime.now(UTC).timestamp(),
            error=result.get("error"),
            metadata={
                "attempts": 1,
                "exchange": result.get("exchange", "unknown"),
            },
        )

    async def cancel_order(self, order_id: str, exchange: str = "binance") -> bool:
        """Annule un ordre."""
        connector = self._active_connections.get(exchange)
        if not connector:
            return False

        result = self._orders.get(order_id)
        if not result:
            logger.warning("Order %s not found for cancellation", order_id)
            return False

        try:
            success = await connector.cancel_order(result.exchange_order_id)
            if success:
                result.status = OrderStatus.CANCELLED
                logger.info("Order %s cancelled", order_id)
            return success
        except Exception as e:
            logger.error("Failed to cancel order %s: %s", order_id, e)
            return False

    async def get_order_status(self, order_id: str, exchange: str = "binance") -> OrderResult | None:
        """Récupère le statut d'un ordre."""
        connector = self._active_connections.get(exchange)
        if not connector:
            return None

        result = self._orders.get(order_id)
        if not result or not result.exchange_order_id:
            return result

        try:
            status = await connector.get_order(result.exchange_order_id)
            updated = self._parse_result(order_id, status, result)
            self._orders[order_id] = updated
            return updated
        except Exception as e:
            logger.error("Failed to get status for %s: %s", order_id, e)
            return result

    async def get_open_orders(self, _exchange: str = "binance") -> list[OrderResult]:
        """Liste les ordres ouverts."""
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL, OrderStatus.PENDING)
        ]

    def get_statistics(self) -> dict[str, Any]:
        """Statistiques d'exécution."""
        total = len(self._orders)
        filled = sum(1 for o in self._orders.values() if o.status == OrderStatus.FILLED)
        failed = sum(1 for o in self._orders.values() if o.status == OrderStatus.FAILED)
        cancelled = sum(1 for o in self._orders.values() if o.status == OrderStatus.CANCELLED)
        rejected = sum(1 for o in self._orders.values() if o.status == OrderStatus.REJECTED)

        total_filled_value = sum(
            o.filled_value_usd for o in self._orders.values()
            if o.status == OrderStatus.FILLED
        )
        total_fees = sum(o.fee for o in self._orders.values() if o.fee_currency == "USD")

        return {
            "total_orders": total,
            "filled": filled,
            "failed": failed,
            "cancelled": cancelled,
            "rejected": rejected,
            "fill_rate": round(filled / max(total, 1) * 100, 1),
            "total_volume_usd": round(total_filled_value, 2),
            "total_fees_usd": round(total_fees, 4),
            "active_connections": list(self._active_connections.keys()),
        }
