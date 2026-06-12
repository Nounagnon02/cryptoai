"""
Stratégies de trading modulaires.

Chaque stratégie est un module indépendant qui :
- Génère des signaux d'achat/vente basés sur sa logique propre
- Rapporte un score de confiance (0-100)
- Définit ses propres paramètres de risque

Stratégies disponibles :
- Trend Following (EMA cross, ADX > 25)
- Momentum (RSI + ROC)
- Mean Reversion (Bollinger Bands)
- Swing Trading (multi-timeframe confluence)
"""

from __future__ import annotations

from enum import StrEnum

from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy
from .swing_trading import SwingTradingStrategy
from .trend_following import TrendFollowingStrategy


class StrategyType(StrEnum):
    """Identifiants normalisés pour les stratégies de trading.

    Remplace les magic strings dans tout le codebase.
    """

    TREND_FOLLOWING = "trend_following"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    SWING_TRADING = "swing_trading"


__all__ = [
    "StrategyType",
    "TrendFollowingStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "SwingTradingStrategy",
]
