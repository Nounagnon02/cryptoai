"""
Moteur d'analyse technique central.

Orchestre l'analyse multi-timeframe complète :
1. Collecte les DataFrames OHLCV depuis le cache/DB
2. Calcule les indicateurs techniques (trend, momentum, volatility, volume)
3. Détecte les patterns de marché
4. Agrège les signaux multi-timeframe
5. Produit un score technique global (0-100)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from src.analysis.technical.aggregator import AggregatedSignal
from src.analysis.technical.patterns import PatternSignal
from src.analysis.technical.scorer import TechnicalScore, TechnicalScorer
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Timeframes supportés, du plus court au plus long
SUPPORTED_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]


class TechnicalAnalysisEngine:
    """
    Moteur d'analyse technique multi-timeframe.

    Orchestre le pipeline complet :
    Data → Indicateurs → Patterns → Agrégation → Scoring
    """

    def __init__(self) -> None:
        self.scorer = TechnicalScorer()
        self.aggregator = self.scorer.aggregator
        self.pattern_detector = self.scorer.pattern_detector
        self._running = False
        self._last_analysis: dict[str, TechnicalScore] = {}
        self._analysis_count = 0

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        """Démarre le moteur d'analyse technique."""
        logger.info(
            "TechnicalAnalysisEngine starting",
            extra={"timeframes": SUPPORTED_TIMEFRAMES},
        )
        self._running = True
        logger.info("TechnicalAnalysisEngine started")

    async def stop(self) -> None:
        """Arrête proprement le moteur."""
        logger.info(
            "TechnicalAnalysisEngine stopping",
            extra={"analyses_run": self._analysis_count},
        )
        self._running = False
        logger.info("TechnicalAnalysisEngine stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Analyse principale ────────────────────────────────────────

    async def analyze(
        self,
        symbol: str,
        data_by_timeframe: dict[str, pd.DataFrame],
    ) -> TechnicalScore:
        """
        Analyse technique complète d'un actif sur tous les timeframes disponibles.

        Args:
            symbol: Paire de trading (ex: BTC/USDT)
            data_by_timeframe: {timeframe: DataFrame OHLCV}

        Returns:
            TechnicalScore complet
        """
        if not self._running:
            logger.warning("Engine not running, starting analysis anyway")

        if not data_by_timeframe:
            logger.warning("No data provided for %s", symbol)
            return TechnicalScore(
                symbol=symbol,
                total_score=50.0,
                direction="neutral",
                warnings=["Aucune donnée disponible"],
            )

        # Vérifier qu'on a les colonnes nécessaires
        for tf, df in data_by_timeframe.items():
            required = {"open", "high", "low", "close", "volume"}
            missing = required - set(df.columns)
            if missing:
                logger.error(
                    "Missing columns for %s on %s: %s",
                    symbol, tf, missing,
                )
                # Filtrer les timeframes invalides
                data_by_timeframe = {
                    k: v for k, v in data_by_timeframe.items()
                    if required.issubset(set(v.columns))
                }
                break

        # Score complet via le scorer
        score = self.scorer.compute_full_score(symbol, data_by_timeframe)

        # Mettre en cache
        self._last_analysis[symbol] = score
        self._analysis_count += 1

        logger.debug(
            "Analysis complete for %s: score=%.1f direction=%s patterns=%d",
            symbol,
            score.total_score,
            score.direction,
            score.pattern_summary.get("patterns_count", 0),
        )

        return score

    async def analyze_batch(
        self,
        symbols_data: dict[str, dict[str, pd.DataFrame]],
    ) -> dict[str, TechnicalScore]:
        """
        Analyse technique de plusieurs actifs.

        Args:
            symbols_data: {symbol: {timeframe: DataFrame}}

        Returns:
            {symbol: TechnicalScore}
        """
        results: dict[str, TechnicalScore] = {}
        for symbol, data_by_tf in symbols_data.items():
            try:
                results[symbol] = await self.analyze(symbol, data_by_tf)
            except Exception as e:
                logger.error("Analysis failed for %s: %s", symbol, str(e))
                results[symbol] = TechnicalScore(
                    symbol=symbol,
                    total_score=50.0,
                    direction="neutral",
                    warnings=[f"Erreur d'analyse: {str(e)}"],
                )
        return results

    # ── Accès aux résultats ───────────────────────────────────────

    def get_last_score(self, symbol: str) -> TechnicalScore | None:
        """Dernier score technique calculé pour un actif."""
        return self._last_analysis.get(symbol)

    def get_aggregated_signal(self, symbol: str) -> AggregatedSignal | None:
        """Dernier signal agrégé multi-timeframe."""
        return self.aggregator.get_cached(symbol)

    def get_patterns(self, symbol: str) -> list[PatternSignal]:
        """Derniers patterns détectés pour un actif."""
        return self.pattern_detector.detected_patterns.get(symbol, [])

    def get_alignment_score(self, symbol: str) -> float:
        """Score d'alignement des timeframes (0.0 - 1.0)."""
        return self.aggregator.get_alignment_score(symbol)

    def get_statistics(self) -> dict[str, Any]:
        """Statistiques du moteur d'analyse."""
        return {
            "analyses_run": self._analysis_count,
            "symbols_cached": len(self._last_analysis),
            "is_running": self._running,
            "timeframes": SUPPORTED_TIMEFRAMES,
        }

    # ── Outils ────────────────────────────────────────────────────

    async def get_market_overview(
        self,
        symbols_data: dict[str, dict[str, pd.DataFrame]],
    ) -> dict[str, Any]:
        """
        Vue d'ensemble du marché : scores, direction, patterns.

        Utile pour le dashboard et les décisions rapides.
        """
        scores = await self.analyze_batch(symbols_data)

        bullish = sum(1 for s in scores.values() if s.direction == "bullish")
        bearish = sum(1 for s in scores.values() if s.direction == "bearish")
        neutral = sum(1 for s in scores.values() if s.direction == "neutral")

        # Top actifs par score
        sorted_scores = sorted(
            scores.items(),
            key=lambda x: x[1].total_score,
            reverse=True,
        )

        top_bullish = [
            {"symbol": s, "score": sc.total_score}
            for s, sc in sorted_scores[:5]
            if sc.direction == "bullish"
        ]
        top_bearish = [
            {"symbol": s, "score": sc.total_score}
            for s, sc in sorted_scores[-5:]
            if sc.direction == "bearish"
        ]

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_symbols": len(scores),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "market_bias": "bullish" if bullish > bearish else "bearish" if bearish > bullish else "neutral",
            "top_bullish": top_bullish,
            "top_bearish": top_bearish,
            "average_score": (
                sum(s.total_score for s in scores.values()) / len(scores)
                if scores else 50.0
            ),
        }
