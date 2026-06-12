"""
Traqueur de mentions sur les réseaux sociaux.

Surveille les plateformes sociales pour les mentions d'actifs crypto :
- Twitter/X : tweets, retweets, likes
- Reddit : posts, commentaires, upvotes
- Telegram : messages dans les groupes
- Discord : messages dans les serveurs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class SocialMention:
    """Mention sur un réseau social."""

    id: str
    platform: str  # twitter | reddit | telegram | discord
    content: str
    author: str
    symbol: str  # Actif mentionné (BTC, ETH, etc.)
    timestamp: float
    platform_type: str  # post | comment | reply | message
    engagement: int = 0  # Likes, upvotes, etc.
    followers_count: int = 0  # Influence de l'auteur
    is_verified: bool = False  # Compte vérifié
    language: str = "en"


@dataclass
class SocialMetrics:
    """Métriques sociales agrégées."""

    symbol: str
    total_mentions_24h: int
    unique_authors_24h: int
    avg_engagement: float
    author_diversity: float  # 0-1

    # Trending
    mention_velocity: float  # Mentions par heure (récentes)
    mention_acceleration: float  # Accélération des mentions

    # Influence
    top_influencers: list[str] = field(default_factory=list)
    verified_ratio: float = 0.0

    # Warnings
    anomaly_score: float = 0.0  # 0 = normal, 1 = très anormal
    warnings: list[str] = field(default_factory=list)


class SocialTracker:
    """
    Traque les mentions crypto sur les réseaux sociaux.

    Note : Version simulée pour le développement.
    En production, connecter aux APIs (Twitter API v2, Reddit API,
    Telegram Bot API, Discord Bot API).
    """

    def __init__(self) -> None:
        self._mentions: dict[str, list[SocialMention]] = {}
        self._metrics: dict[str, SocialMetrics] = {}

    def record_mention(self, mention: SocialMention) -> None:
        """Enregistre une mention."""
        sym = mention.symbol.upper()
        if sym not in self._mentions:
            self._mentions[sym] = []
        self._mentions[sym].append(mention)

        if len(self._mentions[sym]) > 10_000:
            self._mentions[sym] = self._mentions[sym][-10_000:]

    def record_batch(self, mentions: list[SocialMention]) -> None:
        """Enregistre un lot de mentions."""
        for m in mentions:
            self.record_mention(m)

    def compute_metrics(self, symbol: str) -> SocialMetrics:
        """Calcule les métriques sociales pour un actif."""
        mentions = self._mentions.get(symbol.upper(), [])
        now = datetime.now(UTC).timestamp()

        # Fenêtre 24h
        recent = [m for m in mentions if m.timestamp > now - 86400]

        if not recent:
            return SocialMetrics(
                symbol=symbol,
                total_mentions_24h=0,
                unique_authors_24h=0,
                avg_engagement=0,
                author_diversity=0,
                mention_velocity=0,
                mention_acceleration=0,
            )

        # Métriques de base
        unique_authors = len({m.author for m in recent})
        avg_engagement = sum(m.engagement for m in recent) / max(1, len(recent))
        author_diversity = unique_authors / max(1, len(recent))
        verified_ratio = sum(1 for m in recent if m.is_verified) / max(1, len(recent))

        # Vélocité (mentions par heure - dernières 4h vs 24h)
        recent_4h = [m for m in recent if m.timestamp > now - 14400]
        velocity_4h = len(recent_4h) / 4 if recent_4h else 0
        velocity_24h = len(recent) / 24

        # Accélération
        acceleration = (velocity_4h - velocity_24h) / velocity_24h if velocity_24h > 0 else 0

        # Top influenceurs
        author_scores: dict[str, int] = {}
        for m in recent:
            score = m.engagement + (m.followers_count // 100)
            if m.is_verified:
                score *= 2
            author_scores[m.author] = author_scores.get(m.author, 0) + score

        top_influencers = sorted(
            author_scores, key=author_scores.get, reverse=True
        )[:5]

        # Détection d'anomalies
        anomaly_score = self._detect_anomaly(recent, velocity_4h, author_diversity)

        warnings = []
        if anomaly_score > 0.7:
            warnings.append("Activité sociale anormale — possible manipulation")
        if velocity_4h > velocity_24h * 3:
            warnings.append("Fort pic de mentions — vérifier la cause")
        if author_diversity < 0.2 and len(recent) > 50:
            warnings.append("Faible diversité d'auteurs — possible astroturfing")

        metrics = SocialMetrics(
            symbol=symbol,
            total_mentions_24h=len(recent),
            unique_authors_24h=unique_authors,
            avg_engagement=round(avg_engagement, 1),
            author_diversity=round(author_diversity, 3),
            mention_velocity=round(velocity_4h, 1),
            mention_acceleration=round(acceleration, 3),
            top_influencers=top_influencers,
            verified_ratio=round(verified_ratio, 3),
            anomaly_score=round(anomaly_score, 2),
            warnings=warnings,
        )

        self._metrics[symbol] = metrics
        return metrics

    def _detect_anomaly(
        self,
        mentions: list[SocialMention],
        velocity: float,
        diversity: float,
    ) -> float:
        """
        Détecte les anomalies dans l'activité sociale.

        Score élevé = activité suspecte (bots, manipulation).
        """
        if len(mentions) < 10:
            return 0.0

        score = 0.0

        # Vélocité anormale
        if velocity > 100:
            score += 0.3
        elif velocity > 50:
            score += 0.2

        # Faible diversité malgré un volume élevé
        if diversity < 0.3 and len(mentions) > 100:
            score += 0.3
        elif diversity < 0.5 and len(mentions) > 200:
            score += 0.2

        # Trop de comptes non vérifiés
        verified = sum(1 for m in mentions if m.is_verified)
        if verified / max(1, len(mentions)) < 0.05 and len(mentions) > 50:
            score += 0.2

        return min(1.0, score)

    def get_metrics(self, symbol: str) -> SocialMetrics | None:
        """Dernières métriques sociales."""
        return self._metrics.get(symbol.upper())
