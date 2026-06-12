"""
Exchange Connectors — Connecteurs aux exchanges.

Couche d'abstraction pour les appels exchange :
- Interface unifiée pour create_order, cancel_order, get_order
- CCXT wrapper pour les exchanges standard
- WebSocket pour les mises à jour temps réel
- Gestion des erreurs et retry

Connecteurs disponibles :
- BaseConnector (interface)
- CCXTConnector (Binance, Bybit, OKX, etc.)
- PaperConnector (simulation)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Interface de base pour tous les connecteurs exchange."""

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        quantity_usd: float,
        order_type: str,
        limit_price: float | None = None,
        stop_price: float | None = None,
        slippage_bps: int = 10,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str) -> bool:
        ...

    @abstractmethod
    async def get_order(self, exchange_order_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_balance(self) -> dict[str, float]:
        ...

    @abstractmethod
    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        ...


__all__ = ["BaseConnector"]
