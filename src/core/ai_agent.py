"""
Agent IA central — Fusion multi-sources avec calibration de confiance.

Agrège les signaux de TOUS les moteurs d'analyse :
- Technique (TechnicalScorer)
- Order Book (OrderBookAnalyzer)
- On-chain (OnChainScorer)
- News (NewsScorer)
- Social (SocialScorer)

v2 — Améliorations :
- SignalQualityTracker : tracking de qualité par source (accuracy, Brier, MAE)
- CalibratedConfidenceScorer : calibration par bins avec historique réel
- Poids adaptatifs basés sur la performance récente de chaque source
- Détection de divergence statistique (variance directionnelle)
- Adaptation au régime de marché (trending, ranging, volatile)
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALIBRATION_BINS: int = 10  # 0-10, 10-20, ..., 90-100
QUALITY_WINDOW: int = 100   # Rolling window for source quality tracking
QUALITY_STORE_PATH: Path = Path("data/ai_quality.json")
MIN_SIGNALS_FOR_ADAPTIVE: int = 10

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


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
    confidence: float  # 0-1 (calibrated)
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
    market_regime: str = "unknown"  # trending_up | trending_down | ranging | volatile | calm


# ---------------------------------------------------------------------------
# Signal Quality Tracker
# ---------------------------------------------------------------------------


class _CalibrationBin:
    """Un bin de calibration avec tracking du taux de succès réel."""

    def __init__(self, bin_low: float, bin_high: float) -> None:
        self.bin_low = bin_low
        self.bin_high = bin_high
        self.count: int = 0
        self.successes: int = 0

    @property
    def actual_success_rate(self) -> float:
        if self.count == 0:
            return 0.5  # Prior non-informatif
        return self.successes / self.count

    @property
    def expected_success_rate(self) -> float:
        """Taux attendu basé sur le milieu du bin."""
        return (self.bin_low + self.bin_high) / 200.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_low": self.bin_low,
            "bin_high": self.bin_high,
            "count": self.count,
            "successes": self.successes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _CalibrationBin:
        return cls(bin_low=data["bin_low"], bin_high=data["bin_high"]).set(
            data["count"], data["successes"]
        )

    def set(self, count: int, successes: int) -> _CalibrationBin:
        self.count = count
        self.successes = successes
        return self


class SignalQualityTracker:
    """
    Traque la qualité de chaque source de signal au fil du temps.

    Métriques suivies par rolling window :
    - Direction accuracy : % de fois où la direction prédite était correcte
    - Brier score : erreur quadratique moyenne (calibration probability)
    - Mean Absolute Error entre score prédit et outcome réel
    - Calibration par bins (taux de succès réel par plage de score)
    """

    def __init__(self, window_size: int = QUALITY_WINDOW) -> None:
        self._window_size = window_size
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._cumulative: dict[str, dict[str, float]] = {}
        self._bins: dict[str, list[_CalibrationBin]] = {}

    # ---- Recording ----

    def record_prediction(
        self,
        source: str,
        predicted_direction: str,
        predicted_score: float,
        actual_direction: str | None = None,
        actual_return_sign: float | None = None,
    ) -> None:
        """Enregistre une prédiction pour tracking futur."""
        if source not in self._history:
            self._history[source] = deque(maxlen=self._window_size)
            self._cumulative[source] = {
                "total": 0, "correct": 0, "brier_sum": 0.0, "mae_sum": 0.0,
            }

        entry = {
            "predicted_direction": predicted_direction,
            "predicted_score": predicted_score,
            "actual_direction": actual_direction,
            "actual_return_sign": actual_return_sign,
            "timestamp": datetime.now(UTC).timestamp(),
        }
        self._history[source].append(entry)

        if actual_direction is not None:
            cum = self._cumulative[source]
            cum["total"] += 1
            if predicted_direction == actual_direction:
                cum["correct"] += 1

            predicted_prob = predicted_score / 100.0
            actual_outcome = 1.0 if (actual_return_sign is not None and actual_return_sign > 0) else 0.0
            cum["brier_sum"] += (predicted_prob - actual_outcome) ** 2
            cum["mae_sum"] += abs(predicted_score / 100.0 - actual_outcome)

            self._update_calibration_bin(source, predicted_score, actual_outcome)

    def _update_calibration_bin(self, source: str, score: float, outcome: float) -> None:
        if source not in self._bins:
            self._bins[source] = [
                _CalibrationBin(i * (100 / CALIBRATION_BINS), (i + 1) * (100 / CALIBRATION_BINS))
                for i in range(CALIBRATION_BINS)
            ]
        idx = min(int(score / (100 / CALIBRATION_BINS)), CALIBRATION_BINS - 1)
        cbin = self._bins[source][idx]
        cbin.count += 1
        if outcome > 0.5:
            cbin.successes += 1

    # ---- Metrics ----

    def get_source_metrics(self, source: str) -> dict[str, float]:
        """Retourne les métriques de qualité pour une source donnée."""
        cum = self._cumulative.get(source, {})
        total = max(cum.get("total", 0), 1)

        direction_accuracy = cum.get("correct", 0) / total if total > 0 else 0.5
        brier_score = cum.get("brier_sum", 0.0) / total if total > 0 else 0.25
        mae = cum.get("mae_sum", 0.0) / total if total > 0 else 0.5
        cal_score = self._calibration_score(source)

        quality = (
            direction_accuracy * 0.35
            + (1.0 - brier_score) * 0.25
            + (1.0 - mae) * 0.25
            + cal_score * 0.15
        )
        quality = max(0.1, min(1.0, quality))

        return {
            "direction_accuracy": round(direction_accuracy, 3),
            "brier_score": round(brier_score, 3),
            "mae": round(mae, 3),
            "calibration_score": round(cal_score, 3),
            "quality_score": round(quality, 3),
            "total_predictions": int(total),
            "recent_count": len(self._history.get(source, [])),
        }

    def _calibration_score(self, source: str) -> float:
        bins = self._bins.get(source, [])
        if not bins:
            return 0.5
        total_count = sum(b.count for b in bins)
        if total_count < 5:
            return 0.5

        weighted_error = 0.0
        for cbin in bins:
            if cbin.count > 0:
                weight = cbin.count / total_count
                expected_prob = (cbin.bin_low + cbin.bin_high) / 200.0
                weighted_error += weight * abs(expected_prob - cbin.actual_success_rate)
        return max(0.0, 1.0 - weighted_error * 2)

    # ---- Adaptive Weights ----

    def get_adaptive_weights(
        self,
        available_sources: set[str],
        base_weights: dict[str, float],
    ) -> dict[str, float]:
        """
        Calcule les poids adaptatifs basés sur la qualité de chaque source.
        Blend 60% base weights + 40% quality-adjusted.
        """
        if not available_sources:
            return dict(base_weights)

        quality_scores: dict[str, float] = {}
        for src in available_sources:
            metrics = self.get_source_metrics(src)
            quality_scores[src] = metrics["quality_score"]

        min_q = min(quality_scores.values()) if quality_scores else 0.5
        max_q = max(quality_scores.values()) if quality_scores else 0.5
        q_range = max(max_q - min_q, 0.01)

        adaptive: dict[str, float] = {}
        total = 0.0
        for src in available_sources:
            base_w = base_weights.get(src, 1.0 / max(len(available_sources), 1))
            q_norm = (quality_scores[src] - min_q) / q_range
            q_factor = 0.5 + 0.5 * q_norm  # 0.5–1.0
            adaptive[src] = base_w * q_factor
            total += adaptive[src]

        if total > 0:
            adaptive = {k: v / total for k, v in adaptive.items()}
        return adaptive

    # ---- Calibrated Confidence ----

    def get_calibrated_confidence(self, source: str, raw_score: float) -> float:
        """
        Ajuste la confiance d'un score en fonction de la calibration historique.
        Blend 40% raw expected + 60% actual success rate.
        """
        bins = self._bins.get(source, [])
        if not bins:
            return raw_score / 100.0
        idx = min(int(raw_score / (100 / CALIBRATION_BINS)), CALIBRATION_BINS - 1)
        cbin = bins[idx]
        if cbin.count < 5:
            return raw_score / 100.0
        expected = max(raw_score / 100.0, 0.01)
        actual = max(cbin.actual_success_rate, 0.01)
        return min(1.0, max(0.01, expected * 0.4 + actual * 0.6))

    # ---- Persistence ----

    def export_state(self) -> dict[str, Any]:
        return {
            "cumulative": {src: dict(data) for src, data in self._cumulative.items()},
            "bins": {
                src: [b.to_dict() for b in bins]
                for src, bins in self._bins.items()
            },
        }

    def import_state(self, state: dict[str, Any]) -> None:
        if "cumulative" in state:
            for src, data in state["cumulative"].items():
                if src not in self._cumulative:
                    self._cumulative[src] = {"total": 0, "correct": 0, "brier_sum": 0.0, "mae_sum": 0.0}
                self._cumulative[src].update(data)
        if "bins" in state:
            for src, bins_data in state["bins"].items():
                self._bins[src] = [_CalibrationBin.from_dict(b) for b in bins_data]

    def save(self, path: Path = QUALITY_STORE_PATH) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.export_state(), indent=2))
        except Exception as exc:
            logger.warning("Failed to save AI quality state: %s", exc)

    def load(self, path: Path = QUALITY_STORE_PATH) -> bool:
        try:
            if path.exists():
                state = json.loads(path.read_text())
                self.import_state(state)
                logger.info("AI quality state loaded (%d sources)", len(state.get("cumulative", {})))
                return True
        except Exception as exc:
            logger.warning("Failed to load AI quality state: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Feature Fusion Engine (Enhanced v2)
# ---------------------------------------------------------------------------


class FeatureFusionEngine:
    """
    Moteur de fusion multi-sources avec calibration et poids adaptatifs.

    Améliorations vs v1 :
    - Poids adaptatifs basés sur la qualité historique des sources
    - Détection statistique de divergence (variance directionnelle)
    - Calibration de confiance par bins
    - Adaptation au régime de marché
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "technical": 0.35,
        "onchain": 0.20,
        "orderbook": 0.15,
        "social": 0.15,
        "news": 0.15,
    }

    def __init__(self, quality_tracker: SignalQualityTracker | None = None) -> None:
        self._weights = dict(self.DEFAULT_WEIGHTS)
        self._tracker = quality_tracker or SignalQualityTracker()

    @staticmethod
    def detect_market_regime(
        ohlcv_close: list[float],
    ) -> str:
        """
        Détecte le régime de marché actuel à partir des prix de clôture.

        Utilise :
        - Volatilité récente (écart-type des returns)
        - Direction / pente de la tendance (régression simple)
        """
        if len(ohlcv_close) < 20:
            return "normal"

        closes = ohlcv_close[-20:]
        n = len(closes)

        # Tendance via pente de régression simple
        x_mean = (n - 1) / 2
        y_mean = sum(closes) / n
        numerator = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0
        norm_slope = slope / (y_mean + 1e-10) * 100

        # Volatilité
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(1, n)]
        volatility = math.sqrt(sum(r ** 2 for r in returns) / len(returns)) if returns else 0.0

        if volatility > 4.0:
            return "volatile"
        if volatility < 0.5:
            return "calm"
        if abs(norm_slope) > 0.3:
            return "trending_up" if norm_slope > 0 else "trending_down"
        if volatility < 2.0:
            return "ranging"
        return "normal"

    def fuse(
        self,
        symbol: str,
        signals: dict[str, SourceSignal],
        dynamic_weights: dict[str, float] | None = None,
        market_regime: str = "normal",
        use_adaptive_weights: bool = True,
    ) -> FusedSignal:
        """
        Fusionne les signaux de toutes les sources avec calibration.

        Args:
            symbol: Actif analysé
            signals: {source: SourceSignal}
            dynamic_weights: Poids manuels (override tout)
            market_regime: Régime de marché détecté
            use_adaptive_weights: Activer les poids adaptatifs

        Returns:
            Signal fusionné calibré
        """
        if not signals:
            return FusedSignal(
                symbol=symbol,
                final_score=50.0,
                direction="neutral",
                confidence=0.0,
                strength=0.0,
                reasoning=["Aucun signal disponible"],
                market_regime=market_regime,
            )

        # ── 1. Determine weights ──
        if dynamic_weights:
            effective_weights = dict(dynamic_weights)
        elif use_adaptive_weights:
            effective_weights = self._tracker.get_adaptive_weights(
                set(signals.keys()), self._weights
            )
        else:
            effective_weights = dict(self._weights)

        available = set(signals.keys())
        raw_total = sum(effective_weights.get(s, 0.0) for s in available) or 1.0
        normalized_weights = {
            s: effective_weights.get(s, 0.1) / raw_total for s in available
        }

        # ── 2. Weighted score fusion ──
        weighted_score = 0.0
        weighted_confidence = 0.0
        directions: list[str] = []

        for source, signal in signals.items():
            w = normalized_weights.get(source, 1.0 / max(len(signals), 1))
            cal_conf = self._tracker.get_calibrated_confidence(source, signal.score)
            weighted_score += signal.score * w
            weighted_confidence += cal_conf * w
            directions.append(signal.direction)

        # ── 3. Statistical divergence detection ──
        non_neutral_dirs = [d for d in directions if d != "neutral"]
        unique_dirs = set(non_neutral_dirs)
        divergence = len(unique_dirs) > 1

        severe_divergence = False
        if divergence and len(signals) >= 2:
            adjusted_scores: list[float] = []
            for s in signals.values():
                if s.direction == "bullish":
                    adjusted_scores.append(s.score)
                elif s.direction == "bearish":
                    adjusted_scores.append(100 - s.score)
                else:
                    adjusted_scores.append(50)
            score_spread = max(adjusted_scores) - min(adjusted_scores)
            severe_divergence = score_spread > 30

        # ── 4. Consensus level ──
        if non_neutral_dirs:
            dir_counts: dict[str, int] = {}
            for d in non_neutral_dirs:
                dir_counts[d] = dir_counts.get(d, 0) + 1
            majority_count = max(dir_counts.values())
            agreement_ratio = majority_count / max(len(non_neutral_dirs), 1)

            if len(unique_dirs) == 1 and non_neutral_dirs and len(non_neutral_dirs) == len(signals):
                consensus = "unanimous"
            elif agreement_ratio >= 0.75:
                consensus = "strong"
            elif agreement_ratio >= 0.5:
                consensus = "moderate"
            else:
                consensus = "low"
            direction_agreement = agreement_ratio
        else:
            consensus = "strong"  # all neutral
            direction_agreement = 1.0

        # ── 5. Direction finale ──
        if weighted_score > 60:
            direction = "bullish"
        elif weighted_score < 40:
            direction = "bearish"
        else:
            direction = "neutral"

        # Strong consensus override
        if consensus in ("unanimous", "strong") and non_neutral_dirs:
            majority_dir = max(set(non_neutral_dirs), key=non_neutral_dirs.count)
            if majority_dir == "bullish" and weighted_score < 45:
                weighted_score = 55
                direction = "bullish"
            elif majority_dir == "bearish" and weighted_score > 55:
                weighted_score = 45
                direction = "bearish"

        # ── 6. Strength ──
        strength = abs(weighted_score - 50) / 50

        # ── 7. Confidence ──
        consensus_factors = {
            "unanimous": 1.0, "strong": 0.85, "moderate": 0.65, "low": 0.40,
        }
        consensus_factor = consensus_factors.get(consensus, 0.5)

        if divergence:
            weighted_confidence *= 0.75
            if severe_divergence:
                weighted_confidence *= 0.70
        if direction == "neutral":
            weighted_confidence *= 0.50

        final_confidence = weighted_confidence * consensus_factor * direction_agreement
        final_confidence = min(1.0, max(0.0, final_confidence))

        # ── 8. Reasoning ──
        reasoning = self._generate_reasoning(
            signals, direction, consensus, divergence, severe_divergence,
            market_regime, normalized_weights,
        )

        # ── 9. Risks ──
        risks: list[str] = []
        for _source, signal in signals.items():
            risks.extend(signal.warnings)
        if severe_divergence:
            risks.append("Divergence SÉVÈRE entre sources — signal non fiable")
        elif divergence:
            risks.append("Divergence modérée entre sources")
        if consensus == "low":
            risks.append("Faible consensus — risque élevé de faux signal")
        if market_regime == "volatile":
            risks.append("Marché volatile — signaux moins fiables")

        return FusedSignal(
            symbol=symbol,
            final_score=round(weighted_score, 1),
            direction=direction,
            confidence=round(final_confidence, 3),
            strength=round(strength, 3),
            source_signals=signals,
            weights_used=normalized_weights,
            reasoning=reasoning,
            key_drivers=[s.key_signals[0] for s in signals.values() if s.key_signals][:5],
            risks=risks[:5],
            timestamp=datetime.now(UTC).timestamp(),
            divergence_detected=divergence,
            consensus_level=consensus,
            market_regime=market_regime,
        )

    def _generate_reasoning(
        self,
        signals: dict[str, SourceSignal],
        direction: str,
        consensus: str,
        divergence: bool,
        severe_divergence: bool,
        market_regime: str,
        weights: dict[str, float],
    ) -> list[str]:
        """Génère un raisonnement textuel pour la décision."""
        reasons: list[str] = []

        regime_labels = {
            "trending_up": "Marché en tendance haussière",
            "trending_down": "Marché en tendance baissière",
            "ranging": "Marché en range (consolidation)",
            "volatile": "⚠️ Marché très volatile",
            "calm": "Marché calme (faible volatilité)",
        }
        label = regime_labels.get(market_regime)
        if label:
            reasons.append(label)

        if direction != "neutral":
            aligned = [
                f"{s.source}: {s.direction} ({s.score:.0f}/100, w={weights.get(s.source, 0)*100:.0f}%)"
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

        if consensus in ("unanimous", "strong"):
            reasons.append(f"Consensus {consensus} entre les sources — signal robuste")
        elif severe_divergence:
            reasons.append("⚠️ DIVERGENCE SÉVÈRE — ne pas trader sur ce signal")
        elif divergence:
            reasons.append("ATTENTION : sources divergentes — confiance réduite")

        sources_with_history = [
            src for src in signals
            if self._tracker.get_source_metrics(src)["total_predictions"] > 0
        ]
        if sources_with_history:
            best_source = max(
                sources_with_history,
                key=lambda s: self._tracker.get_source_metrics(s)["quality_score"],
            )
            q_metrics = self._tracker.get_source_metrics(best_source)
            reasons.append(
                f"Source la plus fiable : {best_source} "
                f"(précision {q_metrics['direction_accuracy']*100:.0f}%)"
            )

        return reasons


# ---------------------------------------------------------------------------
# Calibrated Confidence Scorer
# ---------------------------------------------------------------------------


class ConfidenceScorer:
    """
    Score de confiance calibré utilisant l'historique de qualité.

    Remplace le scoring ad-hoc v1 par une approche basée sur :
    1. Calibration bins historiques
    2. Force du consensus
    3. Régime de marché
    4. Pénalités de risque
    """

    def __init__(self, quality_tracker: SignalQualityTracker | None = None) -> None:
        self._tracker = quality_tracker or SignalQualityTracker()

    def score(
        self,
        fused: FusedSignal,
        market_regime: str = "normal",
    ) -> float:
        """
        Calcule la confiance calibrée (0-100) dans le signal fusionné.

        Args:
            fused: Signal fusionné
            market_regime: Régime de marché

        Returns:
            Score de confiance 0-100
        """
        # ── 1. Base confidence from calibrated sources ──
        calibrated_confidences: list[float] = []
        total_weight = 0.0

        for src, signal in fused.source_signals.items():
            w = fused.weights_used.get(src, 0.1)
            calibrated = self._tracker.get_calibrated_confidence(src, signal.score)
            calibrated_confidences.append(calibrated * w)
            total_weight += w

        base_confidence = (
            sum(calibrated_confidences) / total_weight if total_weight > 0 else 0.5
        )

        # ── 2. Consensus adjustment ──
        consensus_map = {
            "unanimous": 1.15, "strong": 1.05, "moderate": 0.95, "low": 0.80,
        }
        consensus_mult = consensus_map.get(fused.consensus_level, 0.90)

        # ── 3. Divergence penalty ──
        if fused.divergence_detected:
            scores = [s.score for s in fused.source_signals.values()]
            if len(scores) >= 2:
                score_variance = sum((s - 50) ** 2 for s in scores) / len(scores)
                divergence_penalty = 1.0 - min(0.30, score_variance / 5000)
            else:
                divergence_penalty = 0.85
        else:
            divergence_penalty = 1.0

        # ── 4. Market regime ──
        regime_map = {
            "trending_up": 1.05, "trending_down": 0.95,
            "ranging": 0.85, "volatile": 0.70,
            "calm": 1.00, "normal": 1.00,
        }
        regime_mult = regime_map.get(market_regime, 1.00)

        # ── 5. Strength boost + risk penalty ──
        strength_boost = fused.strength * 0.10
        risk_penalty = min(0.30, len(fused.risks) * 0.03)

        # ── Combine ──
        raw_confidence = (
            base_confidence
            * consensus_mult
            * divergence_penalty
            * regime_mult
            + strength_boost
            - risk_penalty
        )

        if fused.direction == "neutral":
            raw_confidence = min(raw_confidence, 0.30)

        return max(0.0, min(100.0, round(raw_confidence * 100)))


# Backward compatibility alias
CalibratedConfidenceScorer = ConfidenceScorer


# ---------------------------------------------------------------------------
# AI Explanation Engine
# ---------------------------------------------------------------------------


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
        """Génère une explication textuelle de la décision."""
        lines = [
            f"Décision pour {symbol}: {action.upper()}",
            f"Score global: {fused.final_score:.1f}/100 ({fused.direction})",
            f"Confiance calibrée: {confidence:.0f}/100",
            f"Régime de marché: {fused.market_regime}",
            f"Consensus: {fused.consensus_level}",
            "",
            "Analyse par source:",
        ]

        for source, signal in sorted(
            fused.source_signals.items(),
            key=lambda x: fused.weights_used.get(x[0], 0),
            reverse=True,
        ):
            w = fused.weights_used.get(source, 0) * 100
            dir_icon = (
                "▲" if signal.direction == "bullish"
                else "▼" if signal.direction == "bearish"
                else "●"
            )
            lines.append(
                f"  {dir_icon} {source.title()} ({w:.0f}%) : "
                f"{signal.score:.0f}/100 → {signal.direction}"
            )

        if fused.reasoning:
            lines.append("")
            lines.append("Raisonnement:")
            for reason in fused.reasoning[:5]:
                lines.append(f"  • {reason}")

        if fused.risks:
            lines.append("")
            lines.append("Risques identifiés:")
            for risk in fused.risks[:3]:
                lines.append(f"  ⚠ {risk}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Central AI Agent
# ---------------------------------------------------------------------------


class CentralAIAgent:
    """
    Agent IA central du système de trading — v2 avec calibration.

    Point d'entrée unique pour toute décision :
    1. Collecte les signaux de tous les moteurs d'analyse
    2. Fusionne les signaux (Feature Fusion avec calibration)
    3. Calcule la confiance calibrée
    4. Génère des explications
    5. Track la qualité des signaux pour amélioration continue
    """

    def __init__(self) -> None:
        self._tracker = SignalQualityTracker()
        self.fusion_engine = FeatureFusionEngine(quality_tracker=self._tracker)
        self.confidence_scorer = ConfidenceScorer(quality_tracker=self._tracker)
        self.explanation_engine = AIExplanationEngine()

        self._running = False
        self._last_decisions: dict[str, dict[str, Any]] = {}
        self._total_decisions = 0

        # Charger l'état sauvegardé
        self._tracker.load()

    # ---- Lifecycle ----

    async def start(self) -> None:
        """Démarre l'agent IA."""
        logger.info("Central AI Agent v2 (calibrated) starting")
        self._running = True
        logger.info(
            "Central AI Agent v2 started — %d sources tracked",
            len(self._tracker._cumulative),
        )

    async def stop(self) -> None:
        """Arrête l'agent IA et sauvegarde l'état."""
        logger.info(
            "Central AI Agent stopping",
            extra={"total_decisions": self._total_decisions},
        )
        self._running = False
        self._tracker.save()
        logger.info("Central AI Agent stopped — quality state saved")

    @property
    def is_running(self) -> bool:
        return self._running

    # ---- Analysis ----

    def analyze(
        self,
        symbol: str,
        signals: dict[str, SourceSignal],
        dynamic_weights: dict[str, float] | None = None,
        market_regime: str = "normal",
        use_adaptive_weights: bool = True,
    ) -> dict[str, Any]:
        """
        Analyse complète calibrée : fusion → confiance → explication.

        Args:
            symbol: Actif analysé
            signals: Signaux de tous les moteurs d'analyse
            dynamic_weights: Poids manuels (override l'adaptatif)
            market_regime: Régime de marché détecté
            use_adaptive_weights: Utiliser les poids adaptatifs

        Returns:
            Décision complète avec explication
        """
        # Fusion calibrée
        fused = self.fusion_engine.fuse(
            symbol, signals, dynamic_weights,
            market_regime=market_regime,
            use_adaptive_weights=use_adaptive_weights,
        )

        # Confiance calibrée
        confidence = self.confidence_scorer.score(fused, market_regime=market_regime)

        # Décision préliminaire
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
            "market_regime": fused.market_regime,
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
                    "calibrated_confidence": round(
                        self._tracker.get_calibrated_confidence(k, v.score), 3
                    ),
                }
                for k, v in signals.items()
            },
            "quality_metrics": {
                k: self._tracker.get_source_metrics(k)
                for k in signals
            },
        }

        self._last_decisions[symbol] = result
        self._total_decisions += 1

        return result

    # ---- Outcome Recording (calibration loop) ----

    def record_outcome(
        self,
        symbol: str,
        actual_return_pct: float,
        actual_direction: str | None = None,
    ) -> None:
        """
        Enregistre le résultat réel d'une décision passée pour calibration.

        Args:
            symbol: Actif concerné
            actual_return_pct: Retour réel en %
            actual_direction: Direction réelle du marché
        """
        last = self._last_decisions.get(symbol)
        if not last:
            return

        actual_return_sign = (
            1.0 if actual_return_pct > 0 else -1.0 if actual_return_pct < 0 else 0.0
        )

        if actual_direction is None:
            actual_direction = (
                "bullish" if actual_return_pct > 1.0
                else "bearish" if actual_return_pct < -1.0
                else "neutral"
            )

        for src, sig_data in last.get("source_signals", {}).items():
            self._tracker.record_prediction(
                source=src,
                predicted_direction=str(sig_data.get("direction", "neutral")),
                predicted_score=float(sig_data.get("score", 50)),
                actual_direction=actual_direction,
                actual_return_sign=actual_return_sign,
            )

        if self._total_decisions % 50 == 0:
            self._tracker.save()

        logger.debug(
            "Outcome recorded for %s: return=%.2f%%, direction=%s",
            symbol, actual_return_pct, actual_direction,
        )

    # ---- Helpers ----

    def _preliminary_action(
        self,
        fused: FusedSignal,
        confidence: float,
    ) -> str:
        """Action préliminaire basée sur le score calibré et la confiance."""
        if fused.divergence_detected and fused.consensus_level == "low":
            return "hold"

        if fused.direction == "neutral" or confidence < 20:
            return "hold"

        if fused.direction == "bullish":
            if fused.final_score > 75 and confidence > 60:
                return "strong_buy"
            if fused.final_score > 60 and confidence > 40:
                return "buy"
            if fused.final_score > 55 and confidence > 30:
                return "reinforce"
            return "hold"
        else:  # bearish
            if fused.final_score < 25 and confidence > 60:
                return "strong_sell"
            if fused.final_score < 40 and confidence > 40:
                return "sell"
            if fused.final_score < 45 and confidence > 30:
                return "reduce"
            return "hold"

    # ---- Accessors ----

    def get_last_decision(self, symbol: str) -> dict[str, Any] | None:
        """Dernière décision pour un actif."""
        return self._last_decisions.get(symbol)

    def get_statistics(self) -> dict[str, Any]:
        """Statistiques de l'agent."""
        return {
            "total_decisions": self._total_decisions,
            "symbols_tracked": len(self._last_decisions),
            "is_running": self._running,
            "quality_metrics": {
                src: self._tracker.get_source_metrics(src)
                for src in self._tracker._cumulative
            },
        }

    def get_quality_report(self) -> dict[str, Any]:
        """Rapport complet de qualité des sources."""
        report: dict[str, Any] = {
            "sources": {},
            "overall_calibration": 0.0,
            "total_predictions": 0,
        }
        total_cal = 0.0
        n_sources = 0

        for src in self._tracker._cumulative:
            metrics = self._tracker.get_source_metrics(src)
            report["sources"][src] = metrics
            report["total_predictions"] += metrics["total_predictions"]
            total_cal += metrics["calibration_score"]
            n_sources += 1

        if n_sources > 0:
            report["overall_calibration"] = round(total_cal / n_sources, 3)

        return report
