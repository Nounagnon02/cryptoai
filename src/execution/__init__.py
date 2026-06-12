"""
Execution Engine — Passage et gestion des ordres.

Connecteurs exchange, gestion d'ordres, retry logic,
slippage protection, et paper trading.
"""

from __future__ import annotations

from .manager import ExecutionConfig, ExecutionManager, OrderResult, OrderStatus

__all__ = [
    "ExecutionManager",
    "ExecutionConfig",
    "OrderStatus",
    "OrderResult",
]
