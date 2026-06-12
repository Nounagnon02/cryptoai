"""
Score d'actualité global.

Combine les scores des différentes sources d'actualité
en un score unique de sentiment news.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.news.aggregator import NewsAggregator, NewsArticle
from src.analysis.news.analyzer import NewsAnalyzer
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class NewsScore:
    """Score d'actualité global pour un actif."""

    symbol: str
    total_score: float  # 0-100
    direction: str  # bullish | bearish | neutral

    # Composants
    sentiment_score: float  # 0-100
    volume_score: float  # Nombre d'articles (normalisé)
    impact_score: float  # Importance perçue

    # Détails
    article_count: int = 0
    top_headlines: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class NewsScorer:
    """
    Calcule un score d'actualité global (0-100).

    Agrège :
    - Sentiment des articles (60%)
    - Volume d'actualités (20%)
    - Impact estimé (20%)
    """

    WEIGHTS = {
        "sentiment": 0.60,
        "volume": 0.20,
        "impact": 0.20,
    }

    def __init__(self) -> None:
        self.aggregator = NewsAggregator()
        self.analyzer = NewsAnalyzer()

    async def compute_score(
        self,
        symbol: str,
        articles: list[NewsArticle] | None = None,
    ) -> NewsScore:
        """
        Calcule le score d'actualité pour un actif.

        Args:
            symbol: Actif (BTC, ETH, etc.)
            articles: Articles pré-collectés (sinon fetch auto)

        Returns:
            NewsScore complet
        """
        # Collecter si non fourni
        if articles is None:
            articles = await self.aggregator.fetch_latest(
                symbols=[symbol],
                max_age_hours=48,
            )

        # Score de sentiment agrégé
        sentiment = self.analyzer.aggregate_score(symbol, articles)

        # Sentiment score (0-100)
        sentiment_score = 50 + sentiment.weighted_sentiment * 50
        sentiment_score = max(0, min(100, sentiment_score))

        # Volume score (normalisé : 20+ articles = max)
        volume_score = min(100, (sentiment.article_count / 20) * 100)

        # Impact score (engagement + nombre de sources)
        unique_sources = len({a.source for a in articles})
        impact_score = min(100, unique_sources * 20)

        # Score total pondéré
        total_score = (
            sentiment_score * self.WEIGHTS["sentiment"]
            + volume_score * self.WEIGHTS["volume"]
            + impact_score * self.WEIGHTS["impact"]
        )

        # Signaux
        signals = []
        if sentiment.direction != "neutral":
            signals.append(
                f"Sentiment médias {sentiment.direction} "
                f"({sentiment.weighted_sentiment:+.2f})"
            )
        if sentiment.article_count > 10:
            signals.append(f"Couverture médiatique élevée ({sentiment.article_count} articles)")

        return NewsScore(
            symbol=symbol,
            total_score=round(total_score, 1),
            direction=sentiment.direction,
            sentiment_score=round(sentiment_score, 1),
            volume_score=round(volume_score, 1),
            impact_score=round(impact_score, 1),
            article_count=sentiment.article_count,
            top_headlines=sentiment.recent_headlines[:3],
            signals=signals,
            warnings=sentiment.warnings,
        )
