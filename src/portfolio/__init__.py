"""
Portfolio Management System.

Gestion de portefeuille multi-stratégies :
- Allocation de capital (Kelly Criterion adapté)
- Auto-rebalancing (périodique + thresholds)
- Multi-strategy support (trend, momentum, mean reversion, swing)
- Risk-adjusted position sizing
"""

from __future__ import annotations

from .manager import PortfolioLimits, PortfolioManager, PortfolioState

__all__ = [
    "PortfolioManager",
    "PortfolioState",
    "PortfolioLimits",
]
