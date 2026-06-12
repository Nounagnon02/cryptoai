"""
Tests unitaires pour le BacktestEngine.

Vérifie :
- L'initialisation du moteur avec différentes configurations
- Le calcul des indicateurs techniques
- Le comportement avec données synthétiques
- La gestion des trades et positions
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.backtesting.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
)
from src.data.market.schema import OHLCV
from src.portfolio.strategies import MomentumStrategy, TrendFollowingStrategy

# ---------- Fixtures ----------

@pytest.fixture
def default_config() -> BacktestConfig:
    return BacktestConfig(
        initial_capital=100_000.0,
        fee_rate=0.001,
        warmup_bars=20,
    )


@pytest.fixture
def engine(default_config: BacktestConfig) -> BacktestEngine:
    eng = BacktestEngine(config=default_config)
    eng.register_strategy("trend_following", TrendFollowingStrategy())
    eng.register_strategy("momentum", MomentumStrategy())
    return eng


@pytest.fixture
def synthetic_ohlcv() -> list[OHLCV]:
    """Génère une série OHLCV synthétique courte pour les tests."""
    data: list[OHLCV] = []
    base_price = 30000.0
    now = datetime.now(UTC)

    for i in range(200):
        price = base_price + (i * 10) + (i % 20) * 5  # trend up + noise
        data.append(OHLCV(
            symbol="BTC/USDT",
            timeframe="1h",
            timestamp=now - timedelta(hours=199 - i),
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price * 1.005,
            volume=1000.0 + (i * 10),
        ))

    return data


# ---------- Tests ----------

class TestBacktestConfig:
    """Tests de la configuration du backtest."""

    def test_default_values(self) -> None:
        """Vérifie les valeurs par défaut."""
        config = BacktestConfig()
        assert config.initial_capital == 100_000.0
        assert config.fee_rate == 0.001
        assert config.slippage_model == "conservative"
        assert config.slippage_bps == 10
        assert config.warmup_bars == 100
        assert config.max_positions == 5
        assert config.risk_free_rate == 0.05

    def test_custom_values(self) -> None:
        """Vérifie les valeurs personnalisées."""
        config = BacktestConfig(
            initial_capital=50000,
            fee_rate=0.002,
            slippage_model="aggressive",
            warmup_bars=50,
            max_positions=3,
        )
        assert config.initial_capital == 50000
        assert config.fee_rate == 0.002
        assert config.slippage_model == "aggressive"
        assert config.max_positions == 3


class TestBacktestTrade:
    """Tests du dataclass BacktestTrade."""

    def test_default_trade(self) -> None:
        """Vérifie les valeurs par défaut d'un trade."""
        trade = BacktestTrade(
            entry_time=datetime.now(UTC),
            symbol="BTC/USDT",
            side="buy",
            entry_price=30000.0,
            quantity=1.0,
            value_usd=30000.0,
        )
        assert trade.exit_time is None
        assert trade.exit_price is None
        assert trade.pnl == 0.0
        assert trade.holding_bars == 0
        assert trade.strategy == ""


