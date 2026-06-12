"""
Rate Limiter — Limitation de débit pour API endpoints.

Protège contre :
- Abus et attaques DoS
- Dépassement des limites API exchanges
- Utilisation excessive des ressources

Utilise un sliding window counter pour une granularité précise.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class RateLimitRule:
    """Règle de rate limiting."""

    max_requests: int  # Nombre max de requêtes
    window_seconds: int  # Fenêtre en secondes
    block_seconds: int = 0  # Temps de blocage si dépassé (0 = pas de blocage)


@dataclass
class RateLimitState:
    """État du rate limiter pour une clé."""

    count: int
    window_start: float
    blocked_until: float = 0.0


class RateLimiter:
    """
    Rate limiter avec sliding window.

    Supporte :
    - Multiples règles par clé (ex: 10 req/s + 100 req/min)
    - Blocage temporaire après dépassement
    - Reset automatique des fenêtres
    - Cleanup périodique
    """

    def __init__(self) -> None:
        self._states: dict[str, dict[str, RateLimitState]] = {}
        self._rules: dict[str, RateLimitRule] = {}
        self._cleanup_interval: int = 300  # 5 min

    def add_rule(self, name: str, rule: RateLimitRule) -> None:
        """
        Ajoute une règle de rate limiting.

        Args:
            name: Nom de la règle (ex: "api_default", "auth_login")
            rule: Règle de rate limiting
        """
        self._rules[name] = rule

    def add_default_rules(self) -> None:
        """Ajoute les règles par défaut."""
        default_rules = {
            "api_global": RateLimitRule(max_requests=1000, window_seconds=60, block_seconds=120),
            "api_per_ip": RateLimitRule(max_requests=100, window_seconds=60, block_seconds=60),
            "api_per_user": RateLimitRule(max_requests=200, window_seconds=60, block_seconds=60),
            "auth_login": RateLimitRule(max_requests=5, window_seconds=300, block_seconds=900),
            "auth_register": RateLimitRule(max_requests=3, window_seconds=3600, block_seconds=3600),
            "order_create": RateLimitRule(max_requests=10, window_seconds=1),
            "order_cancel": RateLimitRule(max_requests=20, window_seconds=10),
        }
        for name, rule in default_rules.items():
            self.add_rule(name, rule)

    def check(self, key: str, rule_name: str = "api_global") -> tuple[bool, int]:
        """
        Vérifie si une requête est autorisée.

        Args:
            key: Clé unique (IP, user_id, API key)
            rule_name: Nom de la règle à appliquer

        Returns:
            (allowed, retry_after_seconds)
        """
        rule = self._rules.get(rule_name)
        if not rule:
            return True, 0

        if rule_name not in self._states:
            self._states[rule_name] = {}

        states = self._states[rule_name]
        now = time.monotonic()

        # Initialiser ou récupérer l'état
        if key not in states:
            states[key] = RateLimitState(
                count=0,
                window_start=now,
                blocked_until=0,
            )

        state = states[key]

        # Vérifier si bloqué
        if state.blocked_until > now:
            retry_after = int(state.blocked_until - now) + 1
            return False, retry_after

        # Nouvelle fenêtre ?
        if now - state.window_start > rule.window_seconds:
            state.count = 0
            state.window_start = now

        # Vérifier le quota
        if state.count >= rule.max_requests:
            if rule.block_seconds > 0:
                state.blocked_until = now + rule.block_seconds
                retry_after = rule.block_seconds
            else:
                retry_after = int(rule.window_seconds - (now - state.window_start)) + 1
            return False, retry_after

        state.count += 1
        return True, 0

    async def wait_if_needed(self, key: str, rule_name: str = "api_global") -> None:
        """
        Attend si la limite est atteinte (bloquant).

        Utile pour les appels API externes qui ont du rate limiting.
        """
        allowed, retry_after = self.check(key, rule_name)
        if not allowed and retry_after > 0:
            await asyncio.sleep(retry_after)

    def get_usage(self, key: str, rule_name: str) -> dict[str, Any]:
        """Retourne l'utilisation actuelle pour une clé et règle."""
        states = self._states.get(rule_name, {})
        state = states.get(key)

        if not state:
            rule = self._rules.get(rule_name)
            return {
                "rule": rule_name,
                "max_requests": rule.max_requests if rule else 0,
                "current_usage": 0,
                "remaining": rule.max_requests if rule else 0,
                "reset_in_seconds": 0,
                "blocked": False,
            }

        rule = self._rules.get(rule_name)
        now = time.monotonic()
        reset_in = max(0, int(rule.window_seconds - (now - state.window_start))) if rule else 0
        blocked = state.blocked_until > now

        return {
            "rule": rule_name,
            "max_requests": rule.max_requests if rule else 0,
            "current_usage": state.count,
            "remaining": max(0, (rule.max_requests - state.count)) if rule else 0,
            "reset_in_seconds": reset_in,
            "blocked": blocked,
            "blocked_for_seconds": max(0, int(state.blocked_until - now)) if blocked else 0,
        }

    def get_all_usage(self) -> dict[str, Any]:
        """Retourne l'utilisation de toutes les règles."""
        return {
            rule_name: {
                key: self.get_usage(key, rule_name)
                for key in states
            }
            for rule_name, states in self._states.items()
        }

    def reset_key(self, key: str, rule_name: str | None = None) -> None:
        """Reset l'état d'une clé."""
        if rule_name:
            self._states.get(rule_name, {}).pop(key, None)
        else:
            for states in self._states.values():
                states.pop(key, None)

    def cleanup(self) -> int:
        """
        Nettoie les états périmés.

        Returns:
            Nombre d'entrées nettoyées
        """
        now = time.monotonic()
        cleaned = 0

        for rule_name, states in self._states.items():
            rule = self._rules.get(rule_name)
            if not rule:
                continue

            expired_keys = [
                key for key, state in states.items()
                if now - state.window_start > rule.window_seconds * 2
                and state.blocked_until < now
            ]
            for key in expired_keys:
                del states[key]
                cleaned += 1

        return cleaned


@dataclass
class RateLimitDecorator:
    """
    Décorateur pour rate limiter.

    Utilisation :
    ```python
    rate_limiter = RateLimiter()
    rate_limiter.add_default_rules()

    @RateLimitDecorator(rate_limiter, rule_name="api_per_ip")
    async def my_endpoint(ip: str):
        ...
    ```
    """

    limiter: RateLimiter
    rule_name: str = "api_global"

    async def __call__(self, key: str) -> bool:
        allowed, retry_after = self.limiter.check(key, self.rule_name)
        return allowed


# Instance globale
default_limiter = RateLimiter()


__all__ = ["RateLimiter", "RateLimitRule", "RateLimitState", "default_limiter"]
