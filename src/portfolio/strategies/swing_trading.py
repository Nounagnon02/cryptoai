"""
Swing Trading Strategy — Trading de swing multi-timeframe.

Utilise la confluence de signaux sur plusieurs timeframes :
- Timeframe haute (4h/1d) pour la direction générale
- Timeframe basse (15m/1h) pour le point d'entrée précis

Combinaison :
- Trend (EMA, ADX) sur 4h/1d
- Momentum (RSI, Stochastic) sur 1h
- Volume confirmation
- Support/Résistance (Pivot Points)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SwingSignal:
    """Signal généré par la stratégie swing trading."""

    direction: str  # bullish | bearish | neutral
    score: float  # 0-100
    confidence: float  # 0-1
    confluence_level: str  # low | moderate | high | very_high
    timeframes_aligned: int  # Nombre de timeframes alignés
    reason: str
    indicators: dict[str, Any] = field(default_factory=dict)


class SwingTradingStrategy:
    """
    Stratégie de swing trading multi-timeframe.

    Principe : trader DANS la direction de la tendance principale
    avec un point d'entrée optimisé sur le timeframe inférieur.

    Confluence requise :
    - TF haute bullish + TF basse bullish → BUY (forte conviction)
    - TF haute bullish + TF basse bearish → HOLD/WAIT
    - TF haute bearish + TF basse bearish → SELL
    - TF haute bearish + TF basse bullish → HOLD/WAIT
    """

    def __init__(
        self,
        weight: float = 0.25,
        max_allocation_pct: float = 25.0,
    ) -> None:
        self.weight = weight
        self.max_allocation_pct = max_allocation_pct
        self._name = "swing_trading"

    @property
    def name(self) -> str:
        return self._name

    def analyze(
        self,
        # Timeframe haut (4h/1d)
        tf_high_trend: str,  # bullish | bearish | neutral
        tf_high_adx: float,
        tf_high_rsi: float,
        _tf_high_price: float,
        # Timeframe bas (15m/1h)
        tf_low_trend: str,
        tf_low_rsi: float,
        tf_low_momentum: str,  # building | peaking | fading | reversing
        # Volume
        volume_ratio: float,
        # Support/Résistance
        nearest_support: float | None = None,
        nearest_resistance: float | None = None,
        current_price: float | None = None,
        **_kwargs,
    ) -> SwingSignal:
        """
        Analyse la confluence multi-timeframe.

        Args:
            tf_high_trend: Direction du TF haut
            tf_high_adx: ADX du TF haut
            tf_high_rsi: RSI du TF haut
            tf_high_price: Prix sur le TF haut
            tf_low_trend: Direction du TF bas
            tf_low_rsi: RSI du TF bas
            tf_low_momentum: Momentum du TF bas
            volume_ratio: Ratio volume
            nearest_support: Support le plus proche
            nearest_resistance: Résistance la plus proche
            current_price: Prix actuel

        Returns:
            SwingSignal complet
        """
        score = 50.0
        reasons: list[str] = []
        indicators = {
            "tf_high_trend": tf_high_trend,
            "tf_high_adx": tf_high_adx,
            "tf_high_rsi": tf_high_rsi,
            "tf_low_trend": tf_low_trend,
            "tf_low_rsi": tf_low_rsi,
            "tf_low_momentum": tf_low_momentum,
            "volume_ratio": volume_ratio,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
        }

        # Compter les alignements
        timeframes_aligned = 0

        # 1. Confluence des directions
        if tf_high_trend == tf_low_trend and tf_high_trend != "neutral":
            timeframes_aligned = 2
            if tf_high_trend == "bullish":
                score += 25
                reasons.append("Bullish confluence across timeframes")
            else:
                score -= 25
                reasons.append("Bearish confluence across timeframes")
        elif tf_high_trend != "neutral" and tf_low_trend != "neutral":
            # Timeframes en conflit
            score -= 10
            reasons.append(f"TF conflict ({tf_high_trend} high vs {tf_low_trend} low)")
        else:
            # Un seul timeframe donne une direction claire
            if tf_high_trend == "bullish":
                score += 10
                reasons.append("HTF bullish")
                timeframes_aligned = 1
            elif tf_high_trend == "bearish":
                score -= 10
                reasons.append("HTF bearish")
                timeframes_aligned = 1
            elif tf_low_trend == "bullish":
                score += 5
                reasons.append("LTF bullish (no HTF confirmation)")
                timeframes_aligned = 1
            elif tf_low_trend == "bearish":
                score -= 5
                reasons.append("LTF bearish (no HTF confirmation)")
                timeframes_aligned = 1

        # 2. ADX sur TF haut — force de la tendance
        if tf_high_adx > 25:
            if score > 50:
                score += 10
                reasons.append(f"HTF strong trend (ADX={tf_high_adx:.1f})")
            elif score < 50:
                score -= 10
                reasons.append(f"HTF strong bearish trend (ADX={tf_high_adx:.1f})")
        elif tf_high_adx < 20:
            score *= 0.85
            reasons.append(f"HTF weak trend (ADX={tf_high_adx:.1f})")

        # 3. RSI pour le timing
        if 40 <= tf_low_rsi <= 60 and tf_high_trend != "neutral":
            score += 5 if tf_high_trend == "bullish" else -5
            reasons.append(f"LTF RSI neutral ({tf_low_rsi:.1f}) — good entry timing")
        elif tf_low_rsi > 70:
            score -= 10 if score > 50 else 0
            reasons.append(f"LTF RSI overbought ({tf_low_rsi:.1f})")
        elif tf_low_rsi < 30:
            score += 10 if score > 50 else 0
            reasons.append(f"LTF RSI oversold ({tf_low_rsi:.1f})")

        # 4. Momentum sur TF bas
        if tf_low_momentum == "building" and score > 50:
            score += 10
            reasons.append("LTF momentum building")
        elif tf_low_momentum == "peaking":
            score += 5 if score > 50 else -5
            reasons.append("LTF momentum peaking")
        elif tf_low_momentum == "fading":
            score -= 10 if score > 50 else 0
            reasons.append("LTF momentum fading")
        elif tf_low_momentum == "reversing":
            score = 100 - score  # Inversion du score
            reasons.append("LTF momentum reversing")

        # 5. Volume
        if volume_ratio > 1.3:
            if score > 50:
                score += 5
            else:
                score -= 5
            reasons.append(f"Volume confirmation ({volume_ratio:.1f}x)")

        # 6. Support/Résistance
        if current_price and nearest_support:
            dist_to_support = abs(current_price - nearest_support) / current_price * 100
            if dist_to_support < 2.0 and score > 50:
                score += 10
                reasons.append(f"Near support ({dist_to_support:.1f}%)")
            elif dist_to_support > 5.0 and score > 50:
                score -= 5
                reasons.append(f"Far from support ({dist_to_support:.1f}%)")

        if current_price and nearest_resistance:
            dist_to_resistance = abs(nearest_resistance - current_price) / current_price * 100
            if dist_to_resistance < 2.0 and score < 50:
                score -= 10
                reasons.append(f"Near resistance ({dist_to_resistance:.1f}%)")

        # Normaliser
        score = max(0, min(100, score))

        # Direction
        if score > 60:
            direction = "bullish"
        elif score < 40:
            direction = "bearish"
        else:
            direction = "neutral"

        # Niveau de confluence
        if timeframes_aligned >= 2 and abs(score - 50) > 25:
            confluence = "very_high"
        elif timeframes_aligned >= 1 and abs(score - 50) > 15:
            confluence = "high"
        elif abs(score - 50) > 10:
            confluence = "moderate"
        else:
            confluence = "low"

        # Confiance
        confidence = abs(score - 50) / 100 * (0.5 + timeframes_aligned * 0.25)

        return SwingSignal(
            direction=direction,
            score=round(score, 1),
            confidence=round(confidence, 3),
            confluence_level=confluence,
            timeframes_aligned=timeframes_aligned,
            reason="; ".join(reasons),
            indicators=indicators,
        )

    def should_exit(self, signal: SwingSignal) -> bool:
        """Vérifie si la position doit être fermée."""
        return (
            signal.confluence_level == "low"
            or signal.score < 40
            or signal.timeframes_aligned == 0
        )


__all__ = ["SwingTradingStrategy", "SwingSignal"]
