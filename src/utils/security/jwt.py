"""
JWT Authentication Engine — Tokens, validation, middleware.

Standards:
- Algorithm: HS256 (HMAC-SHA256)
- Token format: Bearer <token>
- Token lifetime: 24h access, 7d refresh
- Claims: sub, exp, iat, role
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field


@dataclass
class TokenPayload:
    """Contenu décodé d'un token JWT."""
    sub: str           # Subject (user ID ou "api")
    role: str = "user"
    exp: float = 0.0   # Expiration timestamp
    iat: float = 0.0   # Issued at timestamp

    def is_expired(self) -> bool:
        return self.exp > 0 and time.time() > self.exp


class JWTEngine:
    """
    Moteur JWT pour l'authentification API.

    Usage:
    ```python
    jwt = JWTEngine()

    # Générer un token
    token = jwt.create_token(sub="admin", role="admin")

    # Valider
    payload = jwt.validate_token(token)

    # Middleware FastAPI
    from src.api.auth import JWTAuthMiddleware
    ```
    """

    ALGORITHM = "HS256"
    ACCESS_TTL = 24 * 3600    # 24 heures
    REFRESH_TTL = 7 * 86400   # 7 jours

    def __init__(self, secret: str | None = None) -> None:
        self._secret = secret or os.getenv(
            "CRYPTOAI_JWT_SECRET",
            os.getenv("CRYPTOAI_ENCRYPTION_KEY", secrets.token_hex(32))
        )

    def create_token(
        self,
        sub: str = "api",
        role: str = "user",
        ttl: int | None = None,
    ) -> str:
        """Crée un token JWT signé HMAC-SHA256."""
        now = time.time()
        ttl = ttl or self.ACCESS_TTL
        payload = {
            "sub": sub,
            "role": role,
            "iat": int(now),
            "exp": int(now + ttl),
            "jti": secrets.token_hex(8),
        }
        return self._encode(payload)

    def create_refresh_token(self, sub: str = "api", role: str = "user") -> str:
        """Crée un refresh token longue durée."""
        return self.create_token(sub=sub, role=role, ttl=self.REFRESH_TTL)

    def validate_token(self, token: str) -> TokenPayload | None:
        """Valide et décode un token JWT. Retourne None si invalide/expiré."""
        try:
            payload = self._decode(token)
            if not payload:
                return None

            exp = payload.get("exp", 0)
            if exp and time.time() > exp:
                return None  # Expiré

            return TokenPayload(
                sub=payload.get("sub", "unknown"),
                role=payload.get("role", "user"),
                exp=float(exp),
                iat=float(payload.get("iat", 0)),
            )
        except Exception:
            return None

    def _encode(self, payload: dict) -> str:
        """Encode un payload en JWT HS256."""
        header = {"alg": "HS256", "typ": "JWT"}
        segments = [
            urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"="),
            urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"="),
        ]
        signing_input = b".".join(segments)
        signature = hmac.new(
            self._secret.encode(), signing_input, hashlib.sha256
        ).digest()
        segments.append(urlsafe_b64encode(signature).rstrip(b"="))
        return b".".join(segments).decode()

    def _decode(self, token: str) -> dict | None:
        """Décode et vérifie un JWT."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            header_b64, payload_b64, sig_b64 = parts

            # Vérifier la signature
            signing_input = f"{header_b64}.{payload_b64}".encode()
            expected_sig = hmac.new(
                self._secret.encode(), signing_input, hashlib.sha256
            ).digest()

            # Ajouter le padding base64 si nécessaire
            sig_b64_padded = sig_b64 + "=" * (-len(sig_b64) % 4)
            actual_sig = urlsafe_b64decode(sig_b64_padded)

            if not hmac.compare_digest(expected_sig, actual_sig):
                return None

            # Décoder le payload
            payload_b64_padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            return json.loads(urlsafe_b64decode(payload_b64_padded))
        except Exception:
            return None


# Instance par défaut
_default_jwt: JWTEngine | None = None


def get_jwt_engine() -> JWTEngine:
    """Retourne l'instance JWT par défaut."""
    global _default_jwt
    if _default_jwt is None:
        _default_jwt = JWTEngine()
    return _default_jwt
