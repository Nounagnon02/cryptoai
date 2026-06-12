"""
Integration test: Multi-source feature fusion and confidence scoring.

Validates how FeatureFusionEngine combines signals from different
analysis sources (technical, onchain, orderbook, social, news)
and how ConfidenceScorer rates the resulting fused signal.
"""

from __future__ import annotations

import pytest

from src.core.ai_agent import (
    ConfidenceScorer,
    FeatureFusionEngine,
    FusedSignal,
    SourceSignal,
)

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def fusion_engine() -> FeatureFusionEngine:
    """A FeatureFusionEngine with default weights."""
    return FeatureFusionEngine()


@pytest.fixture
def confidence_scorer() -> ConfidenceScorer:
    """A ConfidenceScorer for scoring fused signals."""
    return ConfidenceScorer()


@pytest.fixture
def bullish_technical() -> SourceSignal:
    return SourceSignal(
        source="technical",
        score=78.0,
        direction="bullish",
        weight=0.35,
        confidence=0.85,
        key_signals=["RSI bullish divergence", "MACD cross up"],
    )


@pytest.fixture
def bullish_onchain() -> SourceSignal:
    return SourceSignal(
        source="onchain",
        score=72.0,
        direction="bullish",
        weight=0.20,
        confidence=0.75,
        key_signals=["Exchange net outflow", "Whale accumulation"],
    )


@pytest.fixture
def bullish_orderbook() -> SourceSignal:
    return SourceSignal(
        source="orderbook",
        score=68.0,
        direction="bullish",
        weight=0.15,
        confidence=0.70,
        key_signals=["Bid wall increasing"],
    )


@pytest.fixture
def bullish_news() -> SourceSignal:
    return SourceSignal(
        source="news",
        score=65.0,
        direction="bullish",
        weight=0.15,
        confidence=0.60,
        key_signals=["Positive regulatory development"],
    )


@pytest.fixture
def bullish_social() -> SourceSignal:
    return SourceSignal(
        source="social",
        score=62.0,
        direction="bullish",
        weight=0.15,
        confidence=0.55,
        key_signals=["Rising social volume"],
    )


@pytest.fixture
def bearish_onchain() -> SourceSignal:
    return SourceSignal(
        source="onchain",
        score=28.0,
        direction="bearish",
        weight=0.20,
        confidence=0.80,
        key_signals=["Exchange inflows spike"],
        warnings=["Large transfer to exchange"],
    )


@pytest.fixture
def bearish_news() -> SourceSignal:
    return SourceSignal(
        source="news",
        score=25.0,
        direction="bearish",
        weight=0.15,
        confidence=0.70,
        key_signals=["Negative regulatory news"],
        warnings=["Potential crackdown"],
    )


# ── Tests ──────────────────────────────────────────────────────────


