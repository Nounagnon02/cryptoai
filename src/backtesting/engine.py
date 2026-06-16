"""
Backtest Engine — Simulation historique de stratégies de trading.

Parcourt les données OHLCV historiques, applique les stratégies,
simule l'exécution via PaperExchange, et calcule les métriques.

Utilisation :
    engine = BacktestEngine(config=BacktestConfig(initial_capital=100_000))
    result = engine.run(
        ohlcv_data=data,           # List[OHLCV]
        strategy_name="trend_following",
        symbol="BTC/USDT",
        timeframe="1h",
    )
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from src.backtesting.metrics import PerformanceMetrics
from src.core.decision_engine import ActionType, DecisionMatrix
from src.data.market.schema import OHLCV
from src.execution.paper import PaperExchange
from src.portfolio.manager import PortfolioManager
from src.risk.manager import RiskManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestConfig:
    """Configuration du backtest."""

    # Capital
    initial_capital: float = 100_000.0

    # Frais et slippage
    fee_rate: float = 0.001  # 0.1%
    slippage_model: str = "conservative"  # conservative | moderate | aggressive
    slippage_bps: int = 10

    # Warmup
    warmup_bars: int = 100  # Minimum de barres avant de générer des signaux

    # Limites
    max_positions: int = 5  # Nombre maximum de positions simultanées
    max_positions_per_symbol: int = 1

    # Multi-timeframe (optionnel)
    higher_tf_ratio: int = 4  # Ex: 1h → 4h = 4x

    # Benchmark
    benchmark_symbol: str = "BTC/USDT"

    # Reporting
    risk_free_rate: float = 0.05  # 5% annualisé (T-bills)
    trading_days_per_year: int = 365


@dataclass
class BacktestTrade:
    """Trade enregistré pendant le backtest."""

    entry_time: datetime
    exit_time: datetime | None = None
    symbol: str = ""
    side: str = ""  # buy | sell
    entry_price: float = 0.0
    exit_price: float | None = None
    quantity: float = 0.0
    value_usd: float = 0.0
    fee: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_bars: int = 0
    strategy: str = ""
    reason: str = ""
    action: str = ""  # strong_buy | buy | reinforce | reduce | sell | strong_sell


@dataclass
class BacktestResult:
    """Résultat complet d'un backtest."""

    # Configuration
    config: BacktestConfig
    symbol: str
    timeframe: str
    strategy_name: str
    start_date: datetime
    end_date: datetime
    total_bars: int

    # Capital
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    cash_remaining: float

    # Trades
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_holding_bars: float
    profit_factor: float

    # Métriques de risque
    max_drawdown: float
    max_drawdown_pct: float
    max_drawdown_peak: datetime = datetime.min
    max_drawdown_valley: datetime = datetime.min
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0

    # Séries
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    drawdown_curve: list[dict[str, Any]] = field(default_factory=list)

    # Benchmark
    benchmark_return_pct: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0

    # Résumé textuel
    summary: str = ""

    # Métadonnées
    decisions_count: int = 0
    errors_count: int = 0


@dataclass
class WalkForwardWindow:
    """Résultat d'une fenêtre de walk-forward validation."""

    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_bars: int
    test_bars: int
    result: BacktestResult | None = None
    status: str = "pending"  # pending | running | completed | failed
    error: str | None = None


@dataclass
class WalkForwardResult:
    """Résultat agrégé de walk-forward validation."""

    # Configuration
    strategy_name: str
    symbol: str
    timeframe: str
    total_windows: int
    completed_windows: int

    # Métriques out-of-sample agrégées
    windows: list[WalkForwardWindow] = field(default_factory=list)

    # Agrégation OOS
    total_return_pct_oos: float = 0.0
    sharpe_ratio_oos: float = 0.0
    sortino_ratio_oos: float = 0.0
    max_drawdown_pct_oos: float = 0.0
    win_rate_oos: float = 0.0
    profit_factor_oos: float = 0.0

    # Stabilité
    window_returns: list[float] = field(default_factory=list)
    return_std: float = 0.0  # Écart-type des returns OOS — plus bas = plus stable
    consistency_score: float = 0.0  # % de fenêtres positives

    # Benchmarks
    benchmark_return_pct_oos: float = 0.0
    alpha_vs_benchmark: float = 0.0  # Exces de rendement vs buy-and-hold

    # Robustesse
    is_robust: bool = False
    robustness_issues: list[str] = field(default_factory=list)

    # Résumé
    summary: str = ""


