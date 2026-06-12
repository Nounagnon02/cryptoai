"""
Agent IA central — Fusion multi-sources et scoring de confiance.

Agrège les signaux de TOUS les moteurs d'analyse :
- Technique (TechnicalScorer)
- Order Book (OrderBookAnalyzer)
- On-chain (OnChainScorer)
- News (NewsScorer)
- Social (SocialScorer)

Produit un score de confiance unique (0-100) avec explications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SourceSignal:
    """Signal provenant d'une source d'analyse."""

    source: str  # technical | orderbook | onchain | news | social
    score: float  # 0-100
    direction: str  # bullish | bearish | neutral
    weight: float  # Poids dans la fusion
    confidence: float  # Confiance dans ce signal (0-1)
    key_signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FusedSignal:
    """Signal fusionné final."""

    symbol: str
    final_score: float  # 0-100
    direction: str  # bullish | bearish | neutral
    confidence: float  # 0-1
    strength: float  # 0-1

    # Décomposition
    source_signals: dict[str, SourceSignal] = field(default_factory=dict)
    weights_used: dict[str, float] = field(default_factory=dict)

    # Explications
    reasoning: list[str] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    # Métadonnées
    timestamp: float = 0.0
    divergence_detected: bool = False
    consensus_level: str = "low"  # low | moderate | strong | unanimous


class FeatureFusionEngine:
    """
    Moteur de fusion multi-sources pondérée.

    Fusionne les signaux des différents moteurs d'analyse en
    un score unique, avec détection de divergence et calcul
    de consensus.
    """

    # Poids par défaut des sources (ajustables)
    DEFAULT_WEIGHTS = {
        "technical": 0.35,
        "onchain": 0.20,
        "orderbook": 0.15,
        "social": 0.15,
        "news": 0.15,
    }

    def __init__(self) -> None:
        self._weights = dict(self.DEFAULT_WEIGHTS)

    def fuse(
        self,
        symbol: str,
        signals: dict[str, SourceSignal],
        dynamic_weights: dict[str, float] | None = None,
    ) -> FusedSignal:
        """
        Fusionne les signaux de toutes les sources.

        Args:
            symbol: Actif analysé
            signals: {source: SourceSignal}
            dynamic_weights: Poids dynamiques (optionnel)

        Returns:
            Signal fusionné
        """
        weights = dynamic_weights or self._weights

        if not signals:
            return FusedSignal(
                symbol=symbol,
                final_score=50.0,
                direction="neutral",
                confidence=0.0,
                strength=0.0,
                reasoning=["Aucun signal disponible"],
            )

        # Ajuster les poids aux sources disponibles
        available = set(signals.keys())
        total_weight = sum(weights[s] for s in available if s in weights) or 1

        # Score pondéré
        weighted_score = 0.0
        weighted_confidence = 0.0
        directions: list[str] = []
        conflicts = 0

        for source, signal in signals.items():
            w = weights.get(source, 0.1) / total_weight
            weighted_score += signal.score * w
            weighted_confidence += signal.confidence * w
            directions.append(signal.direction)

        # Détection de divergence entre sources
        unique_directions = {d for d in directions if d != "neutral"}
        divergence = len(unique_directions) > 1
        conflicts = sum(1 for d in directions if d != directions[0]) if directions else 0

        # Niveau de consensus
        if len(unique_directions) <= 1:
            consensus = "unanimous"
        elif conflicts <= len(directions) * 0.25:
            consensus = "strong"
        elif conflicts <= len(directions) * 0.4:
            consensus = "moderate"
        else:
            consensus = "low"

        # Direction finale
        if weighted_score > 60:
            direction = "bullish"
        elif weighted_score < 40:
            direction = "bearish"
        else:
            direction = "neutral"

        # Force (écart par rapport au neutre)
        strength = abs(weighted_score - 50) / 50

        # Confiance finale (moyenne pondérée, pénalisée par divergence)
        final_confidence = weighted_confidence
        if divergence:
            final_confidence *= 0.7
        if direction == "neutral":
            final_confidence *= 0.5

        # Raisonnement
        reasoning = self._generate_reasoning(signals, direction, consensus, divergence)

        # Risques
        risks = []
        for _source, signal in signals.items():
            risks.extend(signal.warnings)
        if divergence:
            risks.append("Divergence entre sources d'analyse")
        if consensus == "low":
            risks.append("Faible consensus — risque de mauvais signal")

        return FusedSignal(
            symbol=symbol,
            final_score=round(weighted_score, 1),
            direction=direction,
            confidence=round(min(1.0, final_confidence), 3),
            strength=round(strength, 3),
            source_signals=signals,
            weights_used={k: v for k, v in weights.items() if k in signals},
            reasoning=reasoning,
            key_drivers=[s.key_signals[0] for s in signals.values()
                        if s.key_signals][:5],
            risks=risks[:5],
            timestamp=datetime.now(UTC).timestamp(),
            divergence_detected=divergence,
            consensus_level=consensus,
        )

    def _generate_reasoning(
        self,
        signals: dict[str, SourceSignal],
        direction: str,
        consensus: str,
        divergence: bool,
    ) -> list[str]:
        """Génère un raisonnement textuel pour la décision."""
        reasons = []

        if direction != "neutral":
            aligned = [
                f"{s.source}: {s.direction} ({s.score:.0f}/100)"
                for s in signals.values()
                if s.direction == direction
            ]
            if aligned:
                reasons.append(
                    f"Direction {direction} supportée par {len(aligned)} source(s) : "
                    + ", ".join(aligned[:3])
                )

        opposing = [
            f"{s.source}: {s.direction} ({s.score:.0f}/100)"
            for s in signals.values()
            if s.direction != direction and s.direction != "neutral"
        ]
        if opposing:
            reasons.append(f"Signaux opposés : {'; '.join(opposing[:2])}")

        if consensus == "strong" or consensus == "unanimous":
            reasons.append(f"Consensus {consensus} entre les sources")
        elif divergence:
            reasons.append("ATTENTION : les sources divergent sur la direction")

        return reasons


class ConfidenceScorer:
    """
    Calcule un score de confiance (0-100) avec analyse de
    la fiabilité de chaque source et du contexte de marché.

    Utile pour le sizing des positions.
    """

    def score(self, fused: FusedSignal) -> float:
        """
        Calcule la confiance globale dans le signal fusionné.

        Returns:
            Score 0-100 (0=pas confiance, 100=très confiant)
        """
        score = 50.0  # Neutre

        # Bonus pour consensus fort
        consensus_bonus = {
            "unanimous": 20,
            "strong": 10,
            "moderate": 0,
            "low": -10,
        }
        score += consensus_bonus.get(fused.consensus_level, 0)

        # Bonus pour force du signal
        score += fused.strength * 15

        # Bonus pour confiance moyenne des sources
        score += fused.confidence * 15

        # Pénalité pour divergence
        if fused.divergence_detected:
            score -= 15

        # Pénalité pour risques
        score -= len(fused.risks) * 5

        # Pénalité pour direction neutre
        if fused.direction == "neutral":
            score = min(score, 30)

        return max(0, min(100, round(score)))


class AIExplanationEngine:
    """
    Moteur d'explication des décisions.

    Génère des explications en langage naturel pour chaque décision,
    rendant le système transparent et auditable.
    """

    def explain_decision(
        self,
        symbol: str,
        fused: FusedSignal,
        confidence: float,
        action: str,
    ) -> str:
        """
        Génère une explication textuelle de la décision.

        Args:
            symbol: Actif
            fused: Signal fusionné
            confidence: Score de confiance
            action: Décision prise

        Returns:
            Explication en langage naturel
        """
        lines = [
            f"Décision pour {symbol}: {action.upper()}",
            f"Score global: {fused.final_score:.1f}/100 ({fused.direction})",
            f"Confiance: {confidence:.0f}/100",
            "",
            "Analyse par source:",
        ]

        for source, signal in sorted(
            fused.source_signals.items(),
            key=lambda x: fused.weights_used.get(x[0], 0),
            reverse=True,
        ):
            w = fused.weights_used.get(source, 0) * 100
            direction_icon = "▲" if signal.direction == "bullish" else "▼" if signal.direction == "bearish" else "●"
            lines.append(
                f"  {direction_icon} {source.title()} ({w:.0f}%) : "
                f"{signal.score:.0f}/100 → {signal.direction}"
            )

        if fused.reasoning:
            lines.append("")
            lines.append("Raisonnement:")
            for reason in fused.reasoning[:3]:
                lines.append(f"  • {reason}")

        if fused.risks:
            lines.append("")
            lines.append("Risques identifiés:")
            for risk in fused.risks[:3]:
                lines.append(f"  ⚠ {risk}")

        return "\n".join(lines)


class CentralAIAgent:
    """
    Agent IA central du système de trading.

    Point d'entrée unique pour toute décision :
    1. Collecte les signaux de tous les moteurs d'analyse
    2. Fusionne les signaux (Feature Fusion)
    3. Calcule la confiance
    4. Génère des explications
    """

    def __init__(self) -> None:
        self.fusion_engine = FeatureFusionEngine()
        self.confidence_scorer = ConfidenceScorer()
        self.explanation_engine = AIExplanationEngine()

        self._running = False
        self._last_decisions: dict[str, dict[str, Any]] = {}
        self._total_decisions = 0

    async def start(self) -> None:
        """Démarre l'agent IA."""
        logger.info("Central AI Agent starting")
        self._running = True
        logger.info("Central AI Agent started")

    async def stop(self) -> None:
        """Arrête l'agent IA."""
        logger.info(
            "Central AI Agent stopping",
            extra={"total_decisions": self._total_decisions},
        )
        self._running = False
        logger.info("Central AI Agent stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def analyze(
        self,
        symbol: str,
        signals: dict[str, SourceSignal],
        dynamic_weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Analyse complète : fusion → confiance → explication.

        Args:
            symbol: Actif analysé
            signals: Signaux de tous les moteurs d'analyse
            dynamic_weights: Poids dynamiques optionnels

        Returns:
            Décision complète avec explication
        """
        # Fusion
        fused = self.fusion_engine.fuse(symbol, signals, dynamic_weights)

        # Confiance
        confidence = self.confidence_scorer.score(fused)

        # Décision préliminaire (sera raffinée par Decision Engine)
        action = self._preliminary_action(fused, confidence)

        # Explication
        explanation = self.explanation_engine.explain_decision(
            symbol, fused, confidence, action
        )

        result = {
            "symbol": symbol,
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "score": fused.final_score,
            "direction": fused.direction,
            "confidence": confidence,
            "strength": fused.strength,
            "consensus": fused.consensus_level,
            "divergence": fused.divergence_detected,
            "reasoning": fused.reasoning,
            "risks": fused.risks,
            "key_drivers": fused.key_drivers,
            "explanation": explanation,
            "source_signals": {
                k: {
                    "score": v.score,
                    "direction": v.direction,
                    "weight": v.weight,
                    "confidence": v.confidence,
                    "key_signals": v.key_signals[:3],
                }
                for k, v in signals.items()
            },
        }

        self._last_decisions[symbol] = result
        self._total_decisions += 1

        return result

    def _preliminary_action(
        self,
        fused: FusedSignal,
        confidence: float,
    ) -> str:
        """
        Action préliminaire basée sur le score et la confiance.

        Actions :
        - strong_buy : score > 75, confiance > 60
        - buy : score > 60, confiance > 40
        - reinforce : déjà en position, score favorable
        - hold : score neutre ou risque élevé
        - reduce : réduire la position
        - sell : score < 40, confiance > 40
        - strong_sell : score < 25, confiance > 60
        """
        if fused.direction == "neutral" or confidence < 20:
            return "hold"

        if fused.direction == "bullish":
            if fused.final_score > 75 and confidence > 60:
                return "strong_buy"
            elif fused.final_score > 60 and confidence > 40:
                return "buy"
            elif fused.final_score > 55 and confidence > 30:
                return "reinforce"
            else:
                return "hold"
        else:  # bearish
            if fused.final_score < 25 and confidence > 60:
                return "strong_sell"
            elif fused.final_score < 40 and confidence > 40:
                return "sell"
            elif fused.final_score < 45 and confidence > 30:
                return "reduce"
            else:
                return "hold"

    def get_last_decision(self, symbol: str) -> dict[str, Any] | None:
        """Dernière décision pour un actif."""
        return self._last_decisions.get(symbol)

    def get_statistics(self) -> dict[str, Any]:
        """Statistiques de l'agent."""
        return {
            "total_decisions": self._total_decisions,
            "symbols_tracked": len(self._last_decisions),
            "is_running": self._running,
        }