class TestMultiSourceFusion:
    """Multi-source signal fusion and confidence scoring."""

    def test_technical_and_onchain_bullish(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
        bullish_onchain: SourceSignal,
    ) -> None:
        """Two aligned bullish sources → final direction is bullish."""
        signals = {
            "technical": bullish_technical,
            "onchain": bullish_onchain,
        }

        fused = fusion_engine.fuse(symbol="BTC/USDT", signals=signals)

        assert fused.direction == "bullish"
        assert fused.final_score > 60.0
        assert fused.divergence_detected is False
        assert fused.consensus_level == "unanimous"

        # Both sources should appear in the output
        assert "technical" in fused.source_signals
        assert "onchain" in fused.source_signals

    def test_three_sources_strong_consensus(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
        bullish_onchain: SourceSignal,
        bullish_orderbook: SourceSignal,
    ) -> None:
        """Three aligned sources produce strong or unanimous consensus."""
        signals = {
            "technical": bullish_technical,
            "onchain": bullish_onchain,
            "orderbook": bullish_orderbook,
        }

        fused = fusion_engine.fuse(symbol="BTC/USDT", signals=signals)

        assert fused.direction == "bullish"
        assert fused.consensus_level in ("strong", "unanimous")
        assert fused.final_score > 65.0
        assert fused.confidence > 0.0

        # Reasoning should mention the number of supporting sources
        assert any("3 source" in r for r in fused.reasoning) or any(
            "support" in r.lower() for r in fused.reasoning
        )

    def test_divergent_signals(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
        bearish_onchain: SourceSignal,
    ) -> None:
        """
        When signals disagree (technical=bull, onchain=bear),
        divergence is detected and confidence is reduced.
        """
        signals = {
            "technical": bullish_technical,
            "onchain": bearish_onchain,
        }

        fused = fusion_engine.fuse(symbol="ETH/USDT", signals=signals)

        assert fused.divergence_detected is True, (
            "Divergence should be detected with conflicting directions"
        )
        assert fused.consensus_level in ("low", "moderate")

        # Score should be moderated — somewhere between the two
        assert 30 < fused.final_score < 70

        # Risks should include the divergence warning
        risk_texts = [r.lower() for r in fused.risks]
        assert any("divergen" in r for r in risk_texts), (
            "Risks should mention the divergence"
        )

        # Confidence should be penalised for divergence
        assert fused.confidence < 0.7, (
            "Confidence should be reduced due to divergence"
        )

    def test_single_source(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
    ) -> None:
        """A single source still works correctly with fallback weights."""
        signals = {"technical": bullish_technical}

        fused = fusion_engine.fuse(symbol="BTC/USDT", signals=signals)

        assert fused.direction == "bullish"
        assert fused.final_score > 60.0
        assert fused.consensus_level == "unanimous"
        assert fused.divergence_detected is False

        # Only the technical source should appear
        assert len(fused.source_signals) == 1
        assert "technical" in fused.source_signals

        # Reasoning should be coherent for a single source
        assert len(fused.reasoning) > 0

    def test_empty_signals(self, fusion_engine: FeatureFusionEngine) -> None:
        """Empty signals produce a neutral fallback with zero confidence."""
        fused = fusion_engine.fuse(symbol="BTC/USDT", signals={})

        assert fused.final_score == 50.0, (
            f"Expected score 50 for empty signals, got {fused.final_score}"
        )
        assert fused.direction == "neutral"
        assert fused.confidence == 0.0
        assert fused.strength == 0.0
        assert len(fused.reasoning) > 0
        assert "aucun signal" in fused.reasoning[0].lower() or \
               "no signal" in fused.reasoning[0].lower()

    def test_five_sources_full_consensus(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
        bullish_onchain: SourceSignal,
        bullish_orderbook: SourceSignal,
        bullish_news: SourceSignal,
        bullish_social: SourceSignal,
    ) -> None:
        """All five sources aligned → unanimous consensus + high score."""
        signals = {
            "technical": bullish_technical,
            "onchain": bullish_onchain,
            "orderbook": bullish_orderbook,
            "news": bullish_news,
            "social": bullish_social,
        }

        fused = fusion_engine.fuse(symbol="BTC/USDT", signals=signals)

        assert fused.direction == "bullish"
        assert fused.consensus_level == "unanimous"
        assert fused.divergence_detected is False
        assert fused.final_score > 60.0

        # All five sources should be present in the output
        assert len(fused.source_signals) == 5
        for src in ("technical", "onchain", "orderbook", "news", "social"):
            assert src in fused.source_signals, f"Missing source: {src}"

    def test_weights_preserved_in_output(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
        bullish_onchain: SourceSignal,
    ) -> None:
        """The weights_used dict should reflect the weights applied."""
        signals = {
            "technical": bullish_technical,
            "onchain": bullish_onchain,
        }

        fused = fusion_engine.fuse(symbol="BTC/USDT", signals=signals)

        assert "technical" in fused.weights_used
        assert "onchain" in fused.weights_used

        # Weights_used stores the raw (pre-normalization) weights
        assert fused.weights_used["technical"] == 0.35
        assert fused.weights_used["onchain"] == 0.20

    def test_custom_weights(
        self,
        fusion_engine: FeatureFusionEngine,
        bullish_technical: SourceSignal,
        bearish_onchain: SourceSignal,
    ) -> None:
        """
        Custom dynamic weights override the defaults and are
        reflected in the output and the final score.
        """
        signals = {
            "technical": bullish_technical,
            "onchain": bearish_onchain,
        }

        # Override: heavily favour the bullish technical source
        custom_weights = {"technical": 0.9, "onchain": 0.1}

        fused = fusion_engine.fuse(
            symbol="BTC/USDT",
            signals=signals,
            dynamic_weights=custom_weights,
        )

        # Because technical (78, bullish) dominates with 0.9 weight,
        # the final direction should be bullish despite bearish onchain
        assert fused.direction == "bullish", (
            "Technical at 90% weight should override bearish onchain"
        )

        # The weights used should match the custom input
        for src, w in custom_weights.items():
            if src in fused.weights_used:
                assert fused.weights_used[src] == pytest.approx(w / sum(custom_weights.values()), rel=0.05), (
                    f"Weight for {src} should reflect custom_weights"
                )


