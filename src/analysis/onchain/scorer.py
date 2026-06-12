"""
Score on-chain composite.

Agrège les métriques on-chain (whales, flux exchange, réseau)
en un score unique de 0 à 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.onchain.exchange_flow import ExchangeFlowAnalyzer, ExchangeFlowMetrics
from src.analysis.onchain.whale_tracker import WhaleMetrics, WhaleTracker
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OnChainScore:
    """Score on-chain global pour un actif."""

    symbol: str
    total_score: float  # 0-100
    direction: str  # bullish | bearish | neutral

    # Sous-scores
    whale_score: float = 50.0
    exchange_flow_score: float = 50.0
    network_score: float = 50.0  # Pour futures métriques réseau

    # Composants
    whale_metrics: WhaleMetrics | None = None
    exchange_metrics: ExchangeFlowMetrics | None = None

    # Signaux
    key_signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class OnChainScorer:
    """
    Calcule un score on-chain composite (0-100).

    Composants :
    - Whale activity (40%) : mouvements de gros porteurs
    - Exchange flows (40%) : entrées/sorties des exchanges
    - Network health (20%) : métriques réseau (réservé futur)
    """

    WEIGHTS = {
        "whale": 0.40,
        "exchange_flow": 0.40,
        "network": 0.20,
    }

    def __init__(self) -> None:
        self.whale_tracker = WhaleTracker()
        self.exchange_flow_analyzer = ExchangeFlowAnalyzer()

    def compute_score(
        self,
        symbol: str,
        whale_metrics: WhaleMetrics | None = None,
        exchange_metrics: ExchangeFlowMetrics | None = None,
    ) -> OnChainScore:
        """
        Calcule le score on-chain complet.

        Args:
            symbol: Actif analysé
            whale_metrics: Métriques whales (calculées si non fournies)
            exchange_metrics: Métriques flux exchange (calculées si non fournies)

        Returns:
            OnChainScore complet
        """
        # Récupérer ou calculer les métriques
        wm = whale_metrics or self.whale_tracker.get_metrics(symbol)
        em = exchange_metrics or self.exchange_flow_analyzer.get_metrics(symbol)

        # Scores par composant
        whale_score = self._score_whale(wm)
        exchange_score = self._score_exchange_flow(em)

        # Score pondéré
        total = (
            whale_score * self.WEIGHTS["whale"]
            + exchange_score * self.WEIGHTS["exchange_flow"]
            + 50 * self.WEIGHTS["network"]  # Network score par défaut
        )

        # Direction et signaux
        direction = self._determine_direction(whale_score, exchange_score)
        signals, warnings = self._extract_signals(wm, em, whale_score, exchange_score)

        return OnChainScore(
            symbol=symbol,
            total_score=round(total, 1),
            direction=direction,
            whale_score=round(whale_score, 1),
            exchange_flow_score=round(exchange_score, 1),
            whale_metrics=wm,
            exchange_metrics=em,
            key_signals=signals,
            warnings=warnings,
        )

    def _score_whale(self, metrics: WhaleMetrics | None) -> float:
        """Score whale (0-100). 0 = bearish extrême, 100 = bullish extrême."""
        if not metrics:
            return 50.0

        score = 50.0

        # Whale confidence (-1 à +1) → contribution ±20
        score += metrics.whale_confidence * 20

        # Accumulation vs distribution
        if metrics.accumulation_score > metrics.distribution_score:
            score += min(15, (metrics.accumulation_score - metrics.distribution_score) * 0.3)
        else:
            score -= min(15, (metrics.distribution_score - metrics.accumulation_score) * 0.3)

        # Volume anormal
        if metrics.total_volume_24h > 50_000_000:
            score += 5
        elif metrics.large_transactions_24h > 20:
            score += 3

        return max(0, min(100, score))

    def _score_exchange_flow(self, metrics: ExchangeFlowMetrics | None) -> float:
        """Score flux exchange (0-100)."""
        if not metrics:
            return 50.0

        score = 50.0

        # Flux net 24h normalisé
        net_flow_m = metrics.net_flow_24h / 1_000_000  # en millions
        flow_score = max(-20, min(20, -net_flow_m * 2))
        score += flow_score

        # Ratio inflow/outflow
        if metrics.inflow_outflow_ratio < 0.5:
            score += 10
        elif metrics.inflow_outflow_ratio > 2:
            score -= 10

        return max(0, min(100, score))

    def _determine_direction(
        self,
        whale_score: float,
        exchange_score: float,
    ) -> str:
        """Détermine la direction globale."""
        avg = (whale_score + exchange_score) / 2
        if avg > 60:
            return "bullish"
        elif avg < 40:
            return "bearish"
        return "neutral"

    def _extract_signals(
        self,
        wm: WhaleMetrics | None,
        em: ExchangeFlowMetrics | None,
        _whale_score: float,
        _exchange_score: float,
    ) -> tuple[list[str], list[str]]:
        """Extrait les signaux et avertissements."""
        signals = []
        warnings = []

        if wm:
            if wm.accumulation_score > 60:
                signals.append(f"Whales en accumulation (score: {wm.accumulation_score:.0f}/100)")
            if wm.distribution_score > 60:
                signals.append(f"Whales en distribution (score: {wm.distribution_score:.0f}/100)")
            warnings.extend(wm.warnings)

        if em:
            if em.signal == "bullish":
                signals.append("Flux exchange haussier (sorties > entrées)")
            elif em.signal == "bearish":
                signals.append("Flux exchange baissier (entrées > sorties)")
            warnings.extend(em.warnings)

        return signals[:4], warnings[:4]
