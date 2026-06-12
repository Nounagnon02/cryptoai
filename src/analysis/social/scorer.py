"""
Score de sentiment social global.

Agrège les métriques sociales et le sentiment en
un score unique de 0 à 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.social.manipulation import SocialManipulationDetector
from src.analysis.social.sentiment import SentimentAnalyzer
from src.analysis.social.tracker import SocialMention, SocialTracker
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SocialScore:
    """Score social global pour un actif."""

    symbol: str
    total_score: float  # 0-100
    direction: str  # bullish | bearish | neutral

    # Composants
    sentiment_score: float  # 0-100
    volume_score: float  # 0-100 (activité sociale)
    influence_score: float  # 0-100 (qualité des auteurs)

    # Détails
    mention_count: int = 0
    top_hashtags: list[str] = field(default_factory=list)
    manipulation_risk: float = 0.0  # 0-100
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SocialScorer:
    """
    Calcule un score social global (0-100).

    Composants :
    - Sentiment (50%) : bullish/bearish/neutral
    - Volume (25%) : nombre de mentions et vélocité
    - Influence (25%) : qualité et diversité des auteurs
    """

    WEIGHTS = {
        "sentiment": 0.50,
        "volume": 0.25,
        "influence": 0.25,
    }

    def __init__(self) -> None:
        self.tracker = SocialTracker()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.manipulation_detector = SocialManipulationDetector()

    async def compute_score(
        self,
        symbol: str,
        mentions: list[SocialMention] | None = None,
    ) -> SocialScore:
        """
        Calcule le score social global.

        Args:
            symbol: Actif analysé
            mentions: Mentions pré-collectées

        Returns:
            SocialScore complet
        """
        if mentions is None:
            mentions = []

        # Enregistrer et analyser
        self.tracker.record_batch(mentions)

        # Métriques
        metrics = self.tracker.compute_metrics(symbol)

        # Sentiment agrégé
        sentiment = self.sentiment_analyzer.aggregate(symbol, mentions)

        # Risque de manipulation
        risk = self.manipulation_detector.analyze(symbol, mentions)

        # Scores composants
        # Sentiment (0-100)
        sentiment_score = 50 + sentiment.weighted_score * 50
        sentiment_score = max(0, min(100, sentiment_score))

        # Volume (0-100)
        volume_score = min(100, metrics.total_mentions_24h * 2)
        if metrics.mention_acceleration > 0.5:
            volume_score = min(100, volume_score * 1.2)

        # Influence (0-100)
        influence_score = metrics.author_diversity * 50 + metrics.verified_ratio * 50

        # Ajustement pour manipulation
        if risk.overall_risk > 30:
            sentiment_score *= max(0.3, 1 - risk.overall_risk / 100)

        # Score total
        total_score = (
            sentiment_score * self.WEIGHTS["sentiment"]
            + volume_score * self.WEIGHTS["volume"]
            + influence_score * self.WEIGHTS["influence"]
        )

        # Direction
        direction = sentiment.direction

        # Signaux
        signals = []
        if sentiment.direction != "neutral":
            signals.append(
                f"Sentiment social {sentiment.direction} "
                f"({sentiment.weighted_score:+.2f})"
            )
        if metrics.mention_acceleration > 1.0:
            signals.append(f"Fort intérêt social (vélocité x{metrics.mention_acceleration:.1f})")
        if metrics.top_influencers:
            signals.append(f"Influenceurs actifs: {', '.join(metrics.top_influencers[:3])}")

        # Warnings
        warnings = list(metrics.warnings)
        warnings.extend(sentiment.warnings)
        warnings.extend(risk.warnings)

        return SocialScore(
            symbol=symbol,
            total_score=round(total_score, 1),
            direction=direction,
            sentiment_score=round(sentiment_score, 1),
            volume_score=round(volume_score, 1),
            influence_score=round(influence_score, 1),
            mention_count=metrics.total_mentions_24h,
            top_hashtags=sentiment.dominant_hashtags[:5],
            manipulation_risk=risk.overall_risk,
            signals=signals[:5],
            warnings=warnings[:5],
        )