class TestConfidenceScoring:
    """ConfidenceScorer integration with fused signals."""

    def test_confidence_high_consensus(
        self,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """All sources agree → high confidence score."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=80.0,
            direction="bullish",
            confidence=0.85,
            strength=0.6,
            consensus_level="unanimous",
            divergence_detected=False,
            risks=[],
        )

        score = confidence_scorer.score(fused)

        # Unanimous (+20) + strength 0.6*15=+9 + confidence 0.85*15=+12.75
        # = 50 + 20 + 9 + 12.75 = 91.75
        assert score > 70, f"Expected high confidence, got {score}"
        assert score <= 100

    def test_confidence_low_consensus(
        self,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """Divergent signals → lower confidence score."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=50.0,
            direction="neutral",
            confidence=0.4,
            strength=0.1,
            consensus_level="low",
            divergence_detected=True,
            risks=["Divergence between sources", "Low volume on signal"],
        )

        score = confidence_scorer.score(fused)

        # Base 50 -10(low) + 0.1*15=+1.5 + 0.4*15=+6 -15(divergence) -2*5(risks)
        # = 50 - 10 + 1.5 + 6 - 15 - 10 = 22.5
        # Neutral direction → min(22.5, 30) = 22.5
        assert score <= 40, f"Expected low confidence, got {score}"
        assert score >= 0

    def test_confidence_maximum(
        self,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """Perfect conditions → score capped at 100."""
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

        # 50 + 20 + 15 + 15 = 100 (capped)
        assert score == 100.0

    def test_confidence_minimum(
        self,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """Terrible conditions → floor at 0."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=0.0,
            direction="bearish",
            confidence=0.0,
            strength=0.0,
            consensus_level="low",
            divergence_detected=True,
            risks=["a", "b", "c", "d"],  # many risks
        )

        score = confidence_scorer.score(fused)

        # 50 - 10 + 0 + 0 - 15 - 20 = 5 (not 0, but single digits)
        # Actually: 50 - 10(low) + 0 + 0 - 15(divergence) - 4*5(risks) = 50-10-15-20 = 5
        assert 0 <= score <= 10

    def test_confidence_neutral_direction_capped(
        self,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """Neutral direction caps confidence at 30."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=50.0,
            direction="neutral",
            confidence=1.0,
            strength=0.0,
            consensus_level="unanimous",
            divergence_detected=False,
            risks=[],
        )

        score = confidence_scorer.score(fused)

        # 50 + 20 + 0 + 15 = 85, but neutral → min(85, 30) = 30
        assert score == 30, (
            f"Expected 30 for neutral cap, got {score}"
        )

    def test_confidence_reproducible(
        self,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """Same input always produces the same output (deterministic)."""
        fused = FusedSignal(
            symbol="BTC/USDT",
            final_score=72.0,
            direction="bullish",
            confidence=0.7,
            strength=0.44,
            consensus_level="strong",
            divergence_detected=False,
            risks=["Moderate volatility"],
        )

        score1 = confidence_scorer.score(fused)
        score2 = confidence_scorer.score(fused)

        assert score1 == score2
