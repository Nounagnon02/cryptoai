"""
Score technique global.

Fusionne les indicateurs techniques et les patterns en un score
unique de 0 à 100 (ou -100 à +100 pour la direction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.analysis.technical.aggregator import MultiTimeframeAggregator
from src.analysis.technical.patterns import PatternDetector, PatternSignal
from src.utils.logging import get_logger

logger = get_logger(__name__)

FAMILY_WEIGHTS = {
    "trend": 0.35,
    "momentum": 0.25,
    "volatility": 0.15,
    "volume": 0.15,
    "pattern": 0.10,
}


@dataclass
class TechnicalScore:
    """Score technique complet pour un actif."""

    symbol: str
    total_score: float  # 0-100
    direction: str  # bullish | bearish | neutral
    family_scores: dict[str, float] = field(default_factory=dict)
    pattern_summary: dict[str, Any] = field(default_factory=dict)
    aggregated_signal: Any = None
    key_signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TechnicalScorer:
    """
    Calcule un score technique global (0-100) pour chaque actif.

    Agrège par famille d'indicateurs puis pondère :
    - Trend (35%)  : tendance générale
    - Momentum (25%) : force du mouvement
    - Volatility (15%) : conditions de volatilité
    - Volume (15%) : confirmation par le volume
    - Pattern (10%) : patterns détectés
    """

    def __init__(self) -> None:
        self.aggregator = MultiTimeframeAggregator()
        self.pattern_detector = PatternDetector()

    def compute_full_score(
        self,
        symbol: str,
        data_by_timeframe: dict[str, pd.DataFrame],
    ) -> TechnicalScore:
        """
        Calcule le score technique complet multi-timeframe.

        Args:
            symbol: Paire de trading
            data_by_timeframe: {timeframe: DataFrame OHLCV}

        Returns:
            TechnicalScore complet avec explications
        """
        family_scores_all: dict[str, list[float]] = {f: [] for f in FAMILY_WEIGHTS}
        scores_by_tf: dict[str, float] = {}
        conf_by_tf: dict[str, float] = {}

        for tf, df in data_by_timeframe.items():
            if df.empty or len(df) < 30:
                continue

            # Score par famille pour ce timeframe
            tf_family_scores = self._score_timeframe(df)
            for family, score in tf_family_scores.items():
                if family in family_scores_all:
                    family_scores_all[family].append(score)

            # Pattern detection
            patterns = self.pattern_detector.analyze(symbol, df, tf)

            # Score composite pour ce timeframe (-100 à +100)
            tf_score = self._compute_timeframe_score(tf_family_scores, patterns)
            scores_by_tf[tf] = tf_score

            # Confiance basée sur la qualité des données
            conf_by_tf[tf] = min(1.0, len(df) / 200)

        # Agrégation multi-timeframe
        aggregated = self.aggregator.aggregate(symbol, scores_by_tf, conf_by_tf)

        # Scores finaux par famille (moyenne pondérée)
        final_family_scores: dict[str, float] = {}
        for family, scores in family_scores_all.items():
            if scores:
                final_family_scores[family] = sum(scores) / len(scores)
            else:
                final_family_scores[family] = 50.0

        # Score total (0-100)
        total_score = sum(
            final_family_scores.get(family, 50) * weight
            for family, weight in FAMILY_WEIGHTS.items()
        )

        # Mapping ±100 → 0-100
        direction = aggregated.direction
        if direction == "bearish":
            total_score = max(0, min(100, total_score * 0.6))

        # Signaux clés
        key_signals = self._extract_key_signals(
            final_family_scores, aggregated, symbol
        )

        # Pattern summary
        pattern_info = self.pattern_detector.get_summary(symbol)

        return TechnicalScore(
            symbol=symbol,
            total_score=round(total_score, 1),
            direction=direction,
            family_scores={k: round(v, 1) for k, v in final_family_scores.items()},
            pattern_summary=pattern_info,
            aggregated_signal=aggregated,
            key_signals=key_signals,
            warnings=["Timeframes en divergence"] if aggregated.divergence else [],
        )

    def _score_timeframe(self, df: pd.DataFrame) -> dict[str, float]:
        """Score par famille d'indicateurs pour un timeframe (0-100)."""
        from src.analysis.technical import indicators as ind

        scores: dict[str, float] = {}
        close, volume = df["close"], df["volume"]

        # Trend score (EMA, MACD, ADX)
        try:
            ema_9 = ind.ema(close, 9)
            ema_21 = ind.ema(close, 21)
            ema_50 = ind.ema(close, 50)

            trend_bullish = 0
            trend_bearish = 0
            if len(close) > 1:
                if ema_9.iloc[-1] > ema_21.iloc[-1] > ema_50.iloc[-1]:
                    trend_bullish += 2
                if close.iloc[-1] > ema_9.iloc[-1]:
                    trend_bullish += 1
                if ema_9.iloc[-1] > ema_21.iloc[-1]:
                    trend_bullish += 1

                if ema_9.iloc[-1] < ema_21.iloc[-1] < ema_50.iloc[-1]:
                    trend_bearish += 2
                if close.iloc[-1] < ema_9.iloc[-1]:
                    trend_bearish += 1
                if ema_9.iloc[-1] < ema_21.iloc[-1]:
                    trend_bearish += 1

            total = trend_bullish + trend_bearish
            trend_score = 50 + (trend_bullish - trend_bearish) * (50 / max(total, 1))
            scores["trend"] = max(0, min(100, trend_score))
        except Exception:
            scores["trend"] = 50.0

        # Momentum score (RSI, Stoch RSI)
        try:
            rsi_val = ind.rsi(close, 14)
            current_rsi = rsi_val.iloc[-1] if not rsi_val.empty else 50

            if current_rsi < 30:
                momentum_score = 20  # Oversold (potentiel haussier)
            elif current_rsi > 70:
                momentum_score = 80  # Overbought (potentiel baissier)
            else:
                momentum_score = 50 + (current_rsi - 50) * 0.5

            scores["momentum"] = max(0, min(100, momentum_score))
        except Exception:
            scores["momentum"] = 50.0

        # Volatility score (BB width, ATR)
        try:
            bb = ind.bollinger_bands(close)
            bb_width = bb["bb_width"].iloc[-1] if not bb.empty else 0
            # BB width élevé = volatilité haute
            vol_score = 50 + min(50, bb_width * 200) if pd.notna(bb_width) else 50
            scores["volatility"] = max(0, min(100, vol_score))
        except Exception:
            scores["volatility"] = 50.0

        # Volume score (OBV trend)
        try:
            obv_val = ind.obv(close, volume)
            if len(obv_val) > 5:
                obv_trend = obv_val.iloc[-1] > obv_val.iloc[-5]
                # Vérifier divergence OBV/prix
                price_up = close.iloc[-1] > close.iloc[-5]
                if obv_trend and price_up:
                    vol_score = 75  # Confirmation haussière
                elif not obv_trend and not price_up:
                    vol_score = 25  # Confirmation baissière
                elif obv_trend and not price_up:
                    vol_score = 60  # Divergence positive
                else:
                    vol_score = 40  # Divergence négative
            else:
                vol_score = 50
            scores["volume"] = max(0, min(100, vol_score))
        except Exception:
            scores["volume"] = 50.0

        # Reset pattern score — sera enrichi par pattern detector
        scores["pattern"] = 50.0

        return scores

    def _compute_timeframe_score(
        self,
        family_scores: dict[str, float],
        patterns: list[PatternSignal],
    ) -> float:
        """Score composite pour un timeframe (-100 à +100)."""
        # Direction weighted score
        weighted = sum(
            (family_scores.get(f, 50) - 50) * FAMILY_WEIGHTS.get(f, 0)
            for f in FAMILY_WEIGHTS
        )

        # Ajustement par patterns
        pattern_adj = 0.0
        for p in patterns[-3:]:  # Top 3 patterns
            sign = 1 if p.direction == "bullish" else -1
            pattern_adj += sign * p.strength * 15

        total = weighted + pattern_adj
        return max(-100, min(100, total))

    def _extract_key_signals(
        self,
        family_scores: dict[str, float],
        aggregated: Any,
        _symbol: str,
    ) -> list[str]:
        """Extrait les signaux clés pour l'explication."""
        signals = []

        if aggregated.direction == "bullish":
            signals.append(f"Tendance générale haussière (score: {aggregated.final_score:+.0f})")
        elif aggregated.direction == "bearish":
            signals.append(f"Tendance générale baissière (score: {aggregated.final_score:+.0f})")

        for family, score in sorted(family_scores.items(), key=lambda x: FAMILY_WEIGHTS.get(x[0], 0), reverse=True):
            if score > 65:
                signals.append(f"{family.title()} favorable ({score:.0f}/100)")
            elif score < 35:
                signals.append(f"{family.title()} défavorable ({score:.0f}/100)")

        if aggregated.strong_consensus:
            signals.append("Fort consensus multi-timeframe")

        # Limiter
        return signals[:6]
