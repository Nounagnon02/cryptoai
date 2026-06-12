"""
Analyse de sentiment des réseaux sociaux.

Utilise une approche NLP pour classifier le sentiment
des mentions sociales (bullish/bearish/neutral).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.analysis.social.tracker import SocialMention
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SentimentResult:
    """Résultat de sentiment pour une mention."""

    mention_id: str
    sentiment: str  # bullish | bearish | neutral
    score: float  # -1 à +1
    confidence: float  # 0-1
    emoji_score: float  # Sentiment basé sur les emojis (-1 à +1)
    hashtags: list[str] = field(default_factory=list)


@dataclass
class AggregatedSocialSentiment:
    """Sentiment social agrégé."""

    symbol: str
    total_mentions: int
    average_score: float  # -1 à +1
    weighted_score: float  # Pondéré par influence
    bullish_pct: float  # % bullish
    bearish_pct: float  # % bearish
    neutral_pct: float  # % neutral
    direction: str  # bullish | bearish | neutral
    strength: float  # 0-1
    dominant_hashtags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SentimentAnalyzer:
    """
    Analyse le sentiment des mentions sociales crypto.

    Combine :
    1. Analyse lexicale (mots-clés bullish/bearish)
    2. Analyse d'emojis (sentiment via émojis)
    3. Analyse de hashtags
    4. Pondération par influence
    """

    # Lexique crypto social
    BULLISH_LEXICON = {
        "bullish", "moon", "mooning", "rocket", "🚀", "pump",
        "buy", "buying", "hodl", "hold", "long", "calls",
        "gem", "undervalued", "oversold", "accumulate",
        "profits", "gain", "winning", "winner", "breakout",
        "support", "bottom", "rally", "green", "ath",
        "partnership", "adoption", "mainnet", "upgrade",
        "guap", "gains", "profit", "wealth", "rich",
        "bullrun", "bull", "launch", "listing",
    }

    BEARISH_LEXICON = {
        "bearish", "dump", "crash", "💀", "scam", "sell",
        "selling", "short", "puts", "overbought", "resist",
        "fud", "fear", "panic", "capitulation", "rekt",
        "liquidation", "death", "falling", "drop", "decline",
        "correction", "bear", "bearmarket", "trap",
        "fake", "manipulation", "rug", "ponzi", "shitcoin",
        "bagholder", "bag", "down", "red", "loss",
    }

    NEUTRAL_LEXICON = {
        "maybe", "might", "could", "unsure", "confused",
        "analysis", "chart", "pattern", "indicator", "ta",
        "news", "update", "report", "info", "information",
    }

    # Emojis et mapping de sentiment
    EMOJI_SENTIMENT = {
        "🚀": 1.0, "📈": 0.8, "💰": 0.9, "🤑": 0.9,
        "✅": 0.5, "🎯": 0.7, "💎": 0.8, "🔥": 0.7,
        "👀": 0.3, "🤔": -0.2, "😬": -0.5,
        "💀": -1.0, "📉": -0.8, "⚠️": -0.6, "🔻": -0.7,
        "😱": -0.8, "🤡": -0.7, "💩": -0.9,
    }

    def __init__(self) -> None:
        self._results: dict[str, list[SentimentResult]] = {}

    def analyze_mention(self, mention: SocialMention) -> SentimentResult:
        """
        Analyse le sentiment d'une mention sociale.

        Args:
            mention: Mention sociale

        Returns:
            Sentiment result
        """
        content = mention.content.lower()

        # Score lexical
        lexical_score = self._lexical_score(content)

        # Score emoji
        emoji_score = self._emoji_score(content)

        # Score combiné
        score = lexical_score * 0.6 + emoji_score * 0.4 if abs(emoji_score) > 0.3 else lexical_score

        # Hashtags
        hashtags = re.findall(r'#(\w+)', mention.content)

        # Classification
        if score > 0.15:
            sentiment = "bullish"
        elif score < -0.15:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        # Confiance
        word_count = len(content.split())
        confidence = min(1.0, word_count / 20)

        result = SentimentResult(
            mention_id=mention.id,
            sentiment=sentiment,
            score=round(score, 3),
            confidence=round(confidence, 2),
            emoji_score=round(emoji_score, 3),
            hashtags=hashtags,
        )

        sym = mention.symbol.upper()
        if sym not in self._results:
            self._results[sym] = []
        self._results[sym].append(result)

        return result

    def analyze_batch(self, mentions: list[SocialMention]) -> list[SentimentResult]:
        """Analyse le sentiment d'un lot de mentions."""
        return [self.analyze_mention(m) for m in mentions]

    def aggregate(
        self,
        symbol: str,
        mentions: list[SocialMention],
    ) -> AggregatedSocialSentiment:
        """
        Agrège le sentiment social pour un actif.

        Args:
            symbol: Actif
            mentions: Mentions à analyser

        Returns:
            Sentiment social agrégé
        """
        if not mentions:
            return AggregatedSocialSentiment(
                symbol=symbol,
                total_mentions=0,
                average_score=0,
                weighted_score=0,
                bullish_pct=0,
                bearish_pct=0,
                neutral_pct=100,
                direction="neutral",
                strength=0,
            )

        # Analyser toutes les mentions
        results = [self.analyze_mention(m) for m in mentions]

        # Score moyen
        avg_score = sum(r.score for r in results) / len(results)

        # Score pondéré par l'influence (followers)
        total_followers = sum(m.followers_count for m in mentions) or 1
        weighted = sum(
            r.score * (1 + m.followers_count / 1000)
            for r, m in zip(results, mentions, strict=False)
        ) / total_followers

        # Distribution
        bullish = sum(1 for r in results if r.sentiment == "bullish")
        bearish = sum(1 for r in results if r.sentiment == "bearish")
        neutral = sum(1 for r in results if r.sentiment == "neutral")
        total = len(results)

        # Direction
        total_sentiment = weighted
        if total_sentiment > 0.1:
            direction = "bullish"
        elif total_sentiment < -0.1:
            direction = "bearish"
        else:
            direction = "neutral"

        # Force
        strength = min(1.0, abs(total_sentiment) * 3)

        # Hashtags dominants
        all_hashtags = [h for r in results for h in r.hashtags]
        hashtag_freq: dict[str, int] = {}
        for h in all_hashtags:
            hashtag_freq[h] = hashtag_freq.get(h, 0) + 1
        dominant_hashtags = sorted(
            hashtag_freq, key=hashtag_freq.get, reverse=True
        )[:10]

        warnings = []
        if bullish > total * 0.75:
            warnings.append("Sentiment anormalement positif — possible manipulation")
        elif bearish > total * 0.75:
            warnings.append("Sentiment anormalement négatif — possible FUD orchestré")

        if len(mentions) < 5:
            warnings.append("Faible volume de mentions")
        elif len(mentions) > 500:
            warnings.append("Volume de mentions très élevé — vérifier la cause")

        return AggregatedSocialSentiment(
            symbol=symbol,
            total_mentions=total,
            average_score=round(avg_score, 3),
            weighted_score=round(weighted, 3),
            bullish_pct=round(bullish / total * 100, 1),
            bearish_pct=round(bearish / total * 100, 1),
            neutral_pct=round(neutral / total * 100, 1),
            direction=direction,
            strength=round(strength, 2),
            dominant_hashtags=dominant_hashtags,
            warnings=warnings,
        )

    def _lexical_score(self, text: str) -> float:
        """Score basé sur le lexique de mots-clés."""
        words = set(text.split())

        bullish_count = sum(1 for word in words if word in self.BULLISH_LEXICON)
        bearish_count = sum(1 for word in words if word in self.BEARISH_LEXICON)
        _neutral_count = sum(1 for word in words if word in self.NEUTRAL_LEXICON)  # Used to reduce confidence, not direction

        # Neutral words réduisent la confiance, pas le score directionnel
        total_directional = bullish_count + bearish_count

        if total_directional == 0:
            return 0.0

        raw_score = (bullish_count - bearish_count) / total_directional

        # Bootstrap si très peu de mots directionnels
        if total_directional == 1:
            raw_score *= 0.5

        return max(-1, min(1, raw_score))

    def _emoji_score(self, text: str) -> float:
        """Score basé sur les emojis."""
        score = 0.0
        count = 0

        for char in text:
            if char in self.EMOJI_SENTIMENT:
                score += self.EMOJI_SENTIMENT[char]
                count += 1

        if count == 0:
            return 0.0

        return score / count
