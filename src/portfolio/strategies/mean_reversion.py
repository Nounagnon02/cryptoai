"""
Mean Reversion Strategy — Retour à la moyenne.

Utilise :
- Bollinger Bands (déviation > 2σ)
- RSI extrême (< 30 ou > 70)
- Distance à la moyenne mobile

Entrée : Prix proche des bandes extrêmes + RSI extrême
Sortie : Retour vers la moyenne (bande médiane)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MeanReversionSignal:
    """Signal généré par la stratégie mean reversion."""

    direction: str  # bullish | bearish | neutral
    score: float  # 0-100
    confidence: float  # 0-1
    band_position: str  # lower | upper | middle | above | below
    deviation: float  # Écart-type par rapport à la moyenne
    reason: str
    indicators: dict[str, Any] = field(default_factory=dict)


class MeanReversionStrategy:
    """
    Stratégie de retour à la moyenne.

    Points d'entrée (buy) :
    - Prix touche la bande inférieure de Bollinger
    - RSI < 30 (survente)
    - Distance > 2σ de la moyenne

    Points d'entrée (sell) :
    - Prix touche la bande supérieure de Bollinger
    - RSI > 70 (surachat)
    - Distance > 2σ de la moyenne

    Sortie :
    - Retour à la moyenne mobile (bande médiane)
    - RSI revient en zone neutre
    """

    def __init__(
        self,
        weight: float = 0.20,
        max_allocation_pct: float = 20.0,
    ) -> None:
        self.weight = weight
        self.max_allocation_pct = max_allocation_pct
        self._name = "mean_reversion"

    @property
    def name(self) -> str:
        return self._name

    def analyze(
        self,
        current_price: float,
        bb_upper: float,
        bb_middle: float,
        bb_lower: float,
        rsi: float,
        atr: float | None = None,
        volume_ratio: float = 1.0,
        **_kwargs,
    ) -> MeanReversionSignal:
        """
        Analyse les conditions de retour à la moyenne.

        Args:
            current_price: Prix actuel
            bb_upper: Bande supérieure Bollinger
            bb_middle: Bande médiane (SMA 20)
            bb_lower: Bande inférieure Bollinger
            rsi: RSI (0-100)
            atr: ATR (optionnel)
            volume_ratio: Ratio volume actuel/moyen

        Returns:
            MeanReversionSignal complet
        """
        score = 50.0
        reasons: list[str] = []
        indicators = {
            "current_price": current_price,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "rsi": rsi,
            "atr": atr,
            "volume_ratio": volume_ratio,
        }

        # 1. Position par rapport aux bandes
        bb_width = bb_upper - bb_lower

        if current_price <= bb_lower:
            # Support sur bande inférieure
            deviation = (bb_middle - current_price) / max(bb_width / 4, 0.001)
            score += min(25, deviation * 5)
            band_position = "lower"
            reasons.append(f"Price at lower band (deviation={deviation:.1f}σ)")

            # Confirmation RSI
            if rsi < 30:
                score += 15
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi < 40:
                score += 10
                reasons.append(f"RSI near oversold ({rsi:.1f})")

        elif current_price >= bb_upper:
            # Résistance sur bande supérieure
            deviation = (current_price - bb_middle) / max(bb_width / 4, 0.001)
            score -= min(25, deviation * 5)
            band_position = "upper"
            reasons.append(f"Price at upper band (deviation={deviation:.1f}σ)")

            if rsi > 70:
                score -= 15
                reasons.append(f"RSI overbought ({rsi:.1f})")
            elif rsi > 60:
                score -= 10
                reasons.append(f"RSI near overbought ({rsi:.1f})")

        else:
            # Dans les bandes
            deviation = (current_price - bb_middle) / max(bb_width / 4, 0.001)

            if abs(deviation) < 0.5:
                band_position = "middle"
                score = 50  # Neutre — prix autour de la moyenne
                reasons.append("Price near middle band")
            elif current_price > bb_middle:
                band_position = "above"
                score -= deviation * 5
                reasons.append(f"Price above middle band ({deviation:.1f}σ)")
            else:
                band_position = "below"
                score += abs(deviation) * 5
                reasons.append(f"Price below middle band ({deviation:.1f}σ)")

        # 2. Volume — confirmation
        if volume_ratio > 1.5:
            if band_position == "lower":
                score += 10  # Vente massive = opportunité d'achat
                reasons.append("High volume at support")
            elif band_position == "upper":
                score -= 10  # Achat massif = sommet potentiel
                reasons.append("High volume at resistance")
        elif volume_ratio < 0.7 and abs(deviation) > 2:
            score *= 0.85  # Faible volume = mouvement non confirmé
            reasons.append("Low volume — weak signal")

        # Normaliser
        score = max(0, min(100, score))

        # Direction (inversée pour le mean reversion)
        if score > 60:
            direction = "bullish"  # Attente de hausse (prix bas)
        elif score < 40:
            direction = "bearish"  # Attente de baisse (prix haut)
        else:
            direction = "neutral"

        # Confiance basée sur l'extrémité
        confidence = min(1.0, abs(deviation) / 4) if abs(deviation) > 1.5 else abs(score - 50) / 100

        return MeanReversionSignal(
            direction=direction,
            score=round(score, 1),
            confidence=round(confidence, 3),
            band_position=band_position,
            deviation=round(deviation, 2),
            reason="; ".join(reasons),
            indicators=indicators,
        )

    def should_exit(self, signal: MeanReversionSignal) -> bool:
        """Vérifie si la position doit être fermée."""
        return (
            signal.band_position == "middle"
            or abs(signal.deviation) < 0.5
            or signal.score < 45
        )


__all__ = ["MeanReversionStrategy", "MeanReversionSignal"]
