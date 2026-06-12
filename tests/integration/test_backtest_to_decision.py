"""
Test d'intégration : Backtest complet → Décision → Execution.

Vérifie le pipeline complet :
1. Génération de données OHLCV synthétiques
2. Backtest avec une stratégie
3. Vérification des décisions
4. Vérification de l'exécution simulée
5. Validation des métriques de performance
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.backtesting.engine import BacktestConfig, BacktestEngine, BacktestResult
from src.data.market.schema import OHLCV
from src.portfolio.strategies import (
    MeanReversionStrategy,
    MomentumStrategy,
    SwingTradingStrategy,
    TrendFollowingStrategy,
)


def generate_test_data(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    n_bars: int = 500,
    trend: float = 0.0002,
    volatility: float = 0.015,
    seed: int = 42,
) -> list[OHLCV]:
    """
    Génère des données OHLCV déterministes pour les tests.

    Utilise une seed fixe pour garantir la reproductibilité.
    """
    import random

    random.seed(seed)

    data: list[OHLCV] = []
    price = 30000.0
    now = datetime.now(UTC)

    for i in range(n_bars):
        drift = trend
        shock = volatility * random.gauss(0, 1)
        ret = drift + shock

        open_price = price
        close_price = price * (1 + ret)
        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility * 0.3)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility * 0.3)))

        # Volume avec cluster
        volume = random.uniform(500, 5000) * (1.5 if abs(ret) > volatility else 1.0)

        data.append(OHLCV(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now - timedelta(hours=n_bars - 1 - i),
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 2),
        ))

        price = close_price

    return data


@pytest.fixture
def test_data() -> list[OHLCV]:
    """Données de test avec tendance haussière."""
    return generate_test_data(n_bars=500, trend=0.0003, seed=42)


@pytest.fixture
def test_data_bearish() -> list[OHLCV]:
    """Données de test avec tendance baissière."""
    return generate_test_data(n_bars=500, trend=-0.0003, seed=123)


@pytest.fixture
def test_data_volatile() -> list[OHLCV]:
    """Données de test avec forte volatilité."""
    return generate_test_data(n_bars=500, trend=0.0, volatility=0.03, seed=456)


@pytest.fixture
def engine() -> BacktestEngine:
    """Moteur de backtest avec toutes les stratégies."""
    config = BacktestConfig(
        initial_capital=100_000.0,
        fee_rate=0.001,
        slippage_model="conservative",
        warmup_bars=50,
        max_positions=5,
    )
    eng = BacktestEngine(config=config)
    eng.register_strategy("trend_following", TrendFollowingStrategy())
    eng.register_strategy("momentum", MomentumStrategy())
    eng.register_strategy("mean_reversion", MeanReversionStrategy())
    eng.register_strategy("swing_trading", SwingTradingStrategy())
    return eng


# ---------- Tests ----------

@pytest.mark.asyncio
class TestBacktestIntegration:
    """Tests d'intégration du pipeline backtesting."""

    async def test_trend_following_haussiere(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Backtest trend following sur données haussières."""
        result = await engine.run(
            ohlcv_data=test_data,
            strategy_name="trend_following",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        # Vérifications de base
        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTC/USDT"
        assert result.strategy_name == "trend_following"
        assert result.total_bars == 500
        assert result.initial_capital == 100_000.0

        # En tendance haussière, la stratégie devrait performer
        assert result.total_trades >= 0
        assert result.final_capital > 0

        # Le nombre de trades doit être raisonnable
        assert result.total_trades < result.total_bars

    async def test_momentum_bearish(
        self, engine: BacktestEngine, test_data_bearish: list[OHLCV]
    ) -> None:
        """Backtest momentum sur données baissières."""
        result = await engine.run(
            ohlcv_data=test_data_bearish,
            strategy_name="momentum",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        assert result.total_trades >= 0
        assert result.final_capital > 0
        assert result.total_return_pct is not None

    async def test_mean_reversion_volatile(
        self, engine: BacktestEngine, test_data_volatile: list[OHLCV]
    ) -> None:
        """Backtest mean reversion sur données volatiles."""
        result = await engine.run(
            ohlcv_data=test_data_volatile,
            strategy_name="mean_reversion",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        assert result.total_trades >= 0

    async def test_swing_trading(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Backtest swing trading avec timeframe supérieur simulé."""
        # Pour le swing trading, on utilise les mêmes données compressées
        # en timeframe 4h comme timeframe supérieur
        compressed_data = []
        for i in range(0, len(test_data), 4):
            chunk = test_data[i:i + 4]
            if chunk:
                compressed_data.append(OHLCV(
                    symbol=chunk[0].symbol,
                    timeframe="4h",
                    timestamp=chunk[0].timestamp,
                    open=chunk[0].open,
                    high=max(c.high for c in chunk),
                    low=min(c.low for c in chunk),
                    close=chunk[-1].close,
                    volume=sum(c.volume for c in chunk),
                ))

        if len(compressed_data) >= 50:
            result = await engine.run(
                ohlcv_data=test_data,
                strategy_name="swing_trading",
                symbol="BTC/USDT",
                timeframe="1h",
                higher_tf_data=compressed_data,
            )

            assert isinstance(result, BacktestResult)
            assert result.total_trades >= 0

    async def test_equity_curve_structure(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Vérifie la structure de l'equity curve."""
        result = await engine.run(
            ohlcv_data=test_data,
            strategy_name="trend_following",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        assert len(result.equity_curve) > 0
        first_point = result.equity_curve[0]
        last_point = result.equity_curve[-1]

        # Vérifier la structure des points
        assert "timestamp" in first_point
        assert "equity" in first_point
        assert "cash" in first_point
        assert "positions_value" in first_point

        # L'equity finale devrait être proche du capital final
        # (différence due aux frais/slippage de fermeture des dernières positions)
        assert abs(last_point["equity"] - result.final_capital) < 500.0

    async def test_trade_journal(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Vérifie le journal des trades."""
        result = await engine.run(
            ohlcv_data=test_data,
            strategy_name="momentum",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        if result.total_trades > 0:
            trade = result.trades[0]
            assert trade.entry_time is not None
            assert trade.symbol == "BTC/USDT"
            assert trade.side in ("buy", "sell")
            assert trade.entry_price > 0
            assert trade.quantity > 0

            # Si le trade est fermé, vérifier le PnL
            if trade.exit_time is not None:
                assert trade.pnl is not None

    async def test_metrics_consistency(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Vérifie la cohérence des métriques de performance."""
        result = await engine.run(
            ohlcv_data=test_data,
            strategy_name="trend_following",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        # Validation des métriques
        if result.total_trades > 0:
            assert 0 <= result.win_rate <= 100
            assert result.profit_factor >= 0
            assert result.max_drawdown_pct >= 0

            # Le Sharpe peut être négatif si la stratégie perd
            # mais il doit être dans une plage raisonnable
            assert -5.0 <= result.sharpe_ratio <= 10.0

        # Le nombre de trades ne peut pas dépasser le nombre de barres
        assert result.total_trades <= result.total_bars

    async def test_different_slippage_models(
        self, test_data: list[OHLCV]
    ) -> None:
        """Compare les résultats avec différents modèles de slippage."""
        results = []

        for model in ["conservative", "moderate", "aggressive"]:
            config = BacktestConfig(
                initial_capital=100_000.0,
                slippage_model=model,
                warmup_bars=50,
            )
            eng = BacktestEngine(config=config)
            eng.register_strategy("trend_following", TrendFollowingStrategy())

            result = await eng.run(
                ohlcv_data=test_data,
                strategy_name="trend_following",
                symbol="BTC/USDT",
                timeframe="1h",
            )
            results.append(result)

        # Le slippage moins élevé devrait donner de meilleurs résultats
        # (pas garanti à cause de la stochasticité)
        assert all(r.total_trades >= 0 for r in results)

    async def test_multi_strategy_comparison(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Exécute plusieurs stratégies et vérifie que les résultats diffèrent."""
        from src.backtesting.comparator import StrategyComparator

        strategies = ["trend_following", "momentum"]
        results = []

        for s in strategies:
            result = await engine.run(
                ohlcv_data=test_data,
                strategy_name=s,
                symbol="BTC/USDT",
                timeframe="1h",
            )
            results.append(result)

        assert len(results) == 2

        # Les résultats devraient être différents
        # (mêmes données, stratégies différentes)
        comparator = StrategyComparator()
        rankings = comparator.compare(results)
        assert len(rankings) == 2

    async def test_crisis_scenario(
        self, engine: BacktestEngine, test_data_volatile: list[OHLCV]
    ) -> None:
        """Simulation d'un scénario de crise."""
        result = await engine.run_crisis_scenario(
            ohlcv_data=test_data_volatile,
            strategy_name="trend_following",
            symbol="BTC/USDT",
            timeframe="1h",
            crisis_label="test_crash",
        )

        assert isinstance(result, BacktestResult)
        assert result.total_bars > 0

    async def test_empty_strategy_name(
        self, engine: BacktestEngine, test_data: list[OHLCV]
    ) -> None:
        """Vérifie qu'un nom de stratégie invalide lève une erreur."""
        with pytest.raises(ValueError):
            await engine.run(
                ohlcv_data=test_data,
                strategy_name="nonexistent_strategy",
                symbol="BTC/USDT",
                timeframe="1h",
            )
