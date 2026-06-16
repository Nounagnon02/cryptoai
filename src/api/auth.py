"""
Authentication Middleware — JWT validation sur les endpoints API.

Protège toutes les routes /api/v1/* sauf /health et /docs.
"""

from __future__ import annotations

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils.logging import get_logger
from src.utils.security.jwt import JWTEngine, get_jwt_engine

logger = get_logger(__name__)

# Routes publiques (pas d'auth requise)
PUBLIC_PATHS: set[str] = {
    "/health",
    "/health/db",
    "/health/redis",
    "/health/full",
    "/health/ready",
    "/health/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}

# Préfixes publics
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/openapi",
)

# Routes avec auth optionnelle (dashboard, screener, market data)
OPTIONAL_AUTH_PREFIXES: tuple[str, ...] = (
    "/api/v1/settings",
    "/api/v1/market",
    "/api/v1/ai",
    "/api/v1/portfolio",
    "/api/v1/risk",
    "/api/v1/performance",
    "/api/v1/execution",
    "/api/v1/trades",
    "/api/v1/backtest",
)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware JWT pour FastAPI.

    Vérifie le header Authorization: Bearer <token>
    sur toutes les routes non-publiques.

    En mode développement (CRYPTOAI_AUTH_REQUIRED=false), l'auth est optionnelle.
    """

    def __init__(self, app, jwt_engine: JWTEngine | None = None):
        super().__init__(app)
        self._jwt = jwt_engine or get_jwt_engine()
        self._auth_required = True  # Toujours requis par défaut

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Routes publiques — pas d'auth
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # Vérifier le token
        auth_header = request.headers.get("Authorization", "")
        payload = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = self._jwt.validate_token(token)
            if payload:
                # Injecter le payload dans l'état de la requête
                request.state.user = {"sub": payload.sub, "role": payload.role}
            else:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "UNAUTHORIZED",
                        "message": "Invalid or expired token",
                    },
                )

        # Auth optionnelle pour certaines routes (prefix matching)
        if any(path.startswith(prefix) for prefix in OPTIONAL_AUTH_PREFIXES):
            return await call_next(request)

        # Auth requise pour toutes les autres routes /api/v1/
        if not payload:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "UNAUTHORIZED",
                    "message": "Authorization header required. Use: Bearer <token>",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


def generate_api_token(role: str = "admin") -> str:
    """Utilitaire pour générer un token API (usage CLI/admin)."""
    jwt = get_jwt_engine()
    return jwt.create_token(sub="api", role=role)
