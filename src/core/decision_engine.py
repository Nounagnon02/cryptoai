"""
Moteur de décision — Transforme les analyses en ordres.

À partir du signal fusionné de l'AI Agent, le Decision Engine :
1. Valide les conditions de risque
2. Calcule la taille de position
3. Génère les paramètres d'ordre (prix, durée, type)
4. Enregistre la décision complète pour audit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ActionType(StrEnum):
    """Actions de trading possibles."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    REINFORCE = "reinforce"
    HOLD = "hold"
    REDUCE = "reduce"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class OrderType(StrEnum):
    """Types d'ordres supportés."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"
    TWAP = "twap"  # Time-Weighted Average Price
    VWAP = "vwap"  # Volume-Weighted Average Price


class TimeInForce(StrEnum):
    """Durée de validité des ordres."""

    GTC = "gtc"  # Good Till Cancelled
    IOC = "ioc"  # Immediate Or Cancel
    FOK = "fok"  # Fill Or Kill
    DAY = "day"  # Good for the day


@dataclass
class OrderParams:
    """Paramètres complets d'un ordre."""

    symbol: str
    side: str  # buy | sell
    action: ActionType
    order_type: OrderType

    # Taille
    quantity: float  # En unités de l'actif de base
    quantity_usd: float  # En USD
    portfolio_pct: float  # % du portefeuille alloué

    # Prix
    limit_price: float | None = None
    stop_price: float | None = None
    slippage_tolerance: float = 0.001  # 0.1% par défaut

    # Exécution
    time_in_force: TimeInForce = TimeInForce.GTC
    post_only: bool = False
    reduce_only: bool = False

    # Stratégie
    strategy: str = "default"
    reason: str = ""

    # Timestamps
    created_at: float = 0.0
    expires_at: float | None = None


