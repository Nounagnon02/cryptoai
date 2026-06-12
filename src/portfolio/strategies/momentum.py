"""
Momentum Strategy — Stratégie de momentum.

Utilise :
- RSI pour détecter la force du momentum
- ROC (Rate of Change) pour la vélocité
- Stochastic RSI pour les points d'entrée précis
- Volume confirmation

Entrée : Momentum fort + volume croissant + pas en zone d'extinction
Sortie : Momentum faiblissant ou retournement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MomentumSignal:
    """Signal généré par la stratégie momentum."""

    direction: str  # bullish | bearish | neutral
    score: float  # 0-100
    confidence: float  # 0-1
    momentum_regime: str  # building | peaking | fading | reversing
    reason: str
    indicators: dict[str, Any] = field(default_factory=dict)


class MomentumStrategy:
    """
    Stratégie basée sur le momentum.

    Points d'entrée :
    - RSI entre 40-60 (pas en surachat/survente)
    - ROC > 0 (bullish) ou < 0 (bearish)
    - Volume en augmentation

    Sortie :
    - RSI > 70 (surachat) ou RSI < 30 (survente)
    - ROC s'inverse
    - Divergence RSI/prix
    """

    def __init__(
        self,
        weight: float = 0.25,
        max_allocation_pct: float = 25.0,
    ) -> None:
        self.weight = weight
        self.max_allocation_pct = max_allocation_pct
        self._name = "momentum"

    @property
    def name(self) -> str:
        return self._name

    def analyze(
        self,
        rsi: float,
        roc: float,
        stochastic_rsi: float,
        volume_ratio: float,  # Volume actuel / Volume moyen
        _current_price: float,
        price_change_1h: float,  # % de changement sur 1h
        **_kwargs,
    ) -> MomentumSignal:
        """
        Analyse le momentum et génère un signal.

        Args:
            rsi: RSI (0-100)
            roc: Rate of Change (%)
            stochastic_rsi: Stochastic RSI (0-1)
            volume_ratio: Ratio volume actuel/moyen
            current_price: Prix actuel
            price_change_1h: Changement de prix sur 1h (%)

        Returns:
            MomentumSignal complet
        """
        score = 50.0
        reasons: list[str] = []
        indicators = {
            "rsi": rsi,
            "roc": roc,
            "stochastic_rsi": stochastic_rsi,
            "volume_ratio": volume_ratio,
            "price_change_1h": price_change_1h,
        }

        # 1. RSI — force du momentum
        if 40 <= rsi <= 60:
            # Zone neutre — momentum peut se développer
            score += 5
            reasons.append(f"RSI neutral ({rsi:.1f})")
        elif rsi > 70:
            # Surachat — attention au retournement
            score -= 15
            reasons.append(f"RSI overbought ({rsi:.1f})")
        elif rsi < 30:
            # Survente — attention au retournement haussier
            score += 10 if roc > 0 else -10
            reasons.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 60:
            # Momentum haussier
            if roc > 0:
                score += 15
                reasons.append(f"Bullish momentum (RSI={rsi:.1f})")
            else:
                score -= 5
                reasons.append(f"Weakening bullish (RSI={rsi:.1f}, ROC<0)")
        elif rsi < 40:
            # Momentum baissier
            if roc < 0:
                score -= 15
                reasons.append(f"Bearish momentum (RSI={rsi:.1f})")
            else:
                score += 5
                reasons.append(f"Weakening bearish (RSI={rsi:.1f}, ROC>0)")

        # 2. ROC — vélocité
        if roc > 5:
            score += 10
            reasons.append(f"Strong ROC ({roc:.1f}%)")
        elif roc > 2:
            score += 5
            reasons.append(f"Moderate ROC ({roc:.1f}%)")
        elif roc < -5:
            score -= 10
            reasons.append(f"Strong negative ROC ({roc:.1f}%)")
        elif roc < -2:
            score -= 5
            reasons.append(f"Moderate negative ROC ({roc:.1f}%)")

        # 3. Volume confirmation
        if volume_ratio > 1.5:
            score += 10 if score > 50 else -10
            reasons.append(f"High volume ({volume_ratio:.1f}x)")
        elif volume_ratio > 1.2:
            score += 5 if score > 50 else -5
            reasons.append(f"Above avg volume ({volume_ratio:.1f}x)")
        elif volume_ratio < 0.8:
            score *= 0.9  # Faible volume = momentum non confirmé
            reasons.append(f"Low volume ({volume_ratio:.1f}x)")

        # 4. Stochastic RSI — timing
        if 0.2 <= stochastic_rsi <= 0.8:
            score += 5
            reasons.append("Stoch RSI in range")
        elif stochastic_rsi > 0.9 and score < 50:
            score -= 10
            reasons.append("Stoch RSI extreme high")
        elif stochastic_rsi < 0.1 and score > 50:
            score += 10
            reasons.append("Stoch RSI extreme low — reversal potential")

        # Normaliser
        score = max(0, min(100, score))

        # Direction
        if score > 60:
            direction = "bullish"
        elif score < 40:
            direction = "bearish"
        else:
            direction = "neutral"

        # Régime de momentum
        if abs(score - 50) > 25 and volume_ratio > 1.3:
            momentum_regime = "peaking"
        elif abs(score - 50) > 15:
            momentum_regime = "building"
        elif abs(score - 50) > 5:
            momentum_regime = "fading"
        else:
            momentum_regime = "reversing"

        # Confiance
        confidence = abs(score - 50) / 100 * min(1.0, volume_ratio)

        return MomentumSignal(
            direction=direction,
            score=round(score, 1),
            confidence=round(confidence, 3),
            momentum_regime=momentum_regime,
            reason="; ".join(reasons),
            indicators=indicators,
        )

    def should_exit(self, signal: MomentumSignal) -> bool:
        """Vérifie si la position doit être fermée."""
        return (
            signal.momentum_regime in ("fading", "reversing")
            or signal.score < 40
        )


__all__ = ["MomentumStrategy", "MomentumSignal"]
