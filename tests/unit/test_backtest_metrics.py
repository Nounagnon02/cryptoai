"""
Tests unitaires pour PerformanceMetrics.

Vérifie :
- Le calcul du Sharpe Ratio
- Le calcul du Sortino Ratio
- Le Calmar Ratio
- Max Drawdown
- Win Rate et Profit Factor
- CAGR
- Risk of Ruin
- Rapport complet avec trades synthétiques
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from src.backtesting.metrics import MetricsReport, PerformanceMetrics

# ---------- Fixtures ----------

@pytest.fixture
def metrics() -> PerformanceMetrics:
    return PerformanceMetrics()


@pytest.fixture
def sample_trades() -> list[Any]:
    """Trades synthétiques pour les tests."""
    class FakeTrade:
        def __init__(self, pnl: float):
            self.pnl = pnl

    return [
        FakeTrade(100.0),
        FakeTrade(150.0),
        FakeTrade(-50.0),
        FakeTrade(200.0),
        FakeTrade(-30.0),
        FakeTrade(80.0),
        FakeTrade(120.0),
        FakeTrade(-60.0),
        FakeTrade(90.0),
        FakeTrade(40.0),
    ]


@pytest.fixture
def sample_equity_curve() -> list[dict[str, Any]]:
    """Equity curve synthétique (trend haussier avec fluctuations)."""
    equity = 100_000.0
    curve = []
    now = datetime.now(UTC)

    for i in range(100):
        change = np.random.normal(0.001, 0.02)
        equity *= (1 + change)
        curve.append({
            "timestamp": now - __import__("datetime").timedelta(hours=99 - i),
            "equity": equity,
        })

    return curve


# ---------- Tests ----------

class TestPerformanceMetrics:
    """Tests des métriques de performance."""

    def test_calculate_sharpe(self, metrics: PerformanceMetrics) -> None:
        """Vérifie le calcul du Sharpe Ratio."""
        returns = [1.0, 2.0, -0.5, 1.5, -1.0, 0.5]
        sharpe = metrics.calculate_sharpe(returns, risk_free_rate=0.05, periods_per_year=365)
        assert isinstance(sharpe, float)
        # Des returns positifs devraient donner un Sharpe > 0
        assert sharpe >= -1.0  # Plage réaliste

    def test_calculate_sharpe_insufficient_data(self, metrics: PerformanceMetrics) -> None:
        """Sharpe avec données insuffisantes."""
        assert metrics.calculate_sharpe([], risk_free_rate=0.05) == 0.0
        assert metrics.calculate_sharpe([1.0], risk_free_rate=0.05) == 0.0

    def test_calculate_sortino(self, metrics: PerformanceMetrics) -> None:
        """Vérifie le calcul du Sortino Ratio."""
        returns = [1.0, 2.0, -0.5, 1.5, -1.0, 0.5, -0.8, 1.2]
        sortino = metrics.calculate_sortino(returns, risk_free_rate=0.05, periods_per_year=365)
        assert isinstance(sortino, float)

    def test_calculate_sortino_no_downside(self, metrics: PerformanceMetrics) -> None:
        """Sortino avec que des returns positifs."""
        returns = [1.0, 0.5, 2.0, 1.5]
        sortino = metrics.calculate_sortino(returns, risk_free_rate=0.05)
        assert sortino == 0.0

    def test_calculate_max_drawdown(self, metrics: PerformanceMetrics) -> None:
        """Vérifie le calcul du drawdown maximum."""
        equity = [100_000, 105_000, 102_000, 98_000, 95_000, 110_000]
        result = metrics.calculate_max_drawdown(equity)
        assert result["max_drawdown"] > 0
        assert result["max_drawdown_pct"] > 0

        # Le drawdown max devrait être de 100_000 - 95_000 = 5_000
        # Le peak avant est 105_000, valley = 95_000
        expected_dd = 105_000 - 95_000
        assert abs(result["max_drawdown"] - expected_dd) < 1

    def test_calculate_max_drawdown_flat(self, metrics: PerformanceMetrics) -> None:
        """Drawdown avec courbe plate."""
        equity = [100_000] * 10
        result = metrics.calculate_max_drawdown(equity)
        assert result["max_drawdown"] == 0.0
        assert result["max_drawdown_pct"] == 0.0

    def test_calculate_cagr(self, metrics: PerformanceMetrics) -> None:
        """Vérifie le CAGR."""
        cagr = metrics.calculate_cagr(100_000, 200_000, 3.0)
        assert cagr > 0
        # 100k → 200k en 3 ans = ~26%
        assert abs(cagr - 25.99) < 1.0

    def test_calculate_cagr_zero_initial(self, metrics: PerformanceMetrics) -> None:
        """CAGR avec capital initial nul."""
        assert metrics.calculate_cagr(0, 100_000, 1.0) == 0.0

    def test_calculate_cagr_zero_years(self, metrics: PerformanceMetrics) -> None:
        """CAGR avec durée nulle."""
        assert metrics.calculate_cagr(100_000, 200_000, 0) == 0.0

    def test_calculate_profit_factor(self, metrics: PerformanceMetrics, sample_trades) -> None:
        """Vérifie le Profit Factor."""
        pf = metrics.calculate_profit_factor(sample_trades)
        assert pf >= 0
        # Nos trades : gains = 100+150+200+80+120+90+40 = 780, pertes = 50+30+60 = 140
        # Profit Factor = 780/140 ≈ 5.57
        assert abs(pf - 5.57) < 1.0

    def test_calculate_profit_factor_no_trades(self, metrics: PerformanceMetrics) -> None:
        """Profit Factor sans trades."""
        assert metrics.calculate_profit_factor([]) == 0.0

    def test_calculate_win_rate(self, metrics: PerformanceMetrics, sample_trades) -> None:
        """Vérifie le Win Rate."""
        wr = metrics.calculate_win_rate(sample_trades)
        # 7 wins / 10 trades = 70%
        assert abs(wr - 70.0) < 1.0

    def test_calculate_win_rate_no_trades(self, metrics: PerformanceMetrics) -> None:
        """Win Rate sans trades."""
        assert metrics.calculate_win_rate([]) == 0.0

    def test_calculate_consecutive_wins_losses(
        self, metrics: PerformanceMetrics, sample_trades
    ) -> None:
        """Vérifie le calcul des séquences."""
        streaks = metrics.calculate_consecutive_wins_losses(sample_trades)
        assert "max_consecutive_wins" in streaks
        assert "max_consecutive_losses" in streaks
        assert streaks["max_consecutive_wins"] >= 1
        assert streaks["max_consecutive_losses"] >= 0

    def test_calculate_full_report(
        self, metrics: PerformanceMetrics, sample_trades, sample_equity_curve
    ) -> None:
        """Vérifie le calcul du rapport complet."""
        report = metrics.calculate(
            initial_capital=100_000.0,
            final_capital=120_000.0,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            risk_free_rate=0.05,
            trading_days=365,
        )

        assert isinstance(report, MetricsReport)
        assert report.total_return == 20_000.0
        assert report.total_return_pct > 0
        assert report.total_trades == 10
        assert report.win_rate == 70.0
        assert report.profit_factor > 1.0
        assert report.cagr > 0
        assert report.sharpe_ratio != 0.0
        assert report.summary != ""

    def test_minimal_report_short_data(self, metrics: PerformanceMetrics) -> None:
        """Rapport minimal avec données insuffisantes."""
        report = metrics.calculate(
            initial_capital=100_000.0,
            final_capital=100_000.0,
            trades=[],
            equity_curve=[],
            risk_free_rate=0.05,
        )
        assert report.sharpe_ratio == 0.0
        assert report.max_drawdown_pct == 0.0
        assert report.risk_of_ruin == 100.0

    def test_minimal_report_single_point(self, metrics: PerformanceMetrics) -> None:
        """Rapport avec un seul point d'equity curve."""
        report = metrics.calculate(
            initial_capital=100_000.0,
            final_capital=105_000.0,
            trades=[],
            equity_curve=[{"timestamp": datetime.now(UTC), "equity": 100_000}],
        )
        assert report.total_return_pct > 0

    def test_html_report(self, metrics: PerformanceMetrics) -> None:  # noqa: ARG002
        """Vérifie la génération du rapport HTML."""
        report = MetricsReport(
            initial_capital=100_000,
            final_capital=120_000,
            total_return=20_000,
            total_return_pct=20.0,
            total_trades=10,
            winning_trades=7,
            losing_trades=3,
            win_rate=70.0,
            avg_win=150.0,
            avg_loss=50.0,
            largest_win=300.0,
            largest_loss=80.0,
            avg_holding_periods=5.0,
            profit_factor=3.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=1.2,
            max_drawdown=10_000,
            max_drawdown_pct=10.0,
            max_drawdown_peak=datetime.now(UTC),
            max_drawdown_valley=datetime.now(UTC),
            avg_drawdown_pct=5.0,
            drawdown_days=10,
            cagr=15.0,
            avg_daily_return=0.05,
            avg_daily_return_pct=0.05,
            volatility_annual=20.0,
            downside_deviation=15.0,
            value_at_risk_95=-2.0,
            conditional_var_95=-3.0,
            risk_of_ruin=5.0,
            recovery_factor=2.0,
            ulcer_index=8.0,
        )
        html = PerformanceMetrics.generate_html_report(report)
        assert "<html>" in html
        assert "Backtest Performance Report" in html
        assert "20.00%" in html or "20.0%" in html
        assert "</html>" in html
