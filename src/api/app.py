"""
Application FastAPI principale.

Configure le middleware, les routes, et le cycle de vie.
Documentation auto-générée via OpenAPI/Swagger.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import ai, execution, health, market, performance, portfolio, risk
from src.config import config
from src.utils.exceptions import CryptoAIError
from src.utils.logging import get_logger, setup_logging
from src.utils.security.rate_limiter import default_limiter

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Gère le cycle de vie de l'application."""
    # Startup
    setup_logging(config.log_level, config.log_format)
    logger.info(
        "CryptoAI API démarrée",
        extra={
            "version": "1.0.0",
            "mode": config.mode,
            "watchlist_count": len(config.watchlist),
        },
    )
    default_limiter.add_default_rules()
    yield
    # Shutdown
    logger.info("CryptoAI API arrêtée")


app = FastAPI(
    title="CryptoAI API",
    description="Plateforme de trading crypto autonome pilotée par IA",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Inclusion des routeurs ──────────────────────────────────
app.include_router(health.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(risk.router)
app.include_router(ai.router)
app.include_router(performance.router)
app.include_router(execution.router)


# ─── Gestion globale des erreurs ──────────────────────────────
@app.exception_handler(CryptoAIError)
async def cryptoai_error_handler(request: Request, exc: CryptoAIError):
    """Handler pour les exceptions CryptoAI."""
    logger.error(
        "Erreur CryptoAI",
        extra={
            "code": exc.code,
            "error_message": str(exc),
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    """Handler pour les exceptions non prévues."""
    logger.error(
        "Erreur non gérée",
        extra={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "Une erreur interne est survenue",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


# ─── Middleware de rate limiting ──────────────────────────────
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting sur toutes les routes API."""
    if request.url.path.startswith("/health"):
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = default_limiter.check(ip, "api_per_ip")
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "RATE_LIMITED",
                "message": f"Trop de requêtes. Réessayez dans {retry_after}s",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)


# ─── Middleware de logging des requêtes ───────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Logge toutes les requêtes API."""
    start = datetime.now(UTC)
    response = await call_next(request)
    duration = (datetime.now(UTC) - start).total_seconds()

    logger.info(
        "Requête API",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration * 1000),
        },
    )
    return response
