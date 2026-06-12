"""
Trend Following Strategy — Suivi de tendance.

Utilise :
- EMA crossovers (9/21, 21/50, 50/200)
- ADX (> 25 confirmé)
- Supertrend pour le filtre directionnel

Allocation progressive selon la force de la tendance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrendSignal:
    """Signal généré par la stratégie trend following."""

    direction: str  # bullish | bearish | neutral
    score: float  # 0-100
    confidence: float  # 0-1
    strength: str  # weak | moderate | strong
    reason: str
    indicators: dict[str, Any] = field(default_factory=dict)


class TrendFollowingStrategy:
    """
    Stratégie de suivi de tendance.

    Points d'entrée :
    - EMA 9/21 crossover → entrée
    - ADX > 25 → confirmation
    - Supertrend vert → filtre directionnel

    Sortie :
    - EMA crossover inverse
    - ADX < 20 (tendance finie)
    - Supertrend rouge
    """

    def __init__(
        self,
        weight: float = 0.30,
        max_allocation_pct: float = 30.0,
    ) -> None:
        self.weight = weight
        self.max_allocation_pct = max_allocation_pct
        self._name = "trend_following"

    @property
    def name(self) -> str:
        return self._name

    def analyze(
        self,
        ema_9: float,
        ema_21: float,
        ema_50: float,
        ema_200: float,
        adx: float,
        supertrend_direction: str,  # bullish | bearish
        current_price: float,
        **_kwargs,
    ) -> TrendSignal:
        """
        Analyse la tendance et génère un signal.

        Args:
            ema_9: EMA 9 périodes
            ema_21: EMA 21 périodes
            ema_50: EMA 50 périodes
            ema_200: EMA 200 périodes
            adx: ADX (0-100)
            supertrend_direction: Direction du Supertrend
            current_price: Prix actuel

        Returns:
            TrendSignal complet
        """
        score = 50.0
        reasons: list[str] = []
        indicators = {
            "ema_9": ema_9,
            "ema_21": ema_21,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "adx": adx,
            "supertrend": supertrend_direction,
        }

        # 1. Direction des EMAs (courte vs longue)
        bullish_emas = 0
        bearish_emas = 0

        if ema_9 > ema_21:
            bullish_emas += 1
        else:
            bearish_emas += 1

        if ema_21 > ema_50:
            bullish_emas += 1
        else:
            bearish_emas += 1

        if ema_50 > ema_200:
            bullish_emas += 1
        else:
            bearish_emas += 1

        # 2. Score basé sur les alignements d'EMA
        if bullish_emas >= 2:
            score += 15
            reasons.append(f"EMA alignment bullish ({bullish_emas}/3)")
        elif bearish_emas >= 2:
            score -= 15
            reasons.append(f"EMA alignment bearish ({bearish_emas}/3)")

        # 3. ADX — force de la tendance
        if adx > 25:
            if adx > 40:
                score += 15 if score > 50 else -15
                reasons.append(f"Strong trend (ADX={adx:.1f})")
            else:
                score += 10 if score > 50 else -10
                reasons.append(f"Trend confirmed (ADX={adx:.1f})")
        else:
            score *= 0.7  # Pénalité si pas de tendance
            reasons.append(f"Weak trend (ADX={adx:.1f})")

        # 4. Supertrend
        if supertrend_direction == "bullish":
            score += 10
            reasons.append("Supertrend bullish")
        else:
            score -= 10
            reasons.append("Supertrend bearish")

        # 5. Prix par rapport aux EMAs
        if current_price > ema_50:
            score += 5
        else:
            score -= 5

        if current_price > ema_200:
            score += 5
            reasons.append("Price above 200 EMA")
        else:
            score -= 5
            reasons.append("Price below 200 EMA")

        # Normaliser
        score = max(0, min(100, score))

        # Direction
        if score > 60:
            direction = "bullish"
        elif score < 40:
            direction = "bearish"
        else:
            direction = "neutral"

        # Confiance
        confidence = min(1.0, abs(score - 50) / 50) if adx > 25 else abs(score - 50) / 75

        # Force
        if adx > 30 and abs(score - 50) > 20:
            strength = "strong"
        elif adx > 25 and abs(score - 50) > 10:
            strength = "moderate"
        else:
            strength = "weak"

        return TrendSignal(
            direction=direction,
            score=round(score, 1),
            confidence=round(confidence, 3),
            strength=strength,
            reason="; ".join(reasons),
            indicators=indicators,
        )

    def should_exit(self, trend_signal: TrendSignal) -> bool:
        """Vérifie si la position doit être fermée."""
        return (
            trend_signal.direction == "bearish"
            or trend_signal.strength == "weak"
            or trend_signal.score < 40
        )


__all__ = ["TrendFollowingStrategy", "TrendSignal"]
