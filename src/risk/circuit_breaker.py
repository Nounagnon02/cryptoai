"""
Circuit Breaker — Protection anti-crash et arrêt d'urgence.

Arrête automatiquement le trading si les conditions de marché
deviennent trop dangereuses : krach, volatilité extrême, etc.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from src.utils.logging import get_logger


class CircuitState(StrEnum):
    """État du circuit breaker."""

    CLOSED = "closed"  # Fonctionnement normal
    HALF_OPEN = "half_open"  # Test de reprise
    OPEN = "open"  # Arrêté


@dataclass
class CircuitBreakerConfig:
    """Configuration du circuit breaker."""

    # Seuils de déclenchement
    max_drawdown_1m: float = 3.0  # -3% en 1 minute
    max_drawdown_5m: float = 5.0  # -5% en 5 minutes
    max_drawdown_1h: float = 8.0  # -8% en 1 heure
    max_daily_drawdown: float = 10.0  # -10% journalier

    # Volatilité
    max_volatility_spike: float = 5.0  # × ATR normale

    # Général
    cooldown_minutes: int = 15  # Temps avant test de reprise
    consecutive_triggers_limit: int = 3  # Max déclenchements avant arrêt total
    auto_recovery: bool = True  # Reprise automatique

    # Blacklist
    auto_blacklist_on_trigger: bool = True
    blacklist_duration_minutes: int = 60


@dataclass
class CircuitEvent:
    """Événement de déclenchement."""

    symbol: str
    reason: str
    severity: str  # low | medium | high | critical
    price_at_trigger: float
    drawdown_pct: float
    timestamp: float
    triggered_by: str  # drawdown | volatility | manual | systemic


class CircuitBreaker:
    """
    Circuit Breaker multi-niveaux.

    Niveau 1 — Par actif : drawdown rapide
    Niveau 2 — Volatilité : pic de volatilité anormal
    Niveau 3 — Systémique : crash général du marché
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._states: dict[str, CircuitState] = {}
        self._events: list[CircuitEvent] = []
        self._trigger_counts: dict[str, int] = {}
        self._blacklisted: dict[str, float] = {}  # symbol → fin blacklist
        self._system_state = CircuitState.CLOSED
        self._reference_prices: dict[str, list[dict[str, float]]] = {}
        self._alert_handlers: list[Callable] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("CircuitBreaker started")

    async def stop(self) -> None:
        self._running = False
        logger.info("CircuitBreaker stopped")

    def check_symbol(self, symbol: str, current_price: float) -> bool:
        """
        Vérifie si un actif peut être tradé.

        Returns:
            True si autorisé, False si bloqué
        """
        # Blacklist
        if symbol in self._blacklisted:
            if datetime.now(UTC).timestamp() < self._blacklisted[symbol]:
                logger.warning("Circuit breaker: %s blacklisted", symbol)
                return False
            else:
                self._blacklisted.pop(symbol, None)

        # État du circuit
        state = self._states.get(symbol, CircuitState.CLOSED)
        if state == CircuitState.OPEN:
            return False

        # Enregistrer le prix de référence
        self._record_price(symbol, current_price)

        # Vérifier les conditions
        return self._check_drawdown(symbol, current_price)

    def _check_drawdown(self, symbol: str, current_price: float) -> bool:
        """Vérifie les drawdowns pour déclencher le circuit breaker."""
        prices = self._reference_prices.get(symbol, [])

        if len(prices) < 2:
            return True

        now = datetime.now(UTC)

        # Vérifier sur différentes fenêtres
        checks = [
            ("1m", timedelta(minutes=1), self.config.max_drawdown_1m),
            ("5m", timedelta(minutes=5), self.config.max_drawdown_5m),
            ("1h", timedelta(hours=1), self.config.max_drawdown_1h),
        ]

        for label, window, threshold in checks:
            window_start = now - window
            ref = [p for p in prices if p["timestamp"] >= window_start.timestamp()]
            if ref:
                high_price = max(p["price"] for p in ref)
                drawdown = (high_price - current_price) / high_price * 100

                if drawdown >= threshold:
                    self._trigger(symbol, current_price, drawdown,
                                 f"Drawdown {label} ({drawdown:.1f}%)", "drawdown")
                    return False

        return True

    def _trigger(
        self,
        symbol: str,
        price: float,
        drawdown: float,
        reason: str,
        triggered_by: str,
    ) -> None:
        """Déclenche le circuit breaker pour un actif."""
        # Déterminer la sévérité
        if drawdown >= self.config.max_daily_drawdown:
            severity = "critical"
        elif drawdown >= self.config.max_drawdown_1h:
            severity = "high"
        elif drawdown >= self.config.max_drawdown_5m:
            severity = "medium"
        else:
            severity = "low"

        # Enregistrer l'événement
        event = CircuitEvent(
            symbol=symbol,
            reason=reason,
            severity=severity,
            price_at_trigger=price,
            drawdown_pct=drawdown,
            timestamp=datetime.now(UTC).timestamp(),
            triggered_by=triggered_by,
        )
        self._events.append(event)

        # Ouvrir le circuit
        self._states[symbol] = CircuitState.OPEN

        # Compter les déclenchements
        self._trigger_counts[symbol] = self._trigger_counts.get(symbol, 0) + 1

        # Blacklist si configuré
        if self.config.auto_blacklist_on_trigger:
            blacklist_until = datetime.now(UTC) + timedelta(
                minutes=self.config.blacklist_duration_minutes
            )
            self._blacklisted[symbol] = blacklist_until.timestamp()

        # Vérifier si arrêt total nécessaire
        if self._trigger_counts[symbol] >= self.config.consecutive_triggers_limit:
            self._system_state = CircuitState.OPEN

        # Notifier les handlers
        for handler in self._alert_handlers:
            with contextlib.suppress(Exception):
                handler(event)

        logger.warning(
            "Circuit breaker triggered for %s: %s (severity=%s)",
            symbol, reason, severity,
        )

    def _record_price(self, symbol: str, price: float) -> None:
        """Enregistre un prix de référence."""
        if symbol not in self._reference_prices:
            self._reference_prices[symbol] = []

        self._reference_prices[symbol].append({
            "price": price,
            "timestamp": datetime.now(UTC).timestamp(),
        })

        # Garder seulement 1h de données
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        self._reference_prices[symbol] = [
            p for p in self._reference_prices[symbol]
            if p["timestamp"] >= cutoff.timestamp()
        ]

    def try_recovery(self, symbol: str) -> bool:
        """
        Tente une reprise après cooldown.

        Returns:
            True si le circuit est refermé
        """
        if self._states.get(symbol) != CircuitState.OPEN:
            return True

        if not self.config.auto_recovery:
            return False

        # Vérifier le cooldown
        recent = [e for e in self._events[-10:] if e.symbol == symbol]
        if recent:
            last = recent[-1]
            cooldown_end = last.timestamp + self.config.cooldown_minutes * 60
            if datetime.now(UTC).timestamp() < cooldown_end:
                return False

        self._states[symbol] = CircuitState.CLOSED
        logger.info("Circuit breaker recovered for %s", symbol)
        return True

    def force_open(self, symbol: str, reason: str = "Manual override") -> None:
        """Force l'ouverture du circuit (arrêt manuel)."""
        self._trigger(symbol, 0, 100, reason, "manual")
        logger.warning("Circuit breaker forced open for %s: %s", symbol, reason)

    def force_close(self, symbol: str) -> None:
        """Force la fermeture du circuit (reprise manuelle)."""
        self._states[symbol] = CircuitState.CLOSED
        self._blacklisted.pop(symbol, None)
        logger.info("Circuit breaker forced closed for %s", symbol)

    def add_alert_handler(self, handler: Callable) -> None:
        """Ajoute un handler pour les alertes de déclenchement."""
        self._alert_handlers.append(handler)

    def is_system_operational(self) -> bool:
        """Vérifie si le système global peut trader."""
        return self._system_state == CircuitState.CLOSED

    def get_status(self) -> dict[str, Any]:
        """État complet des circuit breakers."""
        return {
            "system_state": self._system_state.value,
            "open_circuits": [
                sym for sym, state in self._states.items()
                if state == CircuitState.OPEN
            ],
            "blacklisted": list(self._blacklisted.keys()),
            "total_triggers": len(self._events),
            "recent_events": [
                {
                    "symbol": e.symbol,
                    "reason": e.reason,
                    "severity": e.severity,
                    "drawdown": round(e.drawdown_pct, 1),
                }
                for e in self._events[-5:]
            ],
        }

    def get_symbol_status(self, symbol: str, reference_price: float | None = None) -> dict[str, Any]:
        """État du circuit breaker pour un actif spécifique.

        Args:
            symbol: Symbole à vérifier
            reference_price: Prix de référence pour vérifier les conditions de déclenchement.
                             Si None, utilise l'état du circuit et la blacklist uniquement.
        """
        can_trade = True

        # Vérifier la blacklist
        if symbol in self._blacklisted:
            if datetime.now(UTC).timestamp() < self._blacklisted[symbol]:
                can_trade = False
            else:
                self._blacklisted.pop(symbol, None)

        # Vérifier l'état du circuit
        state = self._states.get(symbol, CircuitState.CLOSED)
        if state == CircuitState.OPEN:
            can_trade = False

        # Vérification complète avec prix si fourni
        if reference_price is not None and can_trade:
            can_trade = self.check_symbol(symbol, reference_price)

        return {
            "symbol": symbol,
            "state": state.value,
            "triggers": self._trigger_counts.get(symbol, 0),
            "is_blacklisted": symbol in self._blacklisted,
            "can_trade": can_trade,
        }


logger = get_logger(__name__)
