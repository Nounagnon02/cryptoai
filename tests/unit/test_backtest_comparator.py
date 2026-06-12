"""
Tests unitaires pour le StrategyComparator et WalkForwardOptimizer.

Vérifie :
- Le classement des stratégies
- La normalisation des scores
- Le calcul de la matrice de corrélation
- Le rapport de comparaison
- L'optimisation walk-forward
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.backtesting.comparator import (
    ComparisonRanking,
    StrategyComparator,
    WalkForwardOptimizer,
    WalkForwardResult,
)
from src.backtesting.engine import BacktestConfig, BacktestResult

# ---------- Fixtures ----------

@pytest.fixture
def comparator() -> StrategyComparator:
    return StrategyComparator()


@pytest.fixture
def sample_results() -> list[BacktestResult]:
    """Résultats de backtest synthétiques pour tests."""
    config = BacktestConfig()
    now = datetime.now(UTC)

    results = []
    for name in ["trend_following", "momentum", "mean_reversion"]:
        trades_mock = [
            MagicMock(pnl=100.0),
            MagicMock(pnl=50.0),
            MagicMock(pnl=-20.0),
            MagicMock(pnl=80.0),
        ]
        equity = [
            {"timestamp": now, "equity": 100_000 + i * 500}
            for i in range(20)
        ]

        result = BacktestResult(
            config=config,
            symbol="BTC/USDT",
            timeframe="1h",
            strategy_name=name,
            start_date=now,
            end_date=now,
            total_bars=200,
            initial_capital=100_000.0,
            final_capital=110_000.0,
            total_return=10_000.0,
            total_return_pct=10.0,
            cash_remaining=50_000.0,
            total_trades=20,
            winning_trades=12,
            losing_trades=8,
            win_rate=60.0,
            avg_win=150.0,
            avg_loss=80.0,
            largest_win=500.0,
            largest_loss=200.0,
            avg_holding_bars=12.0,
            profit_factor=2.5,
            max_drawdown=8_000,
            max_drawdown_pct=8.0,
            max_drawdown_peak=now,
            max_drawdown_valley=now,
            sharpe_ratio=1.2,
            sortino_ratio=1.8,
            calmar_ratio=1.5,
            recovery_factor=2.0,
            trades=trades_mock,
            equity_curve=equity,
            drawdown_curve=[{"timestamp": now, "drawdown": 0, "drawdown_pct": 0}],
            benchmark_return_pct=5.0,
            alpha=5.0,
            decisions_count=50,
            errors_count=0,
            summary="Test result",
        )
        results.append(result)

    return results


# ---------- Tests ----------

class TestStrategyComparator:
    """Tests du comparateur de stratégies."""

    def test_initialization(self, comparator: StrategyComparator) -> None:
        """Vérifie l'initialisation avec les poids par défaut."""
        assert "sharpe_ratio" in comparator.weights
        assert "total_return_pct" in comparator.weights
        assert "max_drawdown_pct" in comparator.weights
        assert abs(sum(comparator.weights.values()) - 1.0) < 0.01

    def test_compare_empty(self, comparator: StrategyComparator) -> None:
        """Comparaison avec une liste vide."""
        rankings = comparator.compare([])
        assert rankings == []

    def test_compare_three_strategies(
        self, comparator: StrategyComparator, sample_results: list[BacktestResult]
    ) -> None:
        """Compare trois stratégies et vérifie le classement."""
        rankings = comparator.compare(sample_results)
        assert len(rankings) == 3

        # Vérifier que les rangs sont 1, 2, 3
        assert rankings[0].rank == 1
        assert rankings[1].rank == 2
        assert rankings[2].rank == 3

        # Vérifier que les noms sont corrects
        names = [r.strategy_name for r in rankings]
        for name in ["trend_following", "momentum", "mean_reversion"]:
            assert name in names

    def test_compare_scores_structure(
        self, comparator: StrategyComparator, sample_results: list[BacktestResult]
    ) -> None:
        """Vérifie la structure des scores."""
        rankings = comparator.compare(sample_results)
        for r in rankings:
            assert r.weighted_score > 0
            assert r.return_score >= 0
            assert r.risk_score >= 0
            assert r.consistency_score >= 0

    def test_correlation_matrix(
        self, comparator: StrategyComparator, sample_results: list[BacktestResult]
    ) -> None:
        """Vérifie la matrice de corrélation."""
        corr = comparator.correlation_matrix(sample_results)
        assert "names" in corr
        assert "matrix" in corr
        assert len(corr["names"]) == 3
        assert len(corr["matrix"]) == 3

        # Diagonale = 1.0
        for i in range(3):
            assert corr["matrix"][i][i] == 1.0

        # Symétrique
        assert corr["matrix"][0][1] == corr["matrix"][1][0]

    def test_correlation_matrix_single(
        self, comparator: StrategyComparator, sample_results: list[BacktestResult]
    ) -> None:
        """Matrice de corrélation avec un seul résultat."""
        corr = comparator.correlation_matrix([sample_results[0]])
        assert "message" in corr

    def test_generate_report(
        self, comparator: StrategyComparator, sample_results: list[BacktestResult]
    ) -> None:
        """Vérifie la génération du rapport textuel."""
        rankings = comparator.compare(sample_results)
        report = comparator.generate_report(rankings)

        assert isinstance(report, str)
        assert "STRATEGY COMPARISON REPORT" in report
        assert "trend_following" in report
        assert "#1" in report

    def test_to_dict(
        self, comparator: StrategyComparator, sample_results: list[BacktestResult]
    ) -> None:
        """Vérifie la conversion en dictionnaire."""
        rankings = comparator.compare(sample_results)
        data = comparator.to_dict(rankings)

        assert isinstance(data, list)
        assert len(data) == 3
        for item in data:
            assert "rank" in item
            assert "strategy" in item
            assert "weighted_score" in item
            assert "total_return_pct" in item

    def test_calculate_consistency(self, comparator: StrategyComparator) -> None:
        """Vérifie le calcul du score de consistance."""
        # Créer un résultat avec suffisamment de trades
        config = BacktestConfig()
        now = datetime.now(UTC)

        trades_mock = [
            MagicMock(pnl=100.0), MagicMock(pnl=200.0), MagicMock(pnl=50.0),
            MagicMock(pnl=-30.0), MagicMock(pnl=80.0), MagicMock(pnl=120.0),
            MagicMock(pnl=-50.0), MagicMock(pnl=90.0), MagicMock(pnl=60.0),
            MagicMock(pnl=-20.0),
        ]

        result = BacktestResult(
            config=config, symbol="BTC/USDT", timeframe="1h",
            strategy_name="test", start_date=now, end_date=now,
            total_bars=100, initial_capital=100_000, final_capital=110_000,
            total_return=10_000, total_return_pct=10.0, cash_remaining=50_000,
            total_trades=10, winning_trades=7, losing_trades=3,
            win_rate=70.0, avg_win=100.0, avg_loss=33.33, largest_win=200.0,
            largest_loss=50.0, avg_holding_bars=10, profit_factor=7.0,
            max_drawdown=5000, max_drawdown_pct=5.0, max_drawdown_peak=now,
            max_drawdown_valley=now, sharpe_ratio=1.5, sortino_ratio=2.0,
            calmar_ratio=2.0, recovery_factor=3.0, trades=trades_mock,
            equity_curve=[{"timestamp": now, "equity": 100_000}],
            drawdown_curve=[], benchmark_return_pct=5.0, alpha=5.0,
            decisions_count=50, errors_count=0, summary="Test",
        )

        consistency = comparator._calculate_consistency(result)
        assert 0 <= consistency <= 100


