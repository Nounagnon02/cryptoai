"""
Système d'exceptions hiérarchique.

Toutes les exceptions du système héritent de CryptoAIError.
Classification : récupérable vs irrécupérable, attendue vs inattendue.
"""

from __future__ import annotations

from typing import Any


class CryptoAIError(Exception):
    """Exception de base pour tout le système CryptoAI."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.cause = cause
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": str(self),
            "details": self.details,
        }


# ─── Erreurs de données / collecte ──────────────────────────────


class DataError(CryptoAIError):
    """Erreur lors de la collecte ou du traitement de données."""

    def __init__(
        self,
        message: str,
        code: str = "DATA_ERROR",
        symbol: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.symbol = symbol
        super().__init__(message, code=code, details={"symbol": symbol} if symbol else {}, **kwargs)


class ProviderError(DataError):
    """Erreur du fournisseur de données (exchange, API)."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        code: str = "PROVIDER_ERROR",
        **kwargs: Any,
    ) -> None:
        self.provider = provider
        super().__init__(
            message,
            code=code,
            provider=provider,
            **kwargs,
        )


class RateLimitError(ProviderError):
    """Rate limit atteint sur un exchange ou API."""

    def __init__(
        self,
        message: str = "Rate limit atteint",
        provider: str = "unknown",
        retry_after: int = 60,
        **kwargs: Any,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(
            message,
            provider=provider,
            code="RATE_LIMIT",
            retry_after=retry_after,
            **kwargs,
        )


class WebSocketError(DataError):
    """Erreur de connexion WebSocket."""

    def __init__(
        self,
        message: str = "Erreur WebSocket",
        endpoint: str = "unknown",
        **kwargs: Any,
    ) -> None:
        self.endpoint = endpoint
        super().__init__(message, code="WEBSOCKET_ERROR", endpoint=endpoint, **kwargs)


# ─── Erreurs d'analyse ──────────────────────────────────────────


class AnalysisError(CryptoAIError):
    """Erreur lors de l'analyse."""

    def __init__(
        self,
        message: str,
        code: str = "ANALYSIS_ERROR",
        analyzer: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.analyzer = analyzer
        super().__init__(message, code=code, analyzer=analyzer, **kwargs)


class InsufficientDataError(AnalysisError):
    """Données insuffisantes pour l'analyse."""

    def __init__(
        self,
        message: str = "Données insuffisantes pour l'analyse",
        required_points: int = 0,
        available_points: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="INSUFFICIENT_DATA",
            required_points=required_points,
            available_points=available_points,
            **kwargs,
        )


# ─── Erreurs de risque ──────────────────────────────────────────


class RiskError(CryptoAIError):
    """Erreur de gestion des risques."""

    def __init__(
        self,
        message: str,
        code: str = "RISK_ERROR",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, code=code, **kwargs)


class RiskLimitExceededError(RiskError):
    """Limite de risque dépassée."""

    def __init__(
        self,
        message: str = "Limite de risque dépassée",
        limit_type: str = "unknown",
        limit_value: float = 0.0,
        current_value: float = 0.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code="RISK_LIMIT_EXCEEDED",
            limit_type=limit_type,
            limit_value=limit_value,
            current_value=current_value,
            **kwargs,
        )


class CircuitBreakerTriggeredError(RiskError):
    """Circuit breaker déclenché — marché dangereux."""

    def __init__(
        self,
        message: str = "Circuit breaker déclenché",
        reason: str = "unknown",
        cooldown_minutes: int = 60,
        **kwargs: Any,
    ) -> None:
        self.cooldown_minutes = cooldown_minutes
        super().__init__(
            message,
            code="CIRCUIT_BREAKER",
            reason=reason,
            cooldown_minutes=cooldown_minutes,
            **kwargs,
        )


# ─── Erreurs d'exécution ────────────────────────────────────────


class ExecutionError(CryptoAIError):
    """Erreur lors de l'exécution d'un ordre."""

    def __init__(
        self,
        message: str,
        code: str = "EXECUTION_ERROR",
        order_id: str | None = None,
        symbol: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.order_id = order_id
        self.symbol = symbol
        super().__init__(
            message,
            code=code,
            order_id=order_id,
            symbol=symbol,
            **kwargs,
        )


class OrderRejectedError(ExecutionError):
    """Ordre rejeté par l'exchange."""

    def __init__(
        self,
        message: str = "Ordre rejeté",
        reject_reason: str = "unknown",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, code="ORDER_REJECTED", reject_reason=reject_reason, **kwargs)


# ─── Erreurs de sécurité ────────────────────────────────────────


class SecurityError(CryptoAIError):
    """Erreur de sécurité."""

    def __init__(self, message: str, code: str = "SECURITY_ERROR", **kwargs: Any) -> None:
        super().__init__(message, code=code, **kwargs)


class AuthenticationError(SecurityError):
    """Erreur d'authentification."""

    def __init__(
        self,
        message: str = "Authentification échouée",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, code="AUTH_FAILED", **kwargs)


class AuthorizationError(SecurityError):
    """Erreur d'autorisation."""

    def __init__(
        self,
        message: str = "Accès non autorisé",
        required_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, code="FORBIDDEN", required_role=required_role, **kwargs)
