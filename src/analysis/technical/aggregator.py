"""
Agrégateur multi-timeframe.

Fusionne les signaux des différents timeframes (1m à 1w)
en un score cohérent. Timeframes lents ont plus de poids.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.utils.logging import get_logger

logger = get_logger(__name__)


# Poids des timeframes (les plus longs = plus de poids)
TIMEFRAME_WEIGHTS = {
    "1m": 0.05,
    "5m": 0.08,
    "15m": 0.10,
    "1h": 0.17,
    "4h": 0.20,
    "1d": 0.25,
    "1w": 0.15,
}


@dataclass
class TimeframeSignal:
    """Signal d'un timeframe spécifique."""

    timeframe: str
    score: float  # -100 (bearish) à +100 (bullish)
    indicators_count: int = 0
    patterns_count: int = 0
    confidence: float = 0.0


@dataclass
class AggregatedSignal:
    """Signal agrégé multi-timeframe."""

    symbol: str
    final_score: float  # -100 à +100
    direction: str  # bullish | bearish | neutral
    strength: float  # 0 à 1
    timeframe_signals: list[TimeframeSignal] = field(default_factory=list)
    divergence: bool = False  # timeframes en désaccord
    strong_consensus: bool = False  # majorité timeframes alignés


class MultiTimeframeAggregator:
    """
    Agrège les signaux techniques multi-timeframe.

    Logique :
    - Timeframes longs (4h, 1d, 1w) = tendance générale (60% du poids)
    - Timeframes courts (1m, 5m, 15m) = exécution (15% du poids)
    - Timeframe intermédiaire (1h) = confirmation (25% du poids)
    - Détection de divergence entre timeframes
    """

    def __init__(self) -> None:
        self._cache: dict[str, AggregatedSignal] = {}

    def aggregate(
        self,
        symbol: str,
        scores_by_timeframe: dict[str, float],
        confidence_by_timeframe: dict[str, float] | None = None,
    ) -> AggregatedSignal:
        """
        Agrège les scores de tous les timeframes.

        Args:
            symbol: Symbole analysé
            scores_by_timeframe: {timeframe: score} où score ∈ [-100, +100]
            confidence_by_timeframe: {timeframe: confiance} où confiance ∈ [0, 1]

        Returns:
            Signal agrégé
        """
        if confidence_by_timeframe is None:
            confidence_by_timeframe = dict.fromkeys(scores_by_timeframe, 0.7)

        timeframe_signals: list[TimeframeSignal] = []
        weighted_sum = 0.0
        total_weight = 0.0
        directions: dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}

        for tf, weight in TIMEFRAME_WEIGHTS.items():
            if tf not in scores_by_timeframe:
                continue

            score = scores_by_timeframe[tf]
            conf = min(confidence_by_timeframe.get(tf, 0.5), 1.0)

            ts = TimeframeSignal(
                timeframe=tf,
                score=score,
                confidence=conf,
            )
            timeframe_signals.append(ts)

            weighted_sum += score * weight * conf
            total_weight += weight * conf

            # Compter les directions
            if score > 20:
                directions["bullish"] += 1
            elif score < -20:
                directions["bearish"] += 1
            else:
                directions["neutral"] += 1

        # Score final
        final_score = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Détection de divergence entre timeframes
        bullish_tfs = sum(1 for ts in timeframe_signals if ts.score > 20)
        bearish_tfs = sum(1 for ts in timeframe_signals if ts.score < -20)
        total_active = len(timeframe_signals)

        divergence = False
        strong_consensus = False

        if total_active >= 3:
            # Divergence si moins de 60% des timeframes sont alignés
            max_aligned = max(bullish_tfs, bearish_tfs)
            divergence = max_aligned < total_active * 0.6 and total_active > 2

            # Consensus fort si 80%+ alignés
            strong_consensus = max_aligned >= total_active * 0.8

        # Direction et force
        if final_score > 15:
            direction = "bullish"
        elif final_score < -15:
            direction = "bearish"
        else:
            direction = "neutral"

        strength = min(1.0, abs(final_score) / 80.0)

        result = AggregatedSignal(
            symbol=symbol,
            final_score=round(final_score, 2),
            direction=direction,
            strength=round(strength, 3),
            timeframe_signals=timeframe_signals,
            divergence=divergence,
            strong_consensus=strong_consensus,
        )

        self._cache[symbol] = result
        return result

    def get_cached(self, symbol: str) -> AggregatedSignal | None:
        """Retourne le dernier signal agrégé pour un symbole."""
        return self._cache.get(symbol)

    def get_alignment_score(self, symbol: str) -> float:
        """
        Score d'alignement des timeframes.

        0.0 = timeframes en conflit total
        1.0 = timeframes parfaitement alignés
        """
        cached = self._cache.get(symbol)
        if not cached or len(cached.timeframe_signals) < 2:
            return 0.5

        signs = [np.sign(ts.score) for ts in cached.timeframe_signals]
        # Ignorer les neutres
        signs = [s for s in signs if s != 0]

        if not signs:
            return 0.5

        # Proportion de timeframes allant dans la même direction
        majority = max(signs.count(1), signs.count(-1))
        return majority / len(signs)
