"""Tests for AI Agent (FeatureFusionEngine, ConfidenceScorer, AIExplanationEngine)."""
from __future__ import annotations

import pytest

from src.core.ai_agent import (
    AIExplanationEngine,
    CentralAIAgent,
    ConfidenceScorer,
    FeatureFusionEngine,
    FusedSignal,
    SourceSignal,
)


@pytest.fixture
def fusion_engine() -> FeatureFusionEngine:
    return FeatureFusionEngine()


@pytest.fixture
def confidence_scorer() -> ConfidenceScorer:
    return ConfidenceScorer()


@pytest.fixture
def explanation_engine() -> AIExplanationEngine:
    return AIExplanationEngine()


@pytest.fixture
def central_agent() -> CentralAIAgent:
    return CentralAIAgent()


@pytest.fixture
def bullish_signals() -> dict:
    """Signals indicating a bullish consensus."""
    return {
        "technical": SourceSignal(
            source="technical",
            score=72.0,
            direction="bullish",
            weight=0.35,
            confidence=0.8,
            key_signals=["RSI oversold bounce", "MACD bullish cross"],
        ),
        "onchain": SourceSignal(
            source="onchain",
            score=65.0,
            direction="bullish",
            weight=0.20,
            confidence=0.7,
            key_signals=["Exchange outflows increasing"],
        ),
        "orderbook": SourceSignal(
            source="orderbook",
            score=55.0,
            direction="neutral",
            weight=0.15,
            confidence=0.5,
        ),
    }


@pytest.fixture
def divergent_signals() -> dict:
    """Signals with conflicting directions."""
    return {
        "technical": SourceSignal(
            source="technical",
            score=75.0,
            direction="bullish",
            weight=0.35,
            confidence=0.8,
        ),
        "news": SourceSignal(
            source="news",
            score=30.0,
            direction="bearish",
            weight=0.15,
            confidence=0.7,
            warnings=["Negative regulatory news"],
        ),
    }


class TestFeatureFusionEngine:
    """Tests for FeatureFusionEngine.fuse()."""

    def test_fuse_with_empty_data(self, fusion_engine: FeatureFusionEngine) -> None:
        """Test fusion returns neutral signal when no data provided."""
        result = fusion_engine.fuse(symbol="BTC/USDT", signals={})
        assert result.symbol == "BTC/USDT"
        assert result.final_score == 50.0
        assert result.direction == "neutral"
        assert result.confidence == 0.0
        assert result.strength == 0.0
        assert "Aucun signal disponible" in result.reasoning

    def test_fuse_with_all_sources(
        self, fusion_engine: FeatureFusionEngine, bullish_signals: dict
    ) -> None:
        """Test fusion with multiple bullish sources."""
        result = fusion_engine.fuse(symbol="BTC/USDT", signals=bullish_signals)
        assert result.symbol == "BTC/USDT"
        assert result.direction == "bullish"
        assert result.final_score > 50.0
        assert result.confidence > 0
        assert result.strength > 0
        assert result.divergence_detected is False
        assert result.consensus_level == "unanimous"

    def test_fuse_detects_divergence(
        self, fusion_engine: FeatureFusionEngine, divergent_signals: dict
    ) -> None:
        """Test fusion detects divergence between sources."""
        result = fusion_engine.fuse(symbol="ETH/USDT", signals=divergent_signals)
        assert result.divergence_detected is True
        assert result.consensus_level in ("low", "moderate")
        assert any("divergen" in r.lower() for r in result.risks)

    def test_fuse_with_dynamic_weights(
        self, fusion_engine: FeatureFusionEngine, bullish_signals: dict
    ) -> None:
        """Test fusion uses dynamic weights when provided."""
        dynamic_weights = {"technical": 0.8, "onchain": 0.1, "orderbook": 0.1}
        result = fusion_engine.fuse(
            symbol="BTC/USDT", signals=bullish_signals, dynamic_weights=dynamic_weights
        )
        # Technical has highest weight, should dominate
        assert result.final_score > 60.0
        assert "technical" in result.weights_used

    def test_fuse_empty_signals_list(self, fusion_engine: FeatureFusionEngine) -> None:
        """Test fusion with None as signals dict."""
        result = fusion_engine.fuse(symbol="BTC/USDT", signals={})
        assert result.direction == "neutral"
        assert result.final_score == 50.0


