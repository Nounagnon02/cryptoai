"""
Backtesting Engine — Simulation historique des stratégies de trading.

Modules :
- engine : Moteur de backtest principal (BacktestEngine)
- metrics : Métriques de performance (Sharpe, Sortino, Calmar, etc.)
- comparator : Comparaison multi-stratégies et walk-forward optimization
- cli : Interface en ligne de commande

Réutilisation des modules existants :
- PaperExchange (src/execution/paper.py) pour la simulation d'exécution
- RiskManager (src/risk/manager.py) pour la validation des trades
- PortfolioManager (src/portfolio/manager.py) pour le suivi
- DecisionMatrix (src/core/decision_engine.py) pour les décisions
- Stratégies (src/portfolio/strategies/) pour les signaux
"""

from __future__ import annotations

from .engine import BacktestConfig, BacktestEngine, BacktestResult, BacktestTrade
from .metrics import MetricsReport, PerformanceMetrics

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "PerformanceMetrics",
    "MetricsReport",
]
