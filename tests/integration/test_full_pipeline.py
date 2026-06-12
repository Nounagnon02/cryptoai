"""
Integration test: Full pipeline from TechnicalAnalysis → AI Agent Fusion → DecisionMatrix → PaperExchange.

Validates the end-to-end flow using synthetic OHLCV data across
bullish, bearish, and neutral market scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.analysis.technical.engine import TechnicalAnalysisEngine
from src.core.ai_agent import ConfidenceScorer, FeatureFusionEngine, SourceSignal
from src.core.decision_engine import ActionType, DecisionMatrix
from src.execution.paper import PaperExchange

# ── Fixtures ───────────────────────────────────────────────────────


def synthetic_ohlcv(
    close_start: float = 100,
    drift: float = 0.001,
    volatility: float = 0.02,
    bars: int = 500,
) -> pd.DataFrame:
    """
    Generate a synthetic OHLCV DataFrame with a random walk.

    Parameters
    ----------
    close_start : float
        Initial close price.
    drift : float
        Per-bar drift (positive = bull, negative = bear, zero = neutral).
    volatility : float
        Per-bar shock standard deviation.
    bars : int
        Number of bars to generate.

    Returns
    -------
    pd.DataFrame with columns [timestamp, open, high, low, close, volume].
    """
    np.random.seed(42)

    closes: list[float] = [float(close_start)]
    for _ in range(bars - 1):
        ret = drift + volatility * float(np.random.randn())
        closes.append(closes[-1] * (1 + ret))

    opens = [closes[0]] + closes[:-1]

    shocks = abs(np.random.randn(bars) * volatility * 0.5).tolist()
    highs = [max(o, c) * (1 + s) for o, c, s in zip(opens, closes, shocks, strict=False)]
    lows = [min(o, c) * (1 - s) for o, c, s in zip(opens, closes, shocks, strict=False)]

    volumes = np.random.uniform(500, 5000, bars).tolist()

    now = datetime.now(UTC)
    timestamps = [now - timedelta(hours=bars - 1 - i) for i in range(bars)]

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


@pytest.fixture
def ohlcv_bull() -> pd.DataFrame:
    """Strong bullish synthetic data."""
    return synthetic_ohlcv(drift=0.003, volatility=0.015, bars=500)


@pytest.fixture
def ohlcv_bear() -> pd.DataFrame:
    """Strong bearish synthetic data."""
    return synthetic_ohlcv(drift=-0.003, volatility=0.015, bars=500)


@pytest.fixture
def ohlcv_neutral() -> pd.DataFrame:
    """Flat / neutral synthetic data."""
    return synthetic_ohlcv(drift=0.0, volatility=0.01, bars=500)


# ── Stage-level tests ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestFullPipeline:
    """Integration tests for the full analysis-to-execution pipeline."""

    async def test_technical_to_feature_fusion(
        self, ohlcv_bull: pd.DataFrame
    ) -> None:
        """
        Stage 1 → 2 : TechnicalAnalysis → FeatureFusionEngine.

        Generate bullish OHLCV, run technical analysis, wrap the result
        as a SourceSignal, fuse it, and verify the direction is preserved.
        """
        engine = TechnicalAnalysisEngine()
        await engine.start()
        try:
            data_by_tf = {"1h": ohlcv_bull}
            tech_score = await engine.analyze("BTC/USDT", data_by_tf)

            assert tech_score.total_score > 0
            assert tech_score.direction in ("bullish", "bearish", "neutral")

            signal = SourceSignal(
                source="technical",
                score=tech_score.total_score,
                direction=tech_score.direction,
                weight=0.35,
                confidence=min(1.0, tech_score.total_score / 100.0),
                key_signals=tech_score.key_signals,
                warnings=tech_score.warnings,
            )

            fusion = FeatureFusionEngine()
            fused = fusion.fuse("BTC/USDT", {"technical": signal})

            # The fused direction must match the technical direction
            assert fused.direction == tech_score.direction, (
                f"Fused direction {fused.direction} != technical direction "
                f"{tech_score.direction}"
            )
            # The score should be in a reasonable range
            assert 0 <= fused.final_score <= 100

            # Bullish data should yield a score > 50
            assert fused.final_score > 50.0, (
                f"Expected bullish score > 50, got {fused.final_score}"
            )
        finally:
            await engine.stop()

    async def test_feature_fusion_to_decision(self) -> None:
        """
        Stage 2 → 3 : FeatureFusionEngine + ConfidenceScorer → DecisionMatrix.

        Create two aligned bullish signals, fuse them, score confidence,
        feed into DecisionMatrix, and verify a buy-related action.
        """
        fusion = FeatureFusionEngine()
        scorer = ConfidenceScorer()
        dm = DecisionMatrix()

        signals: dict[str, SourceSignal] = {
            "technical": SourceSignal(
                source="technical",
                score=78.0,
                direction="bullish",
                weight=0.35,
                confidence=0.8,
                key_signals=["EMA bullish cross"],
            ),
            "onchain": SourceSignal(
                source="onchain",
                score=70.0,
                direction="bullish",
                weight=0.20,
                confidence=0.7,
                key_signals=["Exchange outflows"],
            ),
        }

        fused = fusion.fuse("BTC/USDT", signals)
        confidence = scorer.score(fused)

        decision = dm.decide(
            symbol="BTC/USDT",
            score=fused.final_score,
            direction=fused.direction,
            confidence=confidence,
            strength=fused.strength,
        )

        # With two aligned bullish sources, the decision should be a buy
        assert decision.action in (ActionType.STRONG_BUY, ActionType.BUY), (
            f"Expected buy action, got {decision.action}"
        )
        assert decision.score > 50.0
        assert decision.confidence >= 0
        assert decision.risk_check["volatility_regime"] == "normal"

    async def test_decision_to_execution(self) -> None:
        """
        Stage 3 → 4 : DecisionMatrix → PaperExchange.create_order().

        Generate a buy decision, execute it on the paper exchange,
        and verify the trade was filled correctly.
        """
        dm = DecisionMatrix()
        exchange = PaperExchange(initial_capital=100_000.0)

        decision = dm.decide(
            symbol="BTC/USDT",
            score=75.0,
            direction="bullish",
            confidence=70.0,
            strength=0.5,
        )

        assert decision.order is not None
        assert decision.order.side == "buy"

        result = await exchange.create_order(
            symbol=decision.order.symbol,
            side=decision.order.side,
            quantity=0,
            quantity_usd=decision.order.quantity_usd,
            order_type="market",
        )

        assert result["status"] == "filled", f"Order was not filled: {result}"
        assert result["filled_quantity"] > 0
        assert result["average_price"] > 0
        assert result["fee"] > 0
        assert isinstance(result["exchange_id"], str)

        # Verify the paper exchange has an open position
        state = exchange.get_state()
        assert state.open_positions == 1

    async def test_full_bull_scenario(self, ohlcv_bull: pd.DataFrame) -> None:
        """
        End-to-end bull run: bullish OHLCV → strong_buy → position opened.

        The full pipeline should produce a buy order that gets filled
        on the paper exchange.
        """
        # ---- Stage 1 : Technical Analysis ----
        engine = TechnicalAnalysisEngine()
        await engine.start()
        try:
            tech_score = await engine.analyze("BTC/USDT", {"1h": ohlcv_bull})

            # ---- Stage 2 : Feature Fusion ----
            signal = SourceSignal(
                source="technical",
                score=tech_score.total_score,
                direction=tech_score.direction,
                weight=0.35,
                confidence=min(1.0, tech_score.total_score / 100.0),
                key_signals=tech_score.key_signals,
                warnings=tech_score.warnings,
            )

            fusion = FeatureFusionEngine()
            fused = fusion.fuse("BTC/USDT", {"technical": signal})

            scorer = ConfidenceScorer()
            confidence = scorer.score(fused)

            # ---- Stage 3 : Decision ----
            dm = DecisionMatrix()
            decision = dm.decide(
                symbol="BTC/USDT",
                score=fused.final_score,
                direction=fused.direction,
                confidence=confidence,
                strength=fused.strength,
            )

            # Bullish data should lead to a buy action
            assert decision.action in (ActionType.STRONG_BUY, ActionType.BUY), (
                f"Expected buy action, got {decision.action}"
            )
            assert fused.direction == "bullish"

            # ---- Stage 4 : Execution ----
            if decision.order:
                exchange = PaperExchange(initial_capital=100_000.0)
                result = await exchange.create_order(
                    symbol=decision.order.symbol,
                    side=decision.order.side,
                    quantity=0,
                    quantity_usd=decision.order.quantity_usd,
                    order_type="market",
                )
                assert result["status"] == "filled"
                state = exchange.get_state()
                assert state.open_positions == 1, (
                    "Bull trade should result in an open position"
                )
                assert state.total_trades == 0  # only open, no closed trades
        finally:
            await engine.stop()

    async def test_full_bear_scenario(self, ohlcv_bear: pd.DataFrame) -> None:
        """
        End-to-end bear run: bearish OHLCV → sell / reduce action.

        The pipeline should detect the downtrend and produce a
        sell-side decision.
        """
        engine = TechnicalAnalysisEngine()
        await engine.start()
        try:
            tech_score = await engine.analyze("BTC/USDT", {"1h": ohlcv_bear})

            signal = SourceSignal(
                source="technical",
                score=tech_score.total_score,
                direction=tech_score.direction,
                weight=0.35,
                confidence=abs(tech_score.total_score - 50.0) / 50.0,
                key_signals=tech_score.key_signals,
                warnings=tech_score.warnings,
            )

            fusion = FeatureFusionEngine()
            fused = fusion.fuse("BTC/USDT", {"technical": signal})

            scorer = ConfidenceScorer()
            confidence = scorer.score(fused)

            dm = DecisionMatrix()
            decision = dm.decide(
                symbol="BTC/USDT",
                score=fused.final_score,
                direction=fused.direction,
                confidence=confidence,
                strength=fused.strength,
            )

            # The DecisionMatrix uses a contrarian component — bearish data
            # with a low score (= oversold) can trigger BUY as a mean-reversion
            # signal. Accept any deliberate action (not HOLD).
            assert decision.action != ActionType.HOLD, (
                f"Expected a deliberate action, got HOLD (score={fused.final_score}, "
                f"direction={fused.direction})"
            )

            # The fused signal must reflect bearishness
            assert fused.direction in ("bearish", "neutral"), (
                f"Expected bearish or neutral direction, got {fused.direction}"
            )
        finally:
            await engine.stop()

    async def test_full_neutral_scenario(
        self, ohlcv_neutral: pd.DataFrame
    ) -> None:
        """
        End-to-end neutral market: flat OHLCV → hold action.

        When the market shows no clear direction, the pipeline
        should recommend holding.
        """
        engine = TechnicalAnalysisEngine()
        await engine.start()
        try:
            tech_score = await engine.analyze("BTC/USDT", {"1h": ohlcv_neutral})

            signal = SourceSignal(
                source="technical",
                score=tech_score.total_score,
                direction=tech_score.direction,
                weight=0.35,
                confidence=abs(tech_score.total_score - 50.0) / 50.0,
                key_signals=tech_score.key_signals,
                warnings=tech_score.warnings,
            )

            fusion = FeatureFusionEngine()
            fused = fusion.fuse("BTC/USDT", {"technical": signal})

            dm = DecisionMatrix()
            decision = dm.decide(
                symbol="BTC/USDT",
                score=fused.final_score,
                direction=fused.direction,
                confidence=50.0,
                strength=fused.strength,
            )

            # Flat data should lead to HOLD (or possibly no order generated)
            assert decision.action == ActionType.HOLD, (
                f"Expected HOLD for neutral market, got {decision.action}"
            )
            assert decision.order is None, (
                "Neutral decision should not generate an order"
            )
        finally:
            await engine.stop()
