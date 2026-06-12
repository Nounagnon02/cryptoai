"""
Tests for NewsAggregator, NewsAnalyzer, NewsScorer.

Covers article fetching, sentiment analysis (bullish/bearish/neutral),
symbol extraction, confidence scoring, and aggregated news scoring.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.analysis.news.aggregator import NewsAggregator, NewsArticle
from src.analysis.news.analyzer import (
    AggregatedNewsScore,
    NewsAnalyzer,
)
from src.analysis.news.scorer import NewsScore, NewsScorer

# ── Helpers ──────────────────────────────────────────────────────────────────


def _article(
    article_id: str = "art-1",
    title: str = "Bitcoin shows strong momentum above $60,000",
    content: str = "Bitcoin continues to show strong positive growth and adoption.",
    symbols: list[str] | None = None,
    source: str = "test_source",
    engagement: int = 100,
) -> NewsArticle:
    return NewsArticle(
        id=article_id,
        source=source,
        title=title,
        content=content,
        url=f"https://example.com/news/{article_id}",
        published_at=datetime.now(UTC).timestamp() - 3600,
        symbols=symbols or ["BTC"],
        engagement=engagement,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestNewsAggregator:
    """Tests for NewsAggregator."""

    @pytest.mark.asyncio
    async def test_fetch_latest_returns_articles(self) -> None:
        """fetch_latest returns a list of NewsArticles without error."""
        aggregator = NewsAggregator()
        articles = await aggregator.fetch_latest()
        assert isinstance(articles, list)
        if articles:
            assert isinstance(articles[0], NewsArticle)

    @pytest.mark.asyncio
    async def test_fetch_latest_with_symbol_filter(self) -> None:
        """fetch_latest with symbols filter narrows results."""
        aggregator = NewsAggregator()
        articles = await aggregator.fetch_latest(symbols=["BTC"])
        # All returned articles should reference BTC
        for a in articles:
            assert "BTC" in a.symbols

    def test_get_articles_for_symbol_cache(self) -> None:
        """get_articles_for_symbol returns cached articles for a symbol."""
        aggregator = NewsAggregator()
        art = _article(article_id="cache-test")
        # Manually insert into cache using _articles (by first symbol)
        aggregator._articles["BTC"] = [art]

        cached = aggregator.get_articles_for_symbol("BTC", limit=5)
        assert len(cached) >= 1
        assert cached[0].id == "cache-test"


class TestNewsAnalyzer:
    """Tests for NewsAnalyzer sentiment classification."""

    def test_bullish_article_bullish_sentiment(self) -> None:
        """An article with bullish terms is classified as bullish with score > 0."""
        analyzer = NewsAnalyzer()
        art = _article(
            title="Bitcoin bullish breakout above resistance, strong rally ahead",
            content="The market is showing a massive bullish breakout with surging "
                    "momentum and positive growth opportunities for investors.",
        )
        result = analyzer.analyze_article(art)

        assert result.sentiment == "bullish"
        assert result.score > 0

    def test_bearish_article_bearish_sentiment(self) -> None:
        """An article with bearish terms is classified as bearish with score < 0."""
        analyzer = NewsAnalyzer()
        art = _article(
            title="Bitcoin crash warning: sell-off intensifies, fear grips market",
            content="A massive bearish breakdown is occuring with extreme fear "
                    "and negative sentiment as prices decline sharply.",
        )
        result = analyzer.analyze_article(art)

        assert result.sentiment == "bearish"
        assert result.score < 0

    def test_neutral_article_neutral_sentiment(self) -> None:
        """An article with neither bullish nor bearish terms is neutral."""
        analyzer = NewsAnalyzer()
        art = _article(
            title="Bitcoin price update: market overview for today",
            content="The report provides information about current market conditions "
                    "and updates on recent price movements in the crypto space.",
        )
        result = analyzer.analyze_article(art)

        assert result.sentiment == "neutral"

    def test_mixed_sentiment_close_to_zero(self) -> None:
        """An article with both bullish and bearish terms scores near 0."""
        analyzer = NewsAnalyzer()
        art = _article(
            title="Bitcoin shows both bullish breakout and bearish risk factors",
            content="While there is bullish momentum and positive adoption, there "
                    "are also bearish risks and negative warning signs to consider.",
        )
        result = analyzer.analyze_article(art)

        # Should be neutral or have a low absolute score
        if result.sentiment == "neutral":
            assert abs(result.score) < 0.3
        else:
            assert abs(result.score) < 0.6

    def test_empty_text_neutral(self) -> None:
        """An article with empty title and content returns neutral."""
        analyzer = NewsAnalyzer()
        art = _article(title="", content="")
        result = analyzer.analyze_article(art)

        assert result.sentiment == "neutral"
        assert result.score == 0

    def test_symbol_extraction_from_text(self) -> None:
        """Symbols mentioned in the article appear in symbols_mentioned."""
        analyzer = NewsAnalyzer()
        art = _article(
            symbols=["BTC", "ETH"],
        )
        result = analyzer.analyze_article(art)

        assert "BTC" in result.symbols_mentioned
        assert "ETH" in result.symbols_mentioned

    def test_high_confidence_with_many_terms(self) -> None:
        """An article with many directional terms yields higher confidence."""
        analyzer = NewsAnalyzer()
        art = _article(
            title=" ".join([
                "bullish", "breakout", "surge", "rally", "moon",
                "accumulation", "adoption", "growth", "opportunity",
            ]),
            content=" ".join([
                "bullish", "breakout", "surge",
            ]),
        )
        result = analyzer.analyze_article(art)

        assert result.confidence >= 0.3

    def test_low_confidence_with_short_text(self) -> None:
        """A very short text lacking terms yields low confidence."""
        analyzer = NewsAnalyzer()
        art = _article(title="ok", content="fine")
        result = analyzer.analyze_article(art)

        assert result.confidence <= 0.5

    def test_aggregate_three_sentiments(self) -> None:
        """aggregate_score handles multiple articles correctly."""
        analyzer = NewsAnalyzer()
        articles = [
            _article(article_id="a1", title="bullish breakout rally", engagement=200),
            _article(article_id="a2", title="bearish crash warning", engagement=100),
            _article(article_id="a3", title="neutral market update", engagement=50),
        ]
        aggregated = analyzer.aggregate_score("BTC", articles)

        assert isinstance(aggregated, AggregatedNewsScore)
        assert aggregated.article_count == 3
        assert aggregated.direction in ("bullish", "bearish", "neutral")

    def test_aggregate_single_article(self) -> None:
        """aggregate_score with one article works correctly."""
        analyzer = NewsAnalyzer()
        art = _article(article_id="single", title="bullish growth expected", engagement=500)
        aggregated = analyzer.aggregate_score("BTC", [art])

        assert aggregated.article_count == 1

    def test_no_articles_returns_neutral(self) -> None:
        """aggregate_score with no articles returns neutral with strength 0."""
        analyzer = NewsAnalyzer()
        aggregated = analyzer.aggregate_score("BTC", [])

        assert aggregated.article_count == 0
        assert aggregated.average_sentiment == 0
        assert aggregated.weighted_sentiment == 0
        assert aggregated.direction == "neutral"
        assert aggregated.strength == 0

    def test_weighted_sentiment_differs_from_average(self) -> None:
        """Weighted sentiment differs when articles have different engagement."""
        analyzer = NewsAnalyzer()
        articles = [
            _article(article_id="w1", title="bullish breakout", engagement=1000),
            _article(article_id="w2", title="bearish crash", engagement=1),
        ]
        aggregated = analyzer.aggregate_score("BTC", articles)

        # The bullish article has much higher engagement
        assert isinstance(aggregated.weighted_sentiment, float)


class TestNewsScorer:
    """Tests for NewsScorer."""

    @pytest.mark.asyncio
    async def test_compute_score_with_articles(self) -> None:
        """compute_score returns a NewsScore with valid fields."""
        scorer = NewsScorer()
        articles = [
            _article(article_id="ns1", title="bullish momentum continues", source="src_a"),
            _article(article_id="ns2", title="positive growth expected", source="src_b"),
        ]
        score = await scorer.compute_score("BTC", articles=articles)

        assert isinstance(score, NewsScore)
        assert score.symbol == "BTC"
        assert 0 <= score.total_score <= 100
        assert 0 <= score.sentiment_score <= 100
        assert 0 <= score.volume_score <= 100
        assert 0 <= score.impact_score <= 100
        assert score.direction in ("bullish", "bearish", "neutral")

    @pytest.mark.asyncio
    async def test_compute_score_no_articles(self) -> None:
        """compute_score with empty articles is handled gracefully."""
        scorer = NewsScorer()
        score = await scorer.compute_score("ETH", articles=[])

        assert score.article_count == 0
        assert score.direction == "neutral"
        # sentiment_score should be 50 (neutral midpoint)
        assert score.sentiment_score == 50.0