class TestBacktestEngine:
    """Tests du moteur de backtest."""

    def test_initialization(self, engine: BacktestEngine) -> None:
        """Vérifie l'initialisation du moteur."""
        assert engine.config.initial_capital == 100_000.0
        assert "trend_following" in engine._strategies
        assert "momentum" in engine._strategies

    def test_register_strategy(self, engine: BacktestEngine) -> None:
        """Vérifie l'enregistrement des stratégies."""
        assert len(engine._strategies) == 2
        engine.register_strategy("mean_reversion", MagicMock())
        assert len(engine._strategies) == 3

    def test_prepare_data(self, engine: BacktestEngine) -> None:
        """Vérifie la conversion OHLCV → DataFrame."""
        data = [
            OHLCV(
                symbol="BTC/USDT", timeframe="1h",
                timestamp=datetime.now(UTC),
                open=100.0, high=110.0, low=90.0, close=105.0, volume=1000.0,
            )
        ]
        df = engine._prepare_data(data)
        assert not df.empty
        assert "close" in df.columns
        assert df["close"].iloc[0] == 105.0

    def test_compute_indicators(self, engine: BacktestEngine) -> None:
        """Vérifie le calcul des indicateurs techniques."""
        import numpy as np
        import pandas as pd

        # Générer un DataFrame avec assez de données
        dates = pd.date_range("2024-01-01", periods=250, freq="h")
        df = pd.DataFrame({
            "open": np.random.uniform(100, 110, 250),
            "high": np.random.uniform(105, 115, 250),
            "low": np.random.uniform(95, 105, 250),
            "close": np.random.uniform(100, 110, 250),
            "volume": np.random.uniform(1000, 5000, 250),
        }, index=dates)

        result = engine._compute_indicators(df)

        # Vérifier que les colonnes d'indicateurs existent
        expected_columns = [
            "ema_9", "ema_21", "ema_50", "ema_200",
            "rsi_14", "atr_14",
            "bb_upper", "bb_middle", "bb_lower",
            "adx_14", "volume_ratio",
            "supertrend",
        ]
        for col in expected_columns:
            assert col in result.columns, f"Missing indicator: {col}"

        # Vérifier que RSI est dans [0, 100]
        valid_rsi = result["rsi_14"].dropna()
        if len(valid_rsi) > 0:
            assert valid_rsi.min() >= 0
            assert valid_rsi.max() <= 100

    @pytest.mark.asyncio
    async def test_run_synthetic_data(
        self, engine: BacktestEngine, synthetic_ohlcv: list[OHLCV]
    ) -> None:
        """Exécute un backtest complet sur données synthétiques."""
        result = await engine.run(
            ohlcv_data=synthetic_ohlcv,
            strategy_name="trend_following",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        # Vérifications basiques du résultat
        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTC/USDT"
        assert result.strategy_name == "trend_following"
        assert result.initial_capital == 100_000.0
        assert result.total_bars == len(synthetic_ohlcv)
        assert result.total_trades >= 0

        # Le résultat doit avoir des métriques
        assert result.total_return_pct != 0
        assert result.equity_curve is not None
        assert len(result.equity_curve) > 0

    @pytest.mark.asyncio
    async def test_run_momentum(
        self, engine: BacktestEngine, synthetic_ohlcv: list[OHLCV]
    ) -> None:
        """Backtest avec la stratégie momentum."""
        result = await engine.run(
            ohlcv_data=synthetic_ohlcv,
            strategy_name="momentum",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert result.total_trades >= 0
        assert result.final_capital > 0

    @pytest.mark.asyncio
    async def test_unknown_strategy(self, engine: BacktestEngine, synthetic_ohlcv: list[OHLCV]) -> None:
        """Vérifie qu'une stratégie inconnue lève une erreur."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            await engine.run(
                ohlcv_data=synthetic_ohlcv,
                strategy_name="nonexistent_strategy",
                symbol="BTC/USDT",
                timeframe="1h",
            )

    @pytest.mark.asyncio
    async def test_empty_data_raises(self, engine: BacktestEngine) -> None:
        """Vérifie que des données vides lèvent une erreur."""
        with pytest.raises(ValueError, match="No OHLCV data"):
            await engine.run(
                ohlcv_data=[],
                strategy_name="trend_following",
                symbol="BTC/USDT",
                timeframe="1h",
            )

    def test_get_trend_direction(self, engine: BacktestEngine) -> None:
        """Vérifie la détection de tendance."""
        # Bullish: ema_short > ema_long et prix > ema_short
        assert engine._get_trend_direction(110, 100, 115) == "bullish"

        # Bearish: ema_short < ema_long et prix < ema_short
        assert engine._get_trend_direction(90, 100, 85) == "bearish"

        # Neutre
        assert engine._get_trend_direction(100, 100, 101) == "neutral"
        assert engine._get_trend_direction(110, 100, 100) == "neutral"  # prix < ema_short


class TestBacktestResult:
    """Tests du dataclass BacktestResult."""

    def test_default_result(self) -> None:
        """Vérifie les valeurs par défaut."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            symbol="BTC/USDT",
            timeframe="1h",
            strategy_name="test",
            start_date=datetime.now(UTC),
            end_date=datetime.now(UTC),
            total_bars=100,
            initial_capital=100000,
            final_capital=100000,
            total_return=0,
            total_return_pct=0,
            cash_remaining=100000,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            largest_win=0,
            largest_loss=0,
            avg_holding_bars=0,
            profit_factor=0,
            max_drawdown=0,
            max_drawdown_pct=0,
        )
        assert result.total_trades == 0
        assert result.win_rate == 0
        assert result.sharpe_ratio == 0.0