class TestConfidenceScorer:
    """Tests for ConfidenceScorer.compute()."""

    def test_confidence_with_unanimous_consensus(
        self, confidence_scorer: ConfidenceScorer
    ) -> None:
        """Test high confidence with unanimous consensus."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=75.0,
            direction="bullish",
            confidence=0.8,
            strength=0.5,
            consensus_level="unanimous",
            divergence_detected=False,
            risks=[],
        )
        score = confidence_scorer.score(fused)
        # Unanimous gives +20, strength 0.5*15=+7.5, confidence 0.8*15=+12
        # Base 50 + 20 + 7.5 + 12 = ~89.5 → capped at 100
        assert 80 <= score <= 100

    def test_confidence_with_divergence(
        self, confidence_scorer: ConfidenceScorer
    ) -> None:
        """Test lower confidence with divergence."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=55.0,
            direction="neutral",
            confidence=0.4,
            strength=0.1,
            consensus_level="low",
            divergence_detected=True,
            risks=["Divergence between sources"],
        )
        score = confidence_scorer.score(fused)
        assert 0 <= score < 50  # Should be penalized

    def test_confidence_score_bounds(
        self, confidence_scorer: ConfidenceScorer
    ) -> None:
        """Test confidence score stays within 0-100 bounds."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=100.0,
            direction="bullish",
            confidence=1.0,
            strength=1.0,
            consensus_level="unanimous",
            divergence_detected=False,
            risks=[],
        )
        score = confidence_scorer.score(fused)
        assert 0 <= score <= 100

    def test_confidence_neutral_capped(
        self, confidence_scorer: ConfidenceScorer
    ) -> None:
        """Test confidence is capped at 30 for neutral direction."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=50.0,
            direction="neutral",
            confidence=0.9,
            strength=0.0,
            consensus_level="unanimous",
            divergence_detected=False,
            risks=[],
        )
        score = confidence_scorer.score(fused)
        assert score <= 30


class TestAIExplanationEngine:
    """Tests for AIExplanationEngine.explain()."""

    def test_explain_decision(
        self, explanation_engine: AIExplanationEngine, bullish_signals: dict
    ) -> None:
        """Test explanation generation for a decision."""
        # Build a fused signal manually
        engine = FeatureFusionEngine()
        fused = engine.fuse(symbol="BTC/USDT", signals=bullish_signals)
        explanation = explanation_engine.explain_decision(
            symbol="BTC/USDT",
            fused=fused,
            confidence=75.0,
            action="buy",
        )
        assert isinstance(explanation, str)
        assert "BTC/USDT" in explanation
        assert "BUY" in explanation or "buy" in explanation
        assert "Score" in explanation
        assert "technical" in explanation.lower()

    def test_explain_with_no_signals(
        self, explanation_engine: AIExplanationEngine
    ) -> None:
        """Test explanation when there are no source signals."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=50.0,
            direction="neutral",
            confidence=0.0,
            strength=0.0,
        )
        explanation = explanation_engine.explain_decision(
            symbol="BTC/USDT",
            fused=fused,
            confidence=0.0,
            action="hold",
        )
        assert isinstance(explanation, str)
        assert "BTC/USDT" in explanation


class TestCentralAIAgent:
    """Tests for CentralAIAgent."""

    @pytest.mark.asyncio
    async def test_start_stop(self, central_agent: CentralAIAgent) -> None:
        """Test agent start and stop."""
        assert central_agent.is_running is False
        await central_agent.start()
        assert central_agent.is_running is True
        await central_agent.stop()
        assert central_agent.is_running is False

    def test_analyze(
        self, central_agent: CentralAIAgent, bullish_signals: dict
    ) -> None:
        """Test full analysis pipeline."""
        result = central_agent.analyze(symbol="BTC/USDT", signals=bullish_signals)
        assert result["symbol"] == "BTC/USDT"
        assert result["score"] > 50.0
        assert result["direction"] == "bullish"
        assert result["confidence"] > 0
        assert "explanation" in result
        assert len(result["reasoning"]) > 0
        assert result["action"] in ("buy", "strong_buy")

    def test_get_last_decision(
        self, central_agent: CentralAIAgent, bullish_signals: dict
    ) -> None:
        """Test retrieving last decision for a symbol."""
        central_agent.analyze(symbol="BTC/USDT", signals=bullish_signals)
        decision = central_agent.get_last_decision("BTC/USDT")
        assert decision is not None
        assert decision["symbol"] == "BTC/USDT"

    def test_get_statistics(
        self, central_agent: CentralAIAgent, bullish_signals: dict
    ) -> None:
        """Test statistics tracking."""
        central_agent.analyze(symbol="BTC/USDT", signals=bullish_signals)
        central_agent.analyze(symbol="ETH/USDT", signals=bullish_signals)
        stats = central_agent.get_statistics()
        assert stats["total_decisions"] == 2
        assert stats["symbols_tracked"] == 2
