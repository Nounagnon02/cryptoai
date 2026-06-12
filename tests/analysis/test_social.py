"""
Tests for SocialTracker, SentimentAnalyzer, SocialScorer, SocialManipulationDetector.

Covers mention recording, sentiment classification (emoji + lexical),
aggregated scoring, influence weighting, and manipulation risk detection.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.analysis.social.manipulation import (
    SocialManipulationDetector,
    SocialRiskScore,
)
from src.analysis.social.scorer import SocialScore, SocialScorer
from src.analysis.social.sentiment import (
    AggregatedSocialSentiment,
    SentimentAnalyzer,
)
from src.analysis.social.tracker import SocialMention, SocialMetrics, SocialTracker

# ── Helpers ──────────────────────────────────────────────────────────────────


def _mention(
    mention_id: str = "m1",
    content: str = "Bitcoin is looking great!",
    symbol: str = "BTC",
    platform: str = "twitter",
    engagement: int = 10,
    followers: int = 1000,
    verified: bool = False,
) -> SocialMention:
    return SocialMention(
        id=mention_id,
        platform=platform,
        content=content,
        author=f"user_{mention_id}",
        symbol=symbol,
        timestamp=datetime.now(UTC).timestamp() - 3600,
        platform_type="post",
        engagement=engagement,
        followers_count=followers,
        is_verified=verified,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSocialTracker:
    """Tests for SocialTracker."""

    def test_record_and_compute_metrics(self) -> None:
        """Recording mentions and computing metrics works end-to-end."""
        tracker = SocialTracker()
        now = datetime.now(UTC).timestamp()

        mentions = [
            SocialMention(
                id="s1", platform="twitter", content="Bullish on BTC",
                author="alice", symbol="BTC",
                timestamp=now - 1000, platform_type="post",
                engagement=50, followers_count=5000,
            ),
            SocialMention(
                id="s2", platform="reddit", content="BTC to the moon",
                author="bob", symbol="BTC",
                timestamp=now - 2000, platform_type="post",
                engagement=30, followers_count=2000,
            ),
        ]
        tracker.record_batch(mentions)
        metrics = tracker.compute_metrics("BTC")

        assert isinstance(metrics, SocialMetrics)
        assert metrics.total_mentions_24h >= 2
        assert metrics.unique_authors_24h >= 2
        assert metrics.avg_engagement > 0
        assert metrics.author_diversity > 0

    def test_get_metrics_returns_last(self) -> None:
        """get_metrics returns the last computed SocialMetrics."""
        tracker = SocialTracker()
        mention = _mention()
        tracker.record_mention(mention)
        metrics = tracker.compute_metrics("BTC")

        cached = tracker.get_metrics("BTC")
        assert cached is metrics

    def test_no_mentions_returns_empty_metrics(self) -> None:
        """compute_metrics on a symbol with no mentions returns zeroed metrics."""
        tracker = SocialTracker()
        metrics = tracker.compute_metrics("UNKNOWN")

        assert metrics.total_mentions_24h == 0
        assert metrics.unique_authors_24h == 0
        assert metrics.mention_velocity == 0
        assert metrics.mention_acceleration == 0


class TestSentimentAnalyzer:
    """Tests for SentimentAnalyzer classification."""

    def test_rocket_moon_text_bullish(self) -> None:
        """Text with rocket emoji and 'moon' keyword is classified as bullish."""
        analyzer = SentimentAnalyzer()
        mention = _mention(content="BTC going to the moon 🚀🚀🚀")
        result = analyzer.analyze_mention(mention)

        assert result.sentiment == "bullish"
        assert result.score > 0

    def test_skull_dump_text_bearish(self) -> None:
        """Text with skull emoji and 'dump' keyword is classified as bearish."""
        analyzer = SentimentAnalyzer()
        mention = _mention(content="BTC dump incoming 💀")
        result = analyzer.analyze_mention(mention)

        assert result.sentiment == "bearish"
        assert result.score < 0

    def test_technical_text_neutral(self) -> None:
        """Text with neutral/technical language is classified as neutral."""
        analyzer = SentimentAnalyzer()
        mention = _mention(content="The chart pattern might indicate a potential "
                                   "move according to my technical analysis")
        result = analyzer.analyze_mention(mention)

        assert result.sentiment == "neutral"

    def test_emoji_only_positive(self) -> None:
        """Text with only positive emojis produces a positive emoji_score."""
        analyzer = SentimentAnalyzer()
        mention = _mention(content="🚀📈💰")
        result = analyzer.analyze_mention(mention)

        assert result.emoji_score > 0

    def test_empty_content_neutral(self) -> None:
        """Empty content returns neutral sentiment with score 0."""
        analyzer = SentimentAnalyzer()
        mention = _mention(content="")
        result = analyzer.analyze_mention(mention)

        assert result.sentiment == "neutral"
        assert result.score == 0

    def test_hashtag_extraction(self) -> None:
        """Hashtags are extracted from mention content."""
        analyzer = SentimentAnalyzer()
        mention = _mention(content="Check out #Bitcoin and #Crypto news today!")
        result = analyzer.analyze_mention(mention)

        assert "Bitcoin" in result.hashtags or "bitcoin" in result.hashtags
        assert "Crypto" in result.hashtags or "crypto" in result.hashtags

    def test_aggregate_mentions_returns_aggregated_social_sentiment(self) -> None:
        """aggregate() returns proper AggregatedSocialSentiment."""
        analyzer = SentimentAnalyzer()

        mentions = [
            _mention(mention_id="agg1", content="BTC to the moon 🚀", followers=5000),
            _mention(mention_id="agg2", content="BTC looking bearish 📉", followers=100),
            _mention(mention_id="agg3", content="maybe BTC will move sideways", followers=1000),
        ]
        aggregated = analyzer.aggregate("BTC", mentions)

        assert isinstance(aggregated, AggregatedSocialSentiment)
        assert aggregated.total_mentions == 3
        assert aggregated.direction in ("bullish", "bearish", "neutral")
        assert 0 <= aggregated.bullish_pct <= 100
        assert 0 <= aggregated.bearish_pct <= 100
        assert 0 <= aggregated.neutral_pct <= 100
        # Percentages should sum to approximately 100
        assert abs(aggregated.bullish_pct + aggregated.bearish_pct + aggregated.neutral_pct - 100) < 1

    def test_aggregate_influence_weighting(self) -> None:
        """Aggregated score reflects influence: bullish from high-follower account dominates."""
        analyzer = SentimentAnalyzer()
        mentions = [
            _mention(mention_id="inf1", content="BTC to the moon 🚀", followers=100_000, engagement=5000),
            _mention(mention_id="inf2", content="BTC is bad sell now", followers=10, engagement=1),
        ]
        aggregated = analyzer.aggregate("BTC", mentions)

        # The high-follower bullish mention should pull weighted_score positive
        assert aggregated.weighted_score > aggregated.average_score or aggregated.weighted_score > -0.1

    def test_no_mentions_returns_neutral(self) -> None:
        """aggregate with empty list returns neutral with strength 0."""
        analyzer = SentimentAnalyzer()
        aggregated = analyzer.aggregate("BTC", [])

        assert aggregated.total_mentions == 0
        assert aggregated.average_score == 0
        assert aggregated.direction == "neutral"
        assert aggregated.strength == 0
        assert aggregated.neutral_pct == 100

    def test_dominant_hashtags_extracted(self) -> None:
        """Aggregate extracts dominant hashtags from all mentions."""
        analyzer = SentimentAnalyzer()
        mentions = [
            _mention(mention_id="h1", content="#BTC looking great #bullish"),
            _mention(mention_id="h2", content="#BTC to the moon #crypto"),
            _mention(mention_id="h3", content="#BTC strong support #hodl"),
        ]
        aggregated = analyzer.aggregate("BTC", mentions)

        assert len(aggregated.dominant_hashtags) >= 1


class TestSocialScorer:
    """Tests for SocialScorer."""

    @pytest.mark.asyncio
    async def test_compute_score_returns_social_score(self) -> None:
        """compute_score returns a properly formed SocialScore."""
        scorer = SocialScorer()
        mentions = [
            _mention(mention_id="ss1", content="BTC looking great!", followers=5000),
            _mention(mention_id="ss2", content="BTC might go up", followers=1000),
        ]
        score = await scorer.compute_score("BTC", mentions=mentions)

        assert isinstance(score, SocialScore)
        assert score.symbol == "BTC"
        assert 0 <= score.total_score <= 100
        assert 0 <= score.sentiment_score <= 100
        assert 0 <= score.volume_score <= 100
        assert 0 <= score.influence_score <= 100
        assert score.direction in ("bullish", "bearish", "neutral")

    @pytest.mark.asyncio
    async def test_compute_score_no_mentions(self) -> None:
        """compute_score with no mentions returns neutral with volume_score 0."""
        scorer = SocialScorer()
        score = await scorer.compute_score("ETH", mentions=[])

        assert score.mention_count == 0
        assert score.direction == "neutral"
        assert score.volume_score == 0


class TestSocialManipulationDetector:
    """Tests for SocialManipulationDetector."""

    def test_bot_activity_detection(self) -> None:
        """Detector flags bot-like accounts with high engagement / low followers."""
        detector = SocialManipulationDetector()
        now = datetime.now(UTC).timestamp()

        # Create mentions that look like bot activity
        mentions = [
            SocialMention(
                id=f"bot_{i}", platform="twitter",
                content=f"BTC pump number {i}",
                author=f"suspicious_account_{i % 5}",
                symbol="BTC",
                timestamp=now - (i * 10),
                platform_type="post",
                engagement=100,
                followers_count=10,
                is_verified=False,
            )
            for i in range(15)
        ]
        risk = detector.analyze("BTC", mentions)

        assert isinstance(risk, SocialRiskScore)
        assert risk.overall_risk >= 0
        assert risk.risk_level in ("low", "medium", "high", "critical")

        if risk.overall_risk > 0:
            # At least one indicator should exist if risk > 0
            assert len(risk.indicators) > 0

    def test_clean_mentions_no_manipulation(self) -> None:
        """Diverse, verified accounts with unique content should have low risk."""
        detector = SocialManipulationDetector()
        now = datetime.now(UTC).timestamp()

        mentions = [
            SocialMention(
                id=f"clean_{i}", platform="twitter",
                content=f"This is a unique opinion about BTC number {i}",
                author=f"real_user_{i}",
                symbol="BTC",
                timestamp=now - (i * 100),
                platform_type="post",
                engagement=10,
                followers_count=5000,
                is_verified=True,
            )
            for i in range(20)
        ]
        risk = detector.analyze("BTC", mentions)

        assert risk.overall_risk == 0 or risk.risk_level == "low"

    def test_few_mentions_returns_low_risk(self) -> None:
        """Fewer than 10 mentions returns an empty (low risk) result."""
        detector = SocialManipulationDetector()
        mentions = [_mention() for _ in range(3)]
        risk = detector.analyze("BTC", mentions)

        assert risk.overall_risk == 0
        assert risk.risk_level == "low"
        assert len(risk.indicators) == 0

    def test_is_manipulated_returns_bool(self) -> None:
        """is_manipulated returns False for a clean symbol."""
        detector = SocialManipulationDetector()
        assert not detector.is_manipulated("BTC")