@dataclass
class DecisionRecord:
    """Enregistrement complet d'une décision."""

    symbol: str
    action: ActionType
    confidence: float
    score: float

    # Ordre généré (None si HOLD)
    order: OrderParams | None = None

    # Analyse
    fused_signal: Any = None
    risk_check: dict[str, Any] = field(default_factory=dict)

    # Métadonnées
    decision_id: str = ""
    timestamp: float = 0.0
    execution_plan: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DecisionMatrix:
    """
    Matrice de décision principale.

    Convertit les scores d'analyse en actions concrètes avec sizing.
    """

    # Mapping score → action
    SCORE_THRESHOLDS = [
        (80, ActionType.STRONG_BUY, 0.20),   # > 80 → max 20% du capital
        (65, ActionType.BUY, 0.10),          # > 65 → max 10%
        (55, ActionType.REINFORCE, 0.05),    # > 55 → max 5%
        (45, ActionType.HOLD, 0.0),          # Neutre
        (35, ActionType.REDUCE, 0.0),        # < 35 → réduire
        (20, ActionType.SELL, 0.0),          # < 20 → vendre
        (0, ActionType.STRONG_SELL, 0.0),    # < 0 → vendre tout
    ]

    # Sizing par niveau de confiance
    CONFIDENCE_MULTIPLIERS = {
        "very_low": 0.0,    # 0-20
        "low": 0.3,         # 20-40
        "moderate": 0.6,    # 40-60
        "high": 0.8,        # 60-80
        "very_high": 1.0,   # 80-100
    }

    def __init__(self) -> None:
        self._decision_log: dict[str, list[DecisionRecord]] = {}
        self._total_decisions = 0

    def decide(
        self,
        symbol: str,
        score: float,
        direction: str,
        confidence: float,
        strength: float,
        current_position: float = 0.0,
        portfolio_value: float = 100_000,
        volatility_regime: str = "normal",
        existing_orders: int = 0,
        **_kwargs,
    ) -> DecisionRecord:
        """
        Prend une décision basée sur l'analyse.

        Args:
            symbol: Actif
            score: Score global (0-100)
            direction: bullish | bearish | neutral
            confidence: Confiance (0-100)
            strength: Force du signal (0-1)
            current_position: Position actuelle (USD)
            portfolio_value: Valeur totale du portefeuille
            volatility_regime: normal | high | low
            existing_orders: Nombre d'ordres ouverts

        Returns:
            DecisionRecord complet
        """
        # Déterminer l'action
        action = self._map_score_to_action(score, direction, confidence)

        # Sizing
        max_allocation = self._calculate_allocation(
            action, confidence, strength, volatility_regime, existing_orders
        )
        position_size = portfolio_value * max_allocation

        # Ajustement si position existante
        if action in (ActionType.BUY, ActionType.REINFORCE):
            position_size = min(position_size, portfolio_value * 0.25)
        elif action in (ActionType.REDUCE, ActionType.SELL, ActionType.STRONG_SELL):
            position_size = current_position * 0.5  # Vendre 50% de la position

        # Ordre
        order = self._generate_order(
            symbol=symbol,
            action=action,
            position_size=position_size,
            portfolio_value=portfolio_value,
            score=score,
            confidence=confidence,
        ) if action not in (ActionType.HOLD,) else None

        # Plan d'exécution
        execution_plan = self._generate_execution_plan(
            action, order, position_size, volatility_regime
        )

        # Avertissements
        warnings = []
        if confidence < 30:
            warnings.append("Faible confiance — considérer réduire la taille")
        if existing_orders > 5:
            warnings.append("Nombre élevé d'ordres ouverts")
        if volatility_regime == "high":
            warnings.append("Volatilité élevée — ajuster le slippage")

        record = DecisionRecord(
            symbol=symbol,
            action=action,
            confidence=confidence,
            score=score,
            order=order,
            risk_check={
                "volatility_regime": volatility_regime,
                "existing_orders": existing_orders,
                "max_allocation_pct": round(max_allocation * 100, 1),
                "position_size_usd": round(position_size, 2),
                "position_pct": round((position_size / max(portfolio_value, 1)) * 100, 2),
            },
            decision_id=f"dec_{symbol}_{int(datetime.now(UTC).timestamp())}",
            timestamp=datetime.now(UTC).timestamp(),
            execution_plan=execution_plan,
            warnings=warnings,
        )

        # Journaliser
        if symbol not in self._decision_log:
            self._decision_log[symbol] = []
        self._decision_log[symbol].append(record)
        self._total_decisions += 1

        if len(self._decision_log[symbol]) > 1000:
            self._decision_log[symbol] = self._decision_log[symbol][-1000:]

        return record

    def _map_score_to_action(
        self,
        score: float,
        direction: str,
        confidence: float,
    ) -> ActionType:
        """Map le score à une action."""
        if direction == "neutral" or confidence < 15:
            return ActionType.HOLD

        for threshold, action, _ in self.SCORE_THRESHOLDS:
            if direction == "bullish" and score >= threshold:
                return action
            elif direction == "bearish":
                inverted_score = 100 - score
                if inverted_score >= threshold:
                    return action

        return ActionType.HOLD

    def _calculate_allocation(
        self,
        action: ActionType,
        confidence: float,
        _strength: float,
        volatility_regime: str,
        existing_orders: int,
    ) -> float:
        """Calcule l'allocation en fraction du portefeuille."""
        # Allocation de base par action
        base = 0.0
        for _threshold, act, alloc in self.SCORE_THRESHOLDS:
            if act == action:
                base = alloc
                break

        if action in (ActionType.HOLD, ActionType.REDUCE, ActionType.SELL, ActionType.STRONG_SELL):
            return base

        # Ajustement par confiance
        if confidence < 20:
            confidence_mult = self.CONFIDENCE_MULTIPLIERS["very_low"]
        elif confidence < 40:
            confidence_mult = self.CONFIDENCE_MULTIPLIERS["low"]
        elif confidence < 60:
            confidence_mult = self.CONFIDENCE_MULTIPLIERS["moderate"]
        elif confidence < 80:
            confidence_mult = self.CONFIDENCE_MULTIPLIERS["high"]
        else:
            confidence_mult = self.CONFIDENCE_MULTIPLIERS["very_high"]

        allocation = base * confidence_mult

        # Ajustement par volatilité
        if volatility_regime == "high":
            allocation *= 0.6
        elif volatility_regime == "low":
            allocation *= 1.1

        # Pénalité si trop d'ordres ouverts
        if existing_orders > 3:
            allocation *= max(0.3, 1 - (existing_orders - 3) * 0.1)

        return min(base, allocation)

    def _generate_order(
        self,
        symbol: str,
        action: ActionType,
        position_size: float,
        portfolio_value: float,
        score: float,
        confidence: float,
    ) -> OrderParams:
        """Génère les paramètres d'ordre."""
        is_buy = action in (ActionType.STRONG_BUY, ActionType.BUY, ActionType.REINFORCE)
        side = "buy" if is_buy else "sell"

        # Type d'ordre basé sur la confiance et la stratégie
        if confidence > 70 and score > 70:
            order_type = OrderType.MARKET
        elif confidence > 50:
            order_type = OrderType.LIMIT
        else:
            order_type = OrderType.LIMIT

        portfolio_pct = (position_size / max(portfolio_value, 1)) * 100

        return OrderParams(
            symbol=symbol,
            side=side,
            action=action,
            order_type=order_type,
            quantity=0.0,  # À calculer au moment de l'exécution avec le prix actuel
            quantity_usd=round(position_size, 2),
            portfolio_pct=round(portfolio_pct, 2),
            slippage_tolerance=0.001,
            time_in_force=TimeInForce.GTC,
            post_only=order_type == OrderType.LIMIT,
            strategy="core_ai",
            reason=f"Score: {score:.0f}/100, Confiance: {confidence:.0f}%",
            created_at=datetime.now(UTC).timestamp(),
        )

    def _generate_execution_plan(
        self,
        action: ActionType,
        order: OrderParams | None,
        position_size: float,
        volatility_regime: str,
    ) -> list[str]:
        """Génère le plan d'exécution."""
        plan = [f"Action: {action.value}"]

        if order:
            plan.append(f"Side: {order.side}")
            plan.append(f"Type: {order.order_type.value}")
            plan.append(f"Taille: ${position_size:,.2f}")
            plan.append(f"Allocation: {order.portfolio_pct:.1f}% du portefeuille")

            if volatility_regime == "high" and order.order_type == OrderType.MARKET:
                plan.append("⚠ Utiliser TWAP pour réduire l'impact sur le prix")

        return plan

    def get_decision_history(
        self,
        symbol: str,
        limit: int = 20,
    ) -> list[DecisionRecord]:
        """Historique des décisions pour un actif."""
        history = self._decision_log.get(symbol, [])
        return history[-limit:]

    def get_recent_decisions(self, limit: int = 50) -> list[DecisionRecord]:
        """Décisions récentes tous actifs confondus."""
        all_decisions = []
        for decisions in self._decision_log.values():
            all_decisions.extend(decisions)

        all_decisions.sort(key=lambda d: d.timestamp, reverse=True)
        return all_decisions[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """Statistiques des décisions."""
        all_decisions = self.get_recent_decisions(1000)
        action_counts: dict[str, int] = {}

        for d in all_decisions:
            action_counts[d.action.value] = action_counts.get(d.action.value, 0) + 1

        return {
            "total_decisions": self._total_decisions,
            "symbols_tracked": len(self._decision_log),
            "actions_distribution": action_counts,
            "recent_actions": sum(1 for d in all_decisions if d.action not in (ActionType.HOLD,)),
        }

    def clear_history(self, symbol: str | None = None) -> None:
        """Vide l'historique des décisions."""
        if symbol:
            self._decision_log.pop(symbol, None)
        else:
            self._decision_log.clear()


class OrderGenerator:
    """
    Générateur d'ordres prêts pour l'exécution.

    Prend une décision et produit l'ordre final avec
    les paramètres précis pour l'execution engine.
    """

    def generate(
        self,
        decision: DecisionRecord,
        current_price: float,
        slippage_bps: float = 10,
    ) -> OrderParams:
        """
        Génère l'ordre final prêt pour l'exécution.

        Args:
            decision: Décision de trading
            current_price: Prix actuel
            slippage_bps: Slippage toléré en bps

        Returns:
            OrderParams complet avec prix et quantité
        """
        if not decision.order:
            raise ValueError("Cannot generate order for HOLD decision")

        order = decision.order

        # Calculer la quantité
        if current_price > 0:
            order.quantity = round(order.quantity_usd / current_price, 8)

        # Prix limites
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if order.side == "buy":
                order.limit_price = round(current_price * (1 - slippage_bps / 10000), 8)
            else:
                order.limit_price = round(current_price * (1 + slippage_bps / 10000), 8)

        # Stop price
        if order.order_type in (OrderType.STOP_LOSS, OrderType.STOP_LIMIT):
            if order.side == "buy":
                order.stop_price = round(current_price * 1.01, 8)  # 1% au-dessus
            else:
                order.stop_price = round(current_price * 0.99, 8)  # 1% en-dessous

        return order


class DecisionLogger:
    """
    Journalisation complète des décisions.

    Enregistre chaque décision avec tout le contexte pour :
    - Audit et traçabilité
    - Analyse post-trade
    - Rejeu des décisions
    - Amélioration du modèle
    """

    def __init__(self) -> None:
        self._log: list[dict[str, Any]] = []

    def log_decision(
        self,
        decision: DecisionRecord,
        ai_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Enregistre une décision complète.

        Returns:
            Entrée de log formatée
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "decision_id": decision.decision_id,
            "symbol": decision.symbol,
            "action": decision.action.value,
            "score": decision.score,
            "confidence": decision.confidence,
            # Risques et avertissements
            "warnings": decision.warnings,
            "risk_check": decision.risk_check,
            # Ordre
            "has_order": decision.order is not None,
        }

        if decision.order:
            entry["order"] = {
                "side": decision.order.side,
                "type": decision.order.order_type.value,
                "quantity_usd": decision.order.quantity_usd,
                "portfolio_pct": decision.order.portfolio_pct,
                "strategy": decision.order.strategy,
                "reason": decision.order.reason,
            }

        if ai_analysis:
            entry["ai_analysis"] = {
                "reasoning": ai_analysis.get("reasoning", []),
                "key_drivers": ai_analysis.get("key_drivers", []),
                "source_signals": {
                    k: v.get("score")
                    for k, v in ai_analysis.get("source_signals", {}).items()
                },
            }

        self._log.append(entry)

        # Limiter la taille du log
        if len(self._log) > 10_000:
            self._log = self._log[-5_000:]

        return entry

    def get_recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Récupère les logs récents."""
        return self._log[-limit:]

    def get_logs_by_symbol(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """Logs filtrés par actif."""
        filtered = [e for e in self._log if e["symbol"] == symbol]
        return filtered[-limit:]

    def get_logs_by_action(self, action: str, limit: int = 50) -> list[dict[str, Any]]:
        """Logs filtrés par action."""
        filtered = [e for e in self._log if e["action"] == action]
        return filtered[-limit:]

    def export_to_dict(self) -> list[dict[str, Any]]:
        """Export complet pour analyse."""
        return list(self._log)