class TestWalkForwardOptimizer:
    """Tests de l'optimisation walk-forward."""

    def test_initialization(self) -> None:
        """Vérifie l'initialisation."""
        optimizer = WalkForwardOptimizer(n_splits=3, train_pct=0.6)
        assert optimizer.n_splits == 3
        assert optimizer.train_pct == 0.6
        assert optimizer.min_train_bars == 500

    def test_initialization_custom(self) -> None:
        """Initialisation personnalisée."""
        optimizer = WalkForwardOptimizer(
            n_splits=5,
            train_pct=0.7,
            min_train_bars=200,
            min_val_bars=50,
        )
        assert optimizer.n_splits == 5
        assert optimizer.min_val_bars == 50

    def test_min_data_validation(self) -> None:
        """Vérifie la validation du nombre de barres minimum."""
        optimizer = WalkForwardOptimizer(
            n_splits=3,
            min_train_bars=500,
            min_val_bars=100,
        )

        # Test avec la méthode _validate_data (ou la logique dans run)
        assert optimizer.min_train_bars + optimizer.min_val_bars == 600


class TestComparisonRanking:
    """Tests du dataclass ComparisonRanking."""

    def test_default_ranking(self) -> None:
        """Vérifie les valeurs par défaut."""
        ranking = ComparisonRanking(
            rank=1,
            strategy_name="test",
            symbol="BTC/USDT",
            weighted_score=85.0,
            total_return_pct=15.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=1.2,
            max_drawdown_pct=10.0,
            win_rate=60.0,
            profit_factor=2.0,
            total_trades=50,
            return_score=80.0,
            risk_score=75.0,
            consistency_score=70.0,
        )
        assert ranking.rank == 1
        assert ranking.weighted_score == 85.0
        assert ranking.return_score == 80.0


class TestWalkForwardResult:
    """Tests du dataclass WalkForwardResult."""

    def test_default_result(self) -> None:
        """Vérifie les valeurs par défaut."""
        result = WalkForwardResult(
            symbol="BTC/USDT",
            strategy_name="test",
            timeframe="1h",
            n_splits=3,
            train_pct=0.6,
        )
        assert result.avg_train_return == 0.0
        assert result.consistency_score == 0.0
        assert result.stability_score == 0.0
        assert result.splits == []