class BacktestEngine:
    """
    Moteur de backtest principal.

    Parcourt les données OHLCV, génère des signaux via les stratégies,
    exécute via PaperExchange, et calcule les métriques de performance.

    Usage :
        engine = BacktestEngine()
        result = await engine.run(ohlcv_data, "trend_following", "BTC/USDT", "1h")
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

        # Modules réutilisés
        self._exchange: PaperExchange | None = None
        self._decision_matrix = DecisionMatrix()
        self._risk_manager = RiskManager()
        self._portfolio_manager = PortfolioManager()

        # Stratégies disponibles
        self._strategies: dict[str, Any] = {}

        # Données
        self._ohlcv: list[OHLCV] = []
        self._higher_tf_ohlcv: list[OHLCV] = []
        self._prices: dict[str, list[float]] = {}

        # Indicateurs pré-calculés (rolling windows)
        self._indicators_cache: dict[str, pd.DataFrame] = {}

    def register_strategy(self, name: str, strategy: Any) -> None:
        """Enregistre une stratégie pour le backtest."""
        self._strategies[name] = strategy

    def _prepare_data(self, ohlcv_data: list[OHLCV]) -> pd.DataFrame:
        """Convertit les données OHLCV en DataFrame avec indicateurs."""
        df = pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in ohlcv_data
        ])
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcule les indicateurs techniques de base nécessaires aux stratégies.

        Utilise pandas pour les calculs vectorisés (évite TA-Lib comme dépendance
        obligatoire pour le backtest — les valeurs historiques sont approximées).
        """
        # Moyennes mobiles (Trend)
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

        df["sma_20"] = df["close"].rolling(window=20).mean()
        df["sma_50"] = df["close"].rolling(window=50).mean()

        # RSI (Momentum)
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(span=14, adjust=False).mean()
        avg_loss = loss.ewm(span=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # Stochastic RSI
        rsi_series = df["rsi_14"]
        stoch_k = (
            (rsi_series - rsi_series.rolling(14).min())
            / (rsi_series.rolling(14).max() - rsi_series.rolling(14).min()).replace(0, np.nan)
        ) * 100
        df["stoch_rsi_k"] = stoch_k
        df["stoch_rsi_d"] = stoch_k.rolling(3).mean()

        # ROC (Rate of Change)
        df["roc_10"] = df["close"].pct_change(periods=10) * 100

        # ATR (Volatility)
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.ewm(span=14, adjust=False).mean()

        # Bollinger Bands (Volatility)
        bb_sma = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = bb_sma + (bb_std * 2)
        df["bb_middle"] = bb_sma
        df["bb_lower"] = bb_sma - (bb_std * 2)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-10)

        # ADX (Trend strength)
        plus_dm = df["high"].diff()
        minus_dm = df["low"].diff()
        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > -minus_dm), 0.0)
        minus_dm = minus_dm.where((-minus_dm > 0) & (-minus_dm > plus_dm), 0.0)
        atr = df["atr_14"].replace(0, np.nan)
        df["plus_di"] = 100 * plus_dm.ewm(span=14).mean() / atr
        df["minus_di"] = 100 * minus_dm.ewm(span=14).mean() / atr
        dx = (abs(df["plus_di"] - df["minus_di"]) / (df["plus_di"] + df["minus_di"]).replace(0, np.nan)) * 100
        df["adx_14"] = dx.ewm(span=14, adjust=False).mean()

        # OBV (Volume)
        obv = [0.0]
        for i in range(1, len(df)):
            if df["close"].iloc[i] > df["close"].iloc[i - 1]:
                obv.append(obv[-1] + df["volume"].iloc[i])
            elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
                obv.append(obv[-1] - df["volume"].iloc[i])
            else:
                obv.append(obv[-1])
        df["obv"] = obv

        # Volume ratio
        df["volume_sma_20"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma_20"].replace(0, np.nan)

        # Supertrend
        period = 10
        multiplier = 3
        hl_avg = (df["high"] + df["low"]) / 2
        atr_st = df["atr_14"].rolling(period).mean()
        df["supertrend_upper"] = hl_avg + multiplier * atr_st
        df["supertrend_lower"] = hl_avg - multiplier * atr_st
        supertrend = [1.0]  # 1 = uptrend, -1 = downtrend
        for i in range(1, len(df)):
            if df["close"].iloc[i] > df["supertrend_upper"].iloc[i - 1]:
                supertrend.append(1.0)
            elif df["close"].iloc[i] < df["supertrend_lower"].iloc[i - 1]:
                supertrend.append(-1.0)
            else:
                supertrend.append(supertrend[-1])
        df["supertrend"] = supertrend

        # Williams %R
        highest_high = df["high"].rolling(14).max()
        lowest_low = df["low"].rolling(14).min()
        df["williams_r"] = -100 * (highest_high - df["close"]) / (highest_high - lowest_low).replace(0, np.nan)

        # Money Flow Index
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        money_flow = typical_price * df["volume"]
        positive_flow = money_flow.where(typical_price > typical_price.shift(), 0.0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(), 0.0)
        pos_total = positive_flow.rolling(14).sum()
        neg_total = negative_flow.rolling(14).sum()
        mfr = pos_total / neg_total.replace(0, np.nan)
        df["mfi_14"] = 100 - (100 / (1 + mfr))

        # Donchian Channels
        df["donchian_upper"] = df["high"].rolling(20).max()
        df["donchian_lower"] = df["low"].rolling(20).min()
        df["donchian_mid"] = (df["donchian_upper"] + df["donchian_lower"]) / 2

        return df

    async def run(
        self,
        ohlcv_data: list[OHLCV],
        strategy_name: str,
        symbol: str,
        timeframe: str,
        higher_tf_data: list[OHLCV] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BacktestResult:
        """
        Exécute un backtest complet.

        Args:
            ohlcv_data: Données OHLCV historiques (triées par timestamp)
            strategy_name: Nom de la stratégie à utiliser
            symbol: Paire de trading
            timeframe: Timeframe des données (1m, 5m, 1h, 1d...)
            higher_tf_data: Données timeframe supérieur pour stratégies multi-TF
            progress_callback: Callback optionnel (current, total) pour suivi

        Returns:
            BacktestResult avec toutes les métriques
        """
        if not ohlcv_data:
            raise ValueError("No OHLCV data provided for backtest")

        strategy = self._strategies.get(strategy_name)
        if not strategy:
            raise ValueError(f"Unknown strategy: '{strategy_name}'. Available: {list(self._strategies.keys())}")

        self._initialize_modules(strategy_name, symbol)

        # Prepare data
        df = self._prepare_data(ohlcv_data)
        df = self._compute_indicators(df)

        # Higher timeframe data
        higher_tf_df: pd.DataFrame | None = None
        if higher_tf_data:
            higher_tf_df = self._prepare_data(higher_tf_data)
            higher_tf_df = self._compute_indicators(higher_tf_df)

        start_date = df.index[0].to_pydatetime() if isinstance(df.index[0], pd.Timestamp) else df.index[0]
        end_date = df.index[-1].to_pydatetime() if isinstance(df.index[-1], pd.Timestamp) else df.index[-1]

        first_close = float(df["close"].iloc[0])
        self._exchange.update_price(symbol, first_close)

        warmup = min(self.config.warmup_bars, len(df) - 1)
        logger.info(
            "Backtest starting: %s %s | %s → %s | %d bars (warmup=%d)",
            strategy_name, symbol,
            start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
            len(df), warmup,
        )

        trades: list[BacktestTrade] = []
        equity_curve: list[dict[str, Any]] = []
        drawdown_curve: list[dict[str, Any]] = []
        decisions_count = 0
        errors_count = 0
        peak_value = self.config.initial_capital
        open_trades: dict[str, BacktestTrade] = {}

        total_bars = len(df)

        for i in range(warmup, total_bars):
            bar = df.iloc[i]
            current_price = float(bar["close"])
            current_time = bar.name.to_pydatetime() if isinstance(bar.name, pd.Timestamp) else bar.name

            self._exchange.update_price(symbol, current_price)
            indicators = self._extract_bar_indicators(bar, current_price, df, i)

            # Higher timeframe context
            ht_indicators: dict[str, Any] = {}
            if higher_tf_df is not None:
                ht_time = current_time
                if not higher_tf_df.empty:
                    ht_idx = higher_tf_df.index.get_indexer([ht_time], method="pad")[0]
                    if ht_idx >= 0:
                        ht_bar = higher_tf_df.iloc[ht_idx]
                        ht_indicators = {
                            "trend": self._get_trend_direction(
                                float(ht_bar["ema_50"]), float(ht_bar["ema_200"]),
                                float(ht_bar["close"]),
                            ),
                            "adx": float(ht_bar["adx_14"]) if pd.notna(ht_bar["adx_14"]) else 0.0,
                            "rsi": float(ht_bar["rsi_14"]) if pd.notna(ht_bar["rsi_14"]) else 50.0,
                            "price": float(ht_bar["close"]),
                            "momentum": float(ht_bar["roc_10"]) if pd.notna(ht_bar["roc_10"]) else 0.0,
                        }

            # Generate signal
            try:
                signal = self._generate_signal(strategy, strategy_name, indicators, ht_indicators, current_price)
            except Exception as e:
                logger.error("Backtest signal error at bar %d: %s", i, e)
                errors_count += 1
                continue

            score = getattr(signal, "score", 50.0)
            direction = getattr(signal, "direction", "neutral")
            confidence = getattr(signal, "confidence", 0.5) * 100.0

            # Check exit conditions for existing positions
            existing_position = open_trades.get(symbol)
            should_exit = strategy.should_exit(signal) if hasattr(strategy, "should_exit") else False

            if should_exit and existing_position:
                closed = await self._close_position(
                    symbol, existing_position, current_price, current_time,
                    trades, open_trades, i, warmup,
                )
                if closed:
                    continue

            if symbol in open_trades:
                continue

            if len(open_trades) >= self.config.max_positions:
                continue

            # Decision via DecisionMatrix
            portfolio_value = float(self._exchange._cash_reserve + sum(
                p.value_usd for p in open_trades.values()
            ))
            decision = self._decision_matrix.decide(
                symbol=symbol,
                score=score,
                direction=direction,
                confidence=confidence,
                strength=getattr(signal, "strength", 0.5),
                current_position=existing_position.value_usd if existing_position else 0.0,
                portfolio_value=portfolio_value,
            )
            decisions_count += 1

            # Execute if BUY
            await self._execute_trade_decision(
                symbol, decision, current_price, indicators, open_trades,
                strategy_name, current_time, i, portfolio_value, score, confidence,
            )

            # Update equity curve
            peak_value = self._update_equity_curve(
                equity_curve, drawdown_curve, current_time, open_trades, peak_value,
            )

            # Progress callback
            if progress_callback:
                progress_callback(i - warmup + 1, total_bars - warmup)

        return await self._finalize_result(
            df, trades, equity_curve, drawdown_curve, end_date,
            decisions_count, errors_count, strategy_name, symbol,
            warmup, total_bars, open_trades, start_date, timeframe,
        )

    async def run_multi_strategy(
        self,
        ohlcv_data: list[OHLCV],
        symbols: list[str],
        timeframe: str,
        strategies: list[str],
        higher_tf_data: dict[str, list[OHLCV]] | None = None,
    ) -> dict[str, BacktestResult]:
        """
        Exécute plusieurs backtests séquentiellement.

        Args:
            ohlcv_data: Données OHLCV pour le premier symbole (ou Dict par symbole)
            symbols: Liste des symboles à backtester
            timeframe: Timeframe
            strategies: Liste des noms de stratégies
            higher_tf_data: Données timeframe supérieur par symbole

        Returns:
            {strategy_symbol: BacktestResult}
        """
        results: dict[str, BacktestResult] = {}

        for symbol in symbols:
            for strategy_name in strategies:
                key = f"{strategy_name}_{symbol}"
                logger.info("Multi-strategy: running %s", key)

                sym_data = ohlcv_data
                sym_ht_data = higher_tf_data.get(symbol) if higher_tf_data else None

                result = await self.run(
                    ohlcv_data=sym_data,
                    strategy_name=strategy_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    higher_tf_data=sym_ht_data,
                )
                results[key] = result

        return results

    async def run_crisis_scenario(
        self,
        ohlcv_data: list[OHLCV],
        strategy_name: str,
        symbol: str,
        timeframe: str,
        crisis_label: str = "unknown",
    ) -> BacktestResult:
        """
        Exécute un backtest sur une période de crise spécifique.

        Utile pour valider la robustesse des stratégies en conditions
        de marché extrêmes (COVID, crash 2022, etc.).

        Args:
            ohlcv_data: Données OHLCV de la période de crise
            strategy_name: Stratégie à tester
            symbol: Paire de trading
            timeframe: Timeframe
            crisis_label: Nom de la crise (pour le logging)

        Returns:
            BacktestResult
        """
        logger.info("Crisis scenario '%s': %s %s", crisis_label, strategy_name, symbol)

        config = BacktestConfig(
            initial_capital=self.config.initial_capital,
            fee_rate=self.config.fee_rate,
            slippage_model="conservative",
            slippage_bps=30,  # Slippage plus élevé en crise
        )

        crisis_engine = BacktestEngine(config=config)
        for name, strat in self._strategies.items():
            crisis_engine.register_strategy(name, strat)

        return await crisis_engine.run(
            ohlcv_data=ohlcv_data,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
        )

    def _get_trend_direction(self, ema_short: float, ema_long: float, price: float) -> str:
        """Détermine la direction de la tendance."""
        if ema_short > ema_long and price > ema_short:
            return "bullish"
        elif ema_short < ema_long and price < ema_short:
            return "bearish"
        return "neutral"

    async def walk_forward_validate(
        self,
        ohlcv_data: list[OHLCV],
        strategy_name: str,
        symbol: str,
        timeframe: str,
        train_size_bars: int = 500,
        test_size_bars: int = 100,
        step_bars: int = 100,
        min_train_bars: int = 200,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> WalkForwardResult:
        """
        Walk-Forward Validation — validation hors-échantillon par fenêtres glissantes.

        Principe :
        1. Diviser les données en fenêtres [train, test] glissantes
        2. Pour chaque fenêtre : entraîner/calibrer sur train, backtest sur test
        3. Agréger les métriques out-of-sample sur toutes les fenêtres
        4. Évaluer la robustesse (stabilité des returns, consistance)

        Cette méthode est le gold standard pour valider qu'une stratégie
        n'est pas overfittée. Les métriques OOS sont le véritable indicateur
        de performance future.

        Args:
            ohlcv_data: Données OHLCV historiques complètes
            strategy_name: Stratégie à valider
            symbol: Paire de trading
            timeframe: Timeframe
            train_size_bars: Nombre de barres par fenêtre d'entraînement
            test_size_bars: Nombre de barres par fenêtre de test
            step_bars: Pas de glissement entre fenêtres
            min_train_bars: Minimum de barres pour la première fenêtre
            progress_callback: Callback (current, total) pour suivi

        Returns:
            WalkForwardResult avec métriques OOS agrégées et diagnostic de robustesse
        """
        if not ohlcv_data:
            raise ValueError("No OHLCV data provided for walk-forward validation")

        strategy = self._strategies.get(strategy_name)
        if not strategy:
            raise ValueError(f"Unknown strategy: '{strategy_name}'. Available: {list(self._strategies.keys())}")

        total_bars = len(ohlcv_data)
        min_required = min_train_bars + test_size_bars
        if total_bars < min_required:
            raise ValueError(
                f"Not enough data for walk-forward: need at least {min_required} bars, "
                f"got {total_bars}"
            )

        # ── 1. Build windows ──
        windows: list[WalkForwardWindow] = []
        window_idx = 0
        train_end = min_train_bars

        while train_end + test_size_bars <= total_bars:
            train_start = max(0, train_end - train_size_bars)
            test_start = train_end
            test_end = min(train_end + test_size_bars, total_bars)

            wf = WalkForwardWindow(
                window_index=window_idx,
                train_start=ohlcv_data[train_start].timestamp,
                train_end=ohlcv_data[train_end - 1].timestamp,
                test_start=ohlcv_data[test_start].timestamp,
                test_end=ohlcv_data[test_end - 1].timestamp,
                train_bars=train_end - train_start,
                test_bars=test_end - test_start,
            )
            windows.append(wf)
            window_idx += 1
            train_end += step_bars

        if not windows:
            raise ValueError("Could not build any walk-forward windows from the provided data")

        total_windows = len(windows)
        logger.info(
            "Walk-forward validation: %s %s | %d windows (train=%d, test=%d, step=%d bars)",
            strategy_name, symbol, total_windows,
            train_size_bars, test_size_bars, step_bars,
        )

        # ── 2. Run backtest on each window ──
        completed = 0
        for idx, wf in enumerate(windows):
            try:
                wf.status = "running"
                if progress_callback:
                    progress_callback(idx + 1, total_windows)

                # Extract window data
                window_data = ohlcv_data[
                    wf.window_index * step_bars :
                    wf.window_index * step_bars + train_size_bars + test_size_bars
                ]
                # Use all data up to test_end for training context,
                # but only evaluate on the test portion
                train_data = ohlcv_data[: wf.window_index * step_bars + train_size_bars]
                test_data = ohlcv_data[
                    wf.window_index * step_bars :
                    wf.window_index * step_bars + train_size_bars + test_size_bars
                ]

                # For proper OOS: use only the test portion
                # Run backtest on the window (train + test for indicator warmup,
                # but results filtered to test period)
                test_start_dt = ohlcv_data[wf.window_index * step_bars + train_size_bars].timestamp

                # Build a config that uses the test portion
                window_config = BacktestConfig(
                    initial_capital=self.config.initial_capital,
                    fee_rate=self.config.fee_rate,
                    slippage_model=self.config.slippage_model,
                    slippage_bps=self.config.slippage_bps,
                    warmup_bars=min(50, len(test_data) - 1),
                    max_positions=self.config.max_positions,
                    risk_free_rate=self.config.risk_free_rate,
                )
                window_engine = BacktestEngine(config=window_config)
                for name, strat in self._strategies.items():
                    window_engine.register_strategy(name, strat)

                result = await window_engine.run(
                    ohlcv_data=test_data,
                    strategy_name=strategy_name,
                    symbol=symbol,
                    timeframe=timeframe,
                )

                # Filter trades and equity to only OOS period
                oos_trades = [t for t in result.trades if t.entry_time >= test_start_dt]
                oos_equity = [e for e in result.equity_curve if e["timestamp"] >= test_start_dt]

                if oos_trades:
                    # Recalculate metrics on OOS trades only
                    oos_metrics = PerformanceMetrics()
                    # Estimate OOS final capital from equity curve
                    oos_final = oos_equity[-1]["equity"] if oos_equity else self.config.initial_capital
                    oos_report = oos_metrics.calculate(
                        initial_capital=self.config.initial_capital,
                        final_capital=oos_final,
                        trades=oos_trades,
                        equity_curve=oos_equity,
                        risk_free_rate=self.config.risk_free_rate,
                    )
                    wf.result = result
                    wf.result.trades = oos_trades
                    wf.result.equity_curve = oos_equity
                    wf.result.total_return_pct = oos_report.total_return_pct
                    wf.result.sharpe_ratio = oos_report.sharpe_ratio
                    wf.result.win_rate = oos_report.win_rate
                else:
                    wf.result = result
                    wf.result.trades = []
                    wf.result.total_return_pct = 0.0

                wf.status = "completed"
                completed += 1

            except Exception as exc:
                logger.error("Walk-forward window %d failed: %s", idx, exc)
                wf.status = "failed"
                wf.error = str(exc)

        # ── 3. Aggregate OOS metrics ──
        completed_windows = [w for w in windows if w.status == "completed" and w.result is not None]
        n_completed = len(completed_windows)

        if n_completed == 0:
            return WalkForwardResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                total_windows=total_windows,
                completed_windows=0,
                windows=windows,
                summary="No windows completed successfully.",
            )

        # Aggregate
        returns = [w.result.total_return_pct for w in completed_windows]
        sharpes = [w.result.sharpe_ratio for w in completed_windows if w.result.sharpe_ratio is not None]
        sortinos = [w.result.sortino_ratio for w in completed_windows if w.result.sortino_ratio is not None]
        drawdowns = [w.result.max_drawdown_pct for w in completed_windows]
        win_rates = [w.result.win_rate for w in completed_windows if w.result.total_trades > 0]
        profit_factors = [w.result.profit_factor for w in completed_windows if w.result.total_trades > 0]
        benchmarks = [w.result.benchmark_return_pct for w in completed_windows]

        avg_return = sum(returns) / n_completed
        avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
        avg_sortino = sum(sortinos) / len(sortinos) if sortinos else 0.0
        avg_drawdown = sum(drawdowns) / n_completed
        avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0.0
        avg_profit_factor = sum(profit_factors) / len(profit_factors) if profit_factors else 0.0
        avg_benchmark = sum(benchmarks) / n_completed

        # Stability: standard deviation of returns
        return_std = float(np.std(returns)) if len(returns) >= 2 else 0.0

        # Consistency: % of positive windows
        positive_windows = sum(1 for r in returns if r > 0)
        consistency = positive_windows / n_completed

        # ── 4. Robustness diagnostics ──
        robustness_issues: list[str] = []
        is_robust = True

        # Check 1: Average Sharpe < 0 → strategy is worse than risk-free
        if avg_sharpe < 0:
            robustness_issues.append("Sharpe ratio OOS négatif — stratégie sous-performante vs risk-free")
            is_robust = False

        # Check 2: Return standard deviation > 2x mean return → unstable
        if return_std > abs(avg_return) * 2 and abs(avg_return) > 0.1:
            robustness_issues.append(
                f"Haute volatilité des returns OOS (σ={return_std:.1f}% vs μ={avg_return:.1f}%)"
            )
            is_robust = False

        # Check 3: Consistency < 50% → more losing than winning windows
        if consistency < 0.50:
            robustness_issues.append(
                f"Moins de 50% de fenêtres positives (consistency={consistency*100:.0f}%)"
            )
            is_robust = False

        # Check 4: Max drawdown > 50% → catastrophic risk
        if avg_drawdown > 50:
            robustness_issues.append(f"Drawdown OOS moyen > 50% ({avg_drawdown:.1f}%)")
            is_robust = False

        # Check 5: Negative alpha vs benchmark
        alpha = avg_return - avg_benchmark
        if alpha < -5:
            robustness_issues.append(
                f"Alpha OOS négatif vs benchmark ({alpha:.1f}% vs buy-and-hold {avg_benchmark:.1f}%)"
            )
            is_robust = False

        # ── 5. Summary ──
        stable = "✓ STABLE" if return_std < abs(avg_return) * 0.5 else "⚠ VOLATILE"
        consistent_label = "✓ CONSISTANT" if consistency >= 0.75 else "⚠ INCONSISTANT"

        summary_lines = [
            f"Walk-Forward Validation: {strategy_name} sur {symbol} ({timeframe})",
            f"Fenêtres: {n_completed}/{total_windows} complétées",
            f"",
            f"Performance Out-of-Sample:",
            f"  Return moyen: {avg_return:+.2f}%  |  Sharpe: {avg_sharpe:.2f}  |  Sortino: {avg_sortino:.2f}",
            f"  Win Rate: {avg_win_rate*100:.0f}%  |  Profit Factor: {avg_profit_factor:.2f}  |  Drawdown: {avg_drawdown:.1f}%",
            f"",
            f"Stabilité:  {stable}  (σ returns = {return_std:.1f}%)",
            f"Consistance: {consistent_label}  ({positive_windows}/{n_completed} fenêtres positives)",
            f"Alpha vs B&H: {alpha:+.1f}%",
            f"",
            f"Verdict: {'ROBUSTE ✓' if is_robust else 'NON ROBUSTE ✗ — voir issues ci-dessous'}",
        ]
        if robustness_issues:
            summary_lines.append("")
            summary_lines.append(f"Issues ({len(robustness_issues)}):")
            for issue in robustness_issues:
                summary_lines.append(f"  ✗ {issue}")

        summary = "\n".join(summary_lines)
        logger.info("Walk-forward complete: robust=%s, consistency=%.0f%%, sharpe=%.2f",
                     is_robust, consistency * 100, avg_sharpe)

        return WalkForwardResult(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            total_windows=total_windows,
            completed_windows=n_completed,
            windows=windows,
            total_return_pct_oos=round(avg_return, 2),
            sharpe_ratio_oos=round(avg_sharpe, 3),
            sortino_ratio_oos=round(avg_sortino, 3),
            max_drawdown_pct_oos=round(avg_drawdown, 2),
            win_rate_oos=round(avg_win_rate, 3),
            profit_factor_oos=round(avg_profit_factor, 2),
            window_returns=[round(r, 2) for r in returns],
            return_std=round(return_std, 2),
            consistency_score=round(consistency, 3),
            benchmark_return_pct_oos=round(avg_benchmark, 2),
            alpha_vs_benchmark=round(alpha, 2),
            is_robust=is_robust,
            robustness_issues=robustness_issues,
            summary=summary,
        )

    # ---------------------------------------------------------------------------
    # Extracted sub-methods from run()
    # ---------------------------------------------------------------------------

    def _initialize_modules(self, _strategy_name: str, _symbol: str) -> None:
        """Initialise les modules de trading pour le backtest."""
        self._exchange = PaperExchange(
            initial_capital=self.config.initial_capital,
            fee_rate=self.config.fee_rate,
            slippage_model=self.config.slippage_model,
        )
        self._portfolio_manager.initialize(self.config.initial_capital)

    def _extract_bar_indicators(
        self, bar: pd.Series, current_price: float, df: pd.DataFrame, i: int
    ) -> dict[str, Any]:
        """Extrait les indicateurs techniques d'une barre OHLCV."""
        indicators: dict[str, Any] = {
            "ema_9": float(bar["ema_9"]) if pd.notna(bar["ema_9"]) else None,
            "ema_21": float(bar["ema_21"]) if pd.notna(bar["ema_21"]) else None,
            "ema_50": float(bar["ema_50"]) if pd.notna(bar["ema_50"]) else None,
            "ema_200": float(bar["ema_200"]) if pd.notna(bar["ema_200"]) else None,
            "rsi_14": float(bar["rsi_14"]) if pd.notna(bar["rsi_14"]) else 50.0,
            "roc_10": float(bar["roc_10"]) if pd.notna(bar["roc_10"]) else 0.0,
            "adx_14": float(bar["adx_14"]) if pd.notna(bar["adx_14"]) else 0.0,
            "bb_upper": float(bar["bb_upper"]) if pd.notna(bar["bb_upper"]) else current_price * 1.05,
            "bb_middle": float(bar["bb_middle"]) if pd.notna(bar["bb_middle"]) else current_price,
            "bb_lower": float(bar["bb_lower"]) if pd.notna(bar["bb_lower"]) else current_price * 0.95,
            "atr_14": float(bar["atr_14"]) if pd.notna(bar["atr_14"]) else current_price * 0.02,
            "supertrend": "bullish" if pd.notna(bar["supertrend"]) and int(bar["supertrend"]) == 1 else "bearish",
            "volume_ratio": float(bar["volume_ratio"]) if pd.notna(bar["volume_ratio"]) else 1.0,
            "stoch_rsi_k": float(bar["stoch_rsi_k"]) if pd.notna(bar["stoch_rsi_k"]) else 50.0,
            "stoch_rsi_d": float(bar["stoch_rsi_d"]) if pd.notna(bar["stoch_rsi_d"]) else 50.0,
            "bb_position": float(bar["bb_position"]) if pd.notna(bar["bb_position"]) else 0.5,
            "mfi_14": float(bar["mfi_14"]) if pd.notna(bar["mfi_14"]) else 50.0,
            "williams_r": float(bar["williams_r"]) if pd.notna(bar["williams_r"]) else -50.0,
        }
        # Support et resistance (Donchian)
        indicators["support"] = (
            float(bar["donchian_lower"]) if pd.notna(bar["donchian_lower"]) else current_price * 0.95
        )
        indicators["resistance"] = (
            float(bar["donchian_upper"]) if pd.notna(bar["donchian_upper"]) else current_price * 1.05
        )
        indicators["current_price"] = current_price
        indicators["price_change_1h"] = (
            float(df["close"].pct_change(periods=min(4, len(df) - 1)).iloc[i]) * 100
            if i > 0 else 0.0
        )
        return indicators

    def _generate_signal(
        self,
        strategy: Any,
        strategy_name: str,
        indicators: dict[str, Any],
        ht_indicators: dict[str, Any],
        current_price: float,
    ) -> Any:
        """Genere le signal de trading a partir de la strategie et des indicateurs."""
        if strategy_name == "trend_following":
            signal = strategy.analyze(
                ema_9=indicators["ema_9"],
                ema_21=indicators["ema_21"],
                ema_50=indicators["ema_50"],
                ema_200=indicators["ema_200"],
                adx=indicators["adx_14"],
                supertrend_direction=indicators["supertrend"],
                current_price=current_price,
            )
        elif strategy_name == "momentum":
            signal = strategy.analyze(
                rsi=indicators["rsi_14"],
                roc=indicators["roc_10"],
                stochastic_rsi=indicators["stoch_rsi_k"],
                volume_ratio=indicators["volume_ratio"],
                current_price=current_price,
                price_change_1h=indicators["price_change_1h"],
            )
        elif strategy_name == "mean_reversion":
            signal = strategy.analyze(
                current_price=current_price,
                bb_upper=indicators["bb_upper"],
                bb_middle=indicators["bb_middle"],
                bb_lower=indicators["bb_lower"],
                rsi=indicators["rsi_14"],
                atr=indicators["atr_14"],
                volume_ratio=indicators["volume_ratio"],
            )
        elif strategy_name == "swing_trading":
            signal = strategy.analyze(
                tf_high_trend=ht_indicators.get("trend", "neutral"),
                tf_high_adx=ht_indicators.get("adx", 0.0),
                tf_high_rsi=ht_indicators.get("rsi", 50.0),
                tf_high_price=ht_indicators.get("price", current_price),
                tf_low_trend=self._get_trend_direction(
                    indicators["ema_9"], indicators["ema_21"], current_price
                ),
                tf_low_rsi=indicators["rsi_14"],
                tf_low_momentum=indicators["roc_10"],
                volume_ratio=indicators["volume_ratio"],
                support=indicators["support"],
                resistance=indicators["resistance"],
                current_price=current_price,
            )
        else:
            # Strategie generique
            try:
                signal = strategy.analyze(**indicators)
            except TypeError:
                signal = strategy.analyze(
                    current_price=current_price,
                    rsi=indicators["rsi_14"],
                    volume_ratio=indicators["volume_ratio"],
                )
        return signal

    async def _close_position(
        self,
        symbol: str,
        trade: BacktestTrade,
        current_price: float,
        current_time: datetime,
        trades: list[BacktestTrade],
        open_trades: dict[str, BacktestTrade],
        i: int,
        warmup: int,
    ) -> bool:
        """Ferme une position existante et retourne True si la fermeture a reussi."""
        order_result = await self._exchange.create_order(
            symbol=symbol,
            side="sell",
            quantity=trade.quantity,
            quantity_usd=0.0,
            order_type="market",
            limit_price=current_price,
            slippage_bps=self.config.slippage_bps,
        )

        if order_result.get("status") == "filled":
            pnl = order_result.get("filled_value_usd", 0) - trade.value_usd
            pnl_pct = (order_result.get("average_price", current_price) / trade.entry_price - 1) * 100
            trade.exit_time = current_time
            trade.exit_price = order_result.get("average_price", current_price)
            trade.pnl = pnl
            trade.pnl_pct = pnl_pct
            trade.holding_bars = i - (trade.holding_bars if isinstance(trade.holding_bars, int) else warmup)
            trades.append(trade)
            del open_trades[symbol]
            return True

        return False

    async def _execute_trade_decision(
        self,
        symbol: str,
        decision: Any,
        current_price: float,
        indicators: dict[str, Any],
        open_trades: dict[str, BacktestTrade],
        strategy_name: str,
        current_time: datetime,
        i: int,
        portfolio_value: float,
        score: float,
        confidence: float,
    ) -> None:
        """Execute une decision d'achat avec validation de risque et creation d'ordre."""
        if decision.action not in (ActionType.STRONG_BUY, ActionType.BUY, ActionType.REINFORCE):
            return

        position_size = decision.order.quantity_usd if decision.order else 0.0
        if position_size <= 0:
            return

        # Valider via RiskManager
        risk = self._risk_manager.assess_trade(
            symbol=symbol,
            side="buy",
            entry_price=current_price,
            portfolio_value=portfolio_value,
            atr=indicators["atr_14"],
            volatility=None,
        )

        if not risk.checks_passed:
            return

        # Executer l'ordre
        order = await self._exchange.create_order(
            symbol=symbol,
            side="buy",
            quantity=0.0,
            quantity_usd=position_size,
            order_type="market",
            limit_price=current_price,
            slippage_bps=self.config.slippage_bps,
        )

        if order.get("status") == "filled":
            trade = BacktestTrade(
                entry_time=current_time,
                symbol=symbol,
                side="buy",
                entry_price=order.get("average_price", current_price),
                quantity=order.get("filled_quantity", 0),
                value_usd=order.get("filled_value_usd", position_size),
                fee=order.get("fee", 0),
                holding_bars=i,
                strategy=strategy_name,
                reason=f"Score: {score:.0f}, Confidence: {confidence:.0f}%",
                action=decision.action.value,
            )
            open_trades[symbol] = trade

            # Assigner au portfolio manager
            current_total = float(self._exchange._cash_reserve) + sum(
                p.value_usd for p in open_trades.values()
            )
            self._portfolio_manager.update_value(current_total, self._exchange._cash_reserve)
            self._portfolio_manager.assign_position(symbol, trade.value_usd)

    def _update_equity_curve(
        self,
        equity_curve: list[dict[str, Any]],
        drawdown_curve: list[dict[str, Any]],
        current_time: datetime,
        open_trades: dict[str, BacktestTrade],
        peak_value: float,
    ) -> float:
        """Met a jour la courbe d'equity et le drawdown."""
        total_value = float(self._exchange._cash_reserve) + sum(
            p.value_usd for p in open_trades.values()
        )
        if total_value > peak_value:
            peak_value = total_value

        drawdown = peak_value - total_value
        drawdown_pct = (drawdown / max(peak_value, 1)) * 100

        equity_curve.append({
            "timestamp": current_time,
            "equity": round(total_value, 2),
            "cash": round(float(self._exchange._cash_reserve), 2),
            "positions_value": round(sum(p.value_usd for p in open_trades.values()), 2),
            "open_positions": len(open_trades),
        })
        drawdown_curve.append({
            "timestamp": current_time,
            "drawdown": round(drawdown, 2),
            "drawdown_pct": round(drawdown_pct, 2),
        })

        return peak_value

    async def _finalize_result(
        self,
        df: pd.DataFrame,
        trades: list[BacktestTrade],
        equity_curve: list[dict[str, Any]],
        drawdown_curve: list[dict[str, Any]],
        end_date: datetime,
        decisions_count: int,
        errors_count: int,
        strategy_name: str,
        symbol: str,
        warmup: int,
        total_bars: int,
        open_trades: dict[str, BacktestTrade],
        start_date: datetime,
        timeframe: str,
    ) -> BacktestResult:
        """Ferme les positions restantes, calcule les metriques et retourne le resultat."""
        if open_trades:
            final_price = float(df["close"].iloc[-1])
            self._exchange.update_price(symbol, final_price)

            for sym, open_trade in list(open_trades.items()):
                order_result = await self._exchange.create_order(
                    symbol=sym,
                    side="sell",
                    quantity=open_trade.quantity,
                    quantity_usd=0.0,
                    order_type="market",
                    limit_price=final_price,
                )

                if order_result.get("status") == "filled":
                    open_trade.exit_time = end_date
                    open_trade.exit_price = order_result.get("average_price", final_price)
                    open_trade.pnl = order_result.get("filled_value_usd", 0) - open_trade.value_usd
                    open_trade.pnl_pct = (open_trade.exit_price / open_trade.entry_price - 1) * 100
                    open_trade.holding_bars = total_bars - warmup
                    trades.append(open_trade)

            open_trades.clear()

        final_balance = await self._exchange.get_balance()
        final_capital = float(final_balance.get("total_equity", self.config.initial_capital))

        metrics = PerformanceMetrics()
        report = metrics.calculate(
            initial_capital=self.config.initial_capital,
            final_capital=final_capital,
            trades=trades,
            equity_curve=equity_curve,
            risk_free_rate=self.config.risk_free_rate,
            trading_days=self.config.trading_days_per_year,
        )

        first_price = float(df["close"].iloc[0])
        benchmark_return = ((float(df["close"].iloc[-1]) - first_price) / max(first_price, 1)) * 100

        result = BacktestResult(
            config=self.config,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            total_bars=total_bars,
            initial_capital=self.config.initial_capital,
            final_capital=report.final_capital,
            total_return=report.total_return,
            total_return_pct=report.total_return_pct,
            cash_remaining=float(self._exchange._cash_reserve),
            total_trades=report.total_trades,
            winning_trades=report.winning_trades,
            losing_trades=report.losing_trades,
            win_rate=report.win_rate,
            avg_win=report.avg_win,
            avg_loss=report.avg_loss,
            largest_win=report.largest_win,
            largest_loss=report.largest_loss,
            avg_holding_bars=report.avg_holding_periods,
            profit_factor=report.profit_factor,
            max_drawdown=report.max_drawdown,
            max_drawdown_pct=report.max_drawdown_pct,
            max_drawdown_peak=report.max_drawdown_peak,
            max_drawdown_valley=report.max_drawdown_valley,
            sharpe_ratio=report.sharpe_ratio,
            sortino_ratio=report.sortino_ratio,
            calmar_ratio=report.calmar_ratio,
            recovery_factor=report.recovery_factor,
            trades=trades,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            benchmark_return_pct=round(benchmark_return, 2),
            alpha=round(report.total_return_pct - benchmark_return, 2),
            decisions_count=decisions_count,
            errors_count=errors_count,
            summary=report.summary,
        )

        logger.info(
            "Backtest complete: %s | return=%.2f%% | Sharpe=%.2f | trades=%d",
            strategy_name, result.total_return_pct, result.sharpe_ratio, result.total_trades,
        )

        return result
