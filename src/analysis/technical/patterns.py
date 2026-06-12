"""
Détection de patterns de marché.

Identifie : breakouts, reversals, divergences, accumulations,
consolidations, bull/bear traps.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.analysis.technical import indicators as ind
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PatternSignal:
    """Signal de pattern détecté."""

    name: str
    type: str  # breakout | reversal | divergence | consolidation | accumulation | trap
    direction: str  # bullish | bearish
    strength: float  # 0.0 - 1.0
    timeframe: str
    symbol: str
    description: str = ""
    confidence: float = 0.0


class PatternDetector:
    """
    Détecte les patterns de marché sur les données OHLCV.

    Analyse multi-timeframe pour confirmer les signaux.
    """

    def __init__(self) -> None:
        self.detected_patterns: dict[str, list[PatternSignal]] = {}
        self._last_close: dict[str, float] = {}
        self._last_high: dict[str, float] = {}
        self._last_low: dict[str, float] = {}

    def analyze(self, symbol: str, df: pd.DataFrame, timeframe: str) -> list[PatternSignal]:
        """
        Analyse complète des patterns pour un symbole/timeframe.

        Args:
            symbol: Paire de trading
            df: DataFrame OHLCV
            timeframe: Timeframe analysé

        Returns:
            Liste des patterns détectés
        """
        signals: list[PatternSignal] = []

        if df.empty or len(df) < 50:
            return signals

        # Mettre à jour les derniers prix
        self._last_close[symbol] = df["close"].iloc[-1]
        self._last_high[symbol] = df["high"].iloc[-1]
        self._last_low[symbol] = df["low"].iloc[-1]

        try:
            signals.extend(self._detect_breakouts(symbol, df, timeframe))
            signals.extend(self._detect_reversals(symbol, df, timeframe))
            signals.extend(self._detect_divergences(symbol, df, timeframe))
            signals.extend(self._detect_consolidations(symbol, df, timeframe))
            signals.extend(self._detect_traps(symbol, df, timeframe))
        except Exception as e:
            logger.error("Erreur détection patterns %s: %s", symbol, str(e))

        self.detected_patterns[symbol] = signals
        return signals

    def _detect_breakouts(self, symbol: str, df: pd.DataFrame, tf: str) -> list[PatternSignal]:
        """Détecte les breakouts de support/résistance."""
        signals = []
        close, high, low = df["close"], df["high"], df["low"]
        lookback = 20

        # Résistance dynamique (plus haut des N dernières bougies)
        resistance = high.rolling(lookback).max().shift(1)
        support = low.rolling(lookback).min().shift(1)

        current = close.iloc[-1]
        prev = close.iloc[-2]

        # Breakout haussier (franchissement résistance avec volume)
        if prev <= resistance.iloc[-2] and current > resistance.iloc[-1]:
            vol_ratio = df["volume"].iloc[-1] / df["volume"].iloc[-lookback:-1].mean()
            strength = min(1.0, vol_ratio * 0.3 + 0.5)
            signals.append(PatternSignal(
                name="Breakout Haussier",
                type="breakout",
                direction="bullish",
                strength=strength,
                timeframe=tf,
                symbol=symbol,
                description=f"Prix a franchi la résistance {lookback}périodes",
                confidence=strength * 0.8,
            ))

        # Breakdown baissier
        if prev >= support.iloc[-2] and current < support.iloc[-1]:
            vol_ratio = df["volume"].iloc[-1] / df["volume"].iloc[-lookback:-1].mean()
            strength = min(1.0, vol_ratio * 0.3 + 0.5)
            signals.append(PatternSignal(
                name="Breakdown Baissier",
                type="breakout",
                direction="bearish",
                strength=strength,
                timeframe=tf,
                symbol=symbol,
                description=f"Prix a cassé le support {lookback}périodes",
                confidence=strength * 0.8,
            ))

        return signals

    def _detect_reversals(self, symbol: str, df: pd.DataFrame, tf: str) -> list[PatternSignal]:
        """Détecte les retournements de tendance."""
        signals = []
        close = df["close"]

        rsi_vals = ind.rsi(close, 14)

        current_rsi = rsi_vals.iloc[-1]
        prev_rsi = rsi_vals.iloc[-2]

        # Reversal haussier (RSI oversold + rejection bas BB)
        if current_rsi < 30 and prev_rsi < current_rsi:
            signals.append(PatternSignal(
                name="Reversal Haussier (RSI)",
                type="reversal",
                direction="bullish",
                strength=max(0.3, (35 - current_rsi) / 35),
                timeframe=tf,
                symbol=symbol,
                description=f"RSI à {current_rsi:.1f} en zone oversold, remontant",
            ))

        # Reversal baissier (RSI overbought + rejet haut BB)
        if current_rsi > 70 and prev_rsi > current_rsi:
            signals.append(PatternSignal(
                name="Reversal Baissier (RSI)",
                type="reversal",
                direction="bearish",
                strength=max(0.3, (current_rsi - 65) / 35),
                timeframe=tf,
                symbol=symbol,
                description=f"RSI à {current_rsi:.1f} en zone overbought, descendant",
            ))

        return signals

    def _detect_divergences(self, symbol: str, df: pd.DataFrame, tf: str) -> list[PatternSignal]:
        """Détecte les divergences RSI (signaux puissants)."""
        signals = []
        close = df["close"]
        rsi_vals = ind.rsi(close, 14)

        lookback = 20
        if len(close) < lookback * 2:
            return signals

        # Divergence haussière (prix plus bas, RSI plus haut)
        price_low_1 = close.iloc[-lookback*2:-lookback].min()
        price_low_2 = close.iloc[-lookback:].min()
        rsi_low_1 = rsi_vals.iloc[-lookback*2:-lookback].min()
        rsi_low_2 = rsi_vals.iloc[-lookback:].min()

        if price_low_2 < price_low_1 and rsi_low_2 > rsi_low_1:
            signals.append(PatternSignal(
                name="Divergence Haussère (RSI)",
                type="divergence",
                direction="bullish",
                strength=0.75,
                timeframe=tf,
                symbol=symbol,
                description="Prix fait des creux plus bas mais RSI plus haut",
                confidence=0.7,
            ))

        # Divergence baissière (prix plus haut, RSI plus bas)
        price_high_1 = close.iloc[-lookback*2:-lookback].max()
        price_high_2 = close.iloc[-lookback:].max()
        rsi_high_1 = rsi_vals.iloc[-lookback*2:-lookback].max()
        rsi_high_2 = rsi_vals.iloc[-lookback:].max()

        if price_high_2 > price_high_1 and rsi_high_2 < rsi_high_1:
            signals.append(PatternSignal(
                name="Divergence Baissière (RSI)",
                type="divergence",
                direction="bearish",
                strength=0.75,
                timeframe=tf,
                symbol=symbol,
                description="Prix fait des sommets plus hauts mais RSI plus bas",
                confidence=0.7,
            ))

        return signals

    def _detect_consolidations(self, symbol: str, df: pd.DataFrame, tf: str) -> list[PatternSignal]:
        """Détecte les phases de consolidation / range."""
        signals = []
        close = df["close"]

        lookback = 20
        if len(close) < lookback:
            return signals

        recent = close.iloc[-lookback:]
        range_pct = ((recent.max() - recent.min()) / recent.min()) * 100
        volatility = recent.std() / recent.mean()

        # Consolidation (range étroit)
        if range_pct < 5.0 and volatility < 0.02:
            direction = "bullish" if close.iloc[-1] > close.iloc[-lookback] else "bearish"
            signals.append(PatternSignal(
                name="Consolidation",
                type="consolidation",
                direction=direction,
                strength=max(0.3, (5.0 - range_pct) / 5.0),
                timeframe=tf,
                symbol=symbol,
                description=f"Range de {range_pct:.1f}% sur {lookback} périodes",
            ))

        # Accumulation (range bas avec volume croissant)
        if range_pct < 8.0:
            vol_trend = df["volume"].iloc[-5:].mean() / df["volume"].iloc[-lookback:-5].mean()
            if vol_trend > 1.3 and close.iloc[-1] > close.iloc[-lookback // 2]:
                signals.append(PatternSignal(
                    name="Accumulation",
                    type="accumulation",
                    direction="bullish",
                    strength=min(1.0, (vol_trend - 1.0) * 2),
                    timeframe=tf,
                    symbol=symbol,
                    description=f"Volume en hausse de {((vol_trend-1)*100):.0f}% dans range",
                ))

        return signals

    def _detect_traps(self, symbol: str, df: pd.DataFrame, tf: str) -> list[PatternSignal]:
        """Détecte les bull traps et bear traps."""
        signals = []
        close, high, low = df["close"], df["high"], df["low"]

        if len(close) < 30:
            return signals

        # Bull Trap : breakout au-dessus résistance → retour rapide en dessous
        res_20 = high.rolling(20).max().shift(1)
        if len(close) >= 3 and (close.iloc[-3] > res_20.iloc[-3] and
                close.iloc[-2] > res_20.iloc[-2] and
                close.iloc[-1] < res_20.iloc[-1]):
            signals.append(PatternSignal(
                name="Bull Trap",
                type="trap",
                direction="bearish",
                strength=0.7,
                timeframe=tf,
                symbol=symbol,
                description="Faux breakout haussier, prix retourné sous résistance",
            ))

        # Bear Trap : breakdown sous support → retour rapide au-dessus
        sup_20 = low.rolling(20).min().shift(1)
        if len(close) >= 3 and (close.iloc[-3] < sup_20.iloc[-3] and
                close.iloc[-2] < sup_20.iloc[-2] and
                close.iloc[-1] > sup_20.iloc[-1]):
            signals.append(PatternSignal(
                name="Bear Trap",
                type="trap",
                direction="bullish",
                strength=0.7,
                timeframe=tf,
                symbol=symbol,
                description="Faux breakdown baissier, prix retourné au-dessus support",
            ))

        return signals

    def get_summary(self, symbol: str) -> dict:
        """Résumé des patterns détectés pour un symbole."""
        patterns = self.detected_patterns.get(symbol, [])
        if not patterns:
            return {"symbol": symbol, "patterns_count": 0, "signals": []}

        bullish = [p for p in patterns if p.direction == "bullish"]
        bearish = [p for p in patterns if p.direction == "bearish"]

        return {
            "symbol": symbol,
            "patterns_count": len(patterns),
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "average_strength": (
                sum(p.strength for p in patterns) / len(patterns)
                if patterns else 0
            ),
            "signals": [
                {
                    "name": p.name,
                    "type": p.type,
                    "direction": p.direction,
                    "strength": p.strength,
                    "timeframe": p.timeframe,
                    "description": p.description,
                }
                for p in sorted(patterns, key=lambda x: x.strength, reverse=True)[:5]
            ],
        }
