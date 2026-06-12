"""
Analyse NLP des actualités crypto.

Classifie les articles par sentiment (bullish/bearish/neutral)
et extrait les mots-clés et actifs mentionnés.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.analysis.news.aggregator import NewsArticle
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class NewsSentiment:
    """Sentiment extrait d'un article."""

    article_id: str
    title: str
    sentiment: str  # bullish | bearish | neutral
    score: float  # -1 (bearish) à +1 (bullish)
    confidence: float  # 0-1
    key_phrases: list[str] = field(default_factory=list)
    symbols_mentioned: list[str] = field(default_factory=list)


@dataclass
class AggregatedNewsScore:
    """Score d'actualité agrégé pour un actif."""

    symbol: str
    article_count: int
    average_sentiment: float  # -1 à +1
    weighted_sentiment: float  # Pondéré par engagement
    direction: str  # bullish | bearish | neutral
    strength: float  # 0-1
    recent_headlines: list[str] = field(default_factory=list)
    top_phrases: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class NewsAnalyzer:
    """
    Analyse le sentiment des actualités crypto.

    Utilise une approche par dictionnaire de mots-clés financiers.
    En production : remplacer par un modèle NLP fine-tuné (BERT, FinBERT).
    """

    # Lexique de sentiment crypto (extensible)
    BULLISH_TERMS = {
        # Général
        "bullish", "breakout", "surge", "rally", "moon", "pump",
        "accumulation", "adoption", "partnership", "institutional",
        "approval", "launch", "upgrade", "positive", "growth",
        "opportunity", "innovation", "breakthrough", "mainnet",
        "bull run", "all-time high", "ATH", "green", "uptrend",
        "oversold", "support", "reversal", "recovery",
        # Régulation
        "ETF", "regulation", "clarity", "legalization",
        # Technique
        "layer 2", "scaling", "hard fork",
    }

    BEARISH_TERMS = {
        # Général
        "bearish", "breakdown", "crash", "dump", "decline",
        "correction", "liquidation", "ban", "restriction",
        "negative", "risk", "warning", "fud", "fear",
        "capitulation", "sell-off", "bear market", "death cross",
        "overbought", "resistance", "downtrend", "recession",
        # Sécurité
        "hack", "exploit", "vulnerability", "attack", "breach",
        "scam", "fraud", "ponzi", "rug pull",
        # Régulation
        "crackdown", "lawsuit", "SEC", "fine", "penalty",
        "illegal", "unregistered", "cease", "desist",
    }

    # Mots-clés d'amplification
    AMPLIFIERS = {
        "massive", "huge", "extreme", "significant", "major",
        "critical", "severe", "enormous", "dramatic", "substantial",
    }

    def __init__(self) -> None:
        self._sentiments: dict[str, list[NewsSentiment]] = {}

    def analyze_article(self, article: NewsArticle) -> NewsSentiment:
        """
        Analyse le sentiment d'un article.

        Args:
            article: Article d'actualité

        Returns:
            Sentiment extrait
        """
        text = f"{article.title} {article.content[:500]}".lower()

        # Compter les termes
        bullish_count = 0
        bearish_count = 0
        amplification = 0

        for term in self.BULLISH_TERMS:
            if term in text:
                bullish_count += 1

        for term in self.BEARISH_TERMS:
            if term in text:
                bearish_count += 1

        for term in self.AMPLIFIERS:
            if term in text:
                amplification += 1

        # Score brut (-1 à +1)
        total = bullish_count + bearish_count
        raw_score = (bullish_count - bearish_count) / total if total > 0 else 0

        # Amplification
        if amplification > 0:
            raw_score *= 1 + (amplification * 0.1)

        # Clamping et mapping
        score = max(-1, min(1, raw_score))

        if score > 0.2:
            sentiment = "bullish"
        elif score < -0.2:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        # Confiance basée sur le nombre de termes trouvés
        confidence = min(1.0, total / 5)

        # Phrases clés
        phrases = self._extract_key_phrases(article.title)

        result = NewsSentiment(
            article_id=article.id,
            title=article.title,
            sentiment=sentiment,
            score=round(score, 3),
            confidence=round(confidence, 2),
            key_phrases=phrases,
            symbols_mentioned=article.symbols,
        )

        # Mettre en cache
        for symbol in article.symbols:
            if symbol not in self._sentiments:
                self._sentiments[symbol] = []
            self._sentiments[symbol].append(result)

        return result

    def analyze_batch(self, articles: list[NewsArticle]) -> list[NewsSentiment]:
        """Analyse le sentiment d'un lot d'articles."""
        return [self.analyze_article(a) for a in articles]

    def aggregate_score(
        self,
        symbol: str,
        articles: list[NewsArticle],
        _max_age_hours: int = 48,
    ) -> AggregatedNewsScore:
        """
        Calcule le score d'actualité agrégé pour un actif.

        Args:
            symbol: Actif (BTC, ETH, etc.)
            articles: Articles à analyser
            max_age_hours: Âge maximum des articles

        Returns:
            Score agrégé
        """
        if not articles:
            return AggregatedNewsScore(
                symbol=symbol,
                article_count=0,
                average_sentiment=0,
                weighted_sentiment=0,
                direction="neutral",
                strength=0,
            )

        # Analyser tous les articles
        sentiments = [self.analyze_article(a) for a in articles]

        # Sentiment moyen non pondéré
        avg_sentiment = sum(s.score for s in sentiments) / len(sentiments)

        # Sentiment pondéré par l'engagement
        total_engagement = sum(a.engagement for a in articles) or 1
        weighted = sum(
            s.score * a.engagement
            for s, a in zip(sentiments, articles, strict=False)
        ) / total_engagement

        # Direction
        if weighted > 0.15:
            direction = "bullish"
        elif weighted < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"

        # Force
        strength = min(1.0, abs(weighted) * 2)

        # Top headlines
        headlines = [a.title for a in articles[:5]]

        # Phrases clés fréquentes
        all_phrases = []
        for s in sentiments:
            all_phrases.extend(s.key_phrases)
        phrase_freq = {}
        for p in all_phrases:
            phrase_freq[p] = phrase_freq.get(p, 0) + 1
        top_phrases = sorted(phrase_freq, key=phrase_freq.get, reverse=True)[:5]

        warnings = []
        if len(articles) >= 10:
            bullish_count = sum(1 for s in sentiments if s.sentiment == "bullish")
            bearish_count = sum(1 for s in sentiments if s.sentiment == "bearish")
            if bullish_count > len(sentiments) * 0.7:
                warnings.append("Sentiment extrêmement positif — risque de bull trap médiatique")
            elif bearish_count > len(sentiments) * 0.7:
                warnings.append("Sentiment extrêmement négatif — possible sur-réaction")

        return AggregatedNewsScore(
            symbol=symbol,
            article_count=len(articles),
            average_sentiment=round(avg_sentiment, 3),
            weighted_sentiment=round(weighted, 3),
            direction=direction,
            strength=round(strength, 3),
            recent_headlines=headlines,
            top_phrases=top_phrases,
            warnings=warnings,
        )

    def _extract_key_phrases(self, title: str) -> list[str]:
        """Extrait les phrases clés d'un titre."""
        # Mots de liaison à ignorer
        stop_words = {
            "the", "a", "an", "in", "on", "at", "to", "for",
            "of", "and", "or", "is", "are", "was", "were",
            "has", "have", "had", "its", "it's", "with",
        }

        words = re.findall(r'\b[a-zA-Z]{3,}\b', title.lower())
        meaningful = [w for w in words if w not in stop_words]

        # Bigrammes
        phrases = []
        for i in range(len(meaningful) - 1):
            bigram = f"{meaningful[i]} {meaningful[i + 1]}"
            if bigram in self.BULLISH_TERMS or bigram in self.BEARISH_TERMS:
                phrases.append(bigram)

        # Unigrammes significatifs
        for word in meaningful:
            if (word in self.BULLISH_TERMS or word in self.BEARISH_TERMS) and word not in phrases:
                phrases.append(word)

        return phrases[:5]
