"""
Application FastAPI principale.

Configure le middleware, les routes, et le cycle de vie.
Documentation auto-générée via OpenAPI/Swagger.
Démarre les services background :
  - MarketCollector : ticker + OHLCV toutes les 60s
  - AI Analysis : analyse technique + IA toutes les 5 min
  - Paper Trading : exécution simulée des décisions
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import ai, execution, health, market, performance, portfolio, risk
from src.config import config
from src.core.ai_agent import CentralAIAgent, SourceSignal
from src.core.decision_engine import DecisionMatrix
from src.data.market.provider import CCXTProvider
from src.execution.paper import PaperExchange
from src.utils.exceptions import CryptoAIError
from src.utils.logging import get_logger, setup_logging
from src.utils.security.rate_limiter import default_limiter
from src.utils.singleton import (
    register_decision_matrix,
    register_paper_exchange,
    set_live_analysis,
    set_live_market_data,
)

logger = get_logger(__name__)


# ── Background tasks ──────────────────────────────────────────

async def _market_collector_loop(interval: int = 60) -> None:
    """Collecte les données de marché Binance toutes les `interval` secondes."""
    logger.info("Market collector loop started (interval=%ds)", interval)
    while True:
        try:
            prov = CCXTProvider(exchange_name="binance", testnet=False)
            try:
                for symbol in config.watchlist:
                    try:
                        df = await prov.fetch_ohlcv(symbol, "1h", limit=50)
                        ticker = await prov.fetch_ticker(symbol)

                        last_row = None
                        if df is not None and not df.empty:
                            last_row = {
                                "open": round(float(df["open"].iloc[-1]), 2),
                                "high": round(float(df["high"].iloc[-1]), 2),
                                "low": round(float(df["low"].iloc[-1]), 2),
                                "close": round(float(df["close"].iloc[-1]), 2),
                                "volume": round(float(df["volume"].iloc[-1]), 2),
                            }

                        set_live_market_data(symbol, {
                            "ticker": {
                                "last": round(ticker.last, 2),
                                "bid": round(ticker.bid, 2) if ticker.bid else 0,
                                "ask": round(ticker.ask, 2) if ticker.ask else 0,
                                "volume_24h": round(ticker.volume_24h, 2),
                                "change_24h": round(ticker.change_24h, 2),
                            },
                            "last_ohlcv": last_row,
                        })
                    except Exception as exc:
                        logger.debug("Collector skip %s: %s", symbol, exc)
            finally:
                await prov.close()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Collector error: %s", exc)
        await asyncio.sleep(interval)


async def _analysis_and_trading_loop(
    ai_agent: CentralAIAgent,
    tech_engine,
    decision_matrix: DecisionMatrix,
    paper_exchange: PaperExchange | None,
    interval: int = 300,
) -> None:
    """Analyse technique + IA + décision + paper trading toutes les `interval` secondes."""
    logger.info("Analysis & trading loop started (interval=%ds)", interval)
    await asyncio.sleep(15)  # laisser le collecteur faire un premier passage

    symbols = config.watchlist[:6]  # top 6 pour ne pas saturer

    while True:
        try:
            prov = CCXTProvider(exchange_name="binance", testnet=False)
            try:
                for symbol in symbols:
                    try:
                        # ── 1. Fetch multi-timeframe ──
                        df_1h = await prov.fetch_ohlcv(symbol, "1h", limit=200)
                        df_4h = await prov.fetch_ohlcv(symbol, "4h", limit=100)

                        if df_1h is None or df_1h.empty:
                            continue

                        # ── 2. Analyse technique ──
                        work = {"1h": df_1h, "4h": df_4h}
                        tech_score = await tech_engine.analyze(symbol, work)

                        # ── 3. Signal source ──
                        signals = {
                            "technical": SourceSignal(
                                source="technical",
                                score=tech_score.total_score,
                                direction=tech_score.direction,
                                weight=0.35,
                                confidence=0.75,
                                key_signals=tech_score.key_signals,
                            ),
                        }

                        # ── 4. IA Agent ──
                        ai_result = ai_agent.analyze(symbol, signals)

                        # Stocker pour les routes API
                        set_live_analysis(symbol, ai_result)

                        # ── 5. Decision Matrix ──
                        decision = decision_matrix.decide(
                            symbol=symbol,
                            score=ai_result["score"],
                            direction=ai_result["direction"],
                            confidence=ai_result["confidence"],
                            strength=ai_result["strength"],
                        )

                        # ── 6. Paper execution ──
                        if decision.order and paper_exchange:
                            current_price = float(df_1h["close"].iloc[-1])
                            paper_exchange.update_price(symbol, current_price)

                            await paper_exchange.create_order(
                                symbol=symbol,
                                side=decision.order.side,
                                quantity=0.0,
                                quantity_usd=decision.order.quantity_usd,
                                order_type=decision.order.order_type.value,
                                slippage_bps=10,
                            )

                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.debug("Analysis skip %s: %s", symbol, exc)
            finally:
                await prov.close()

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Analysis loop error: %s", exc)

        # Mettre à jour les prix paper entre les cycles
        if paper_exchange:
            for sym in symbols:
                md = get_live_market_data(sym)
                if md and md.get("ticker"):
                    paper_exchange.update_price(sym, md["ticker"]["last"])

        await asyncio.sleep(interval)


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Gère le cycle de vie de l'application + services background."""
    # ===================== STARTUP =====================
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

    bg_tasks: list[asyncio.Task] = []
    paper_exchange: PaperExchange | None = None
    ai_agent: CentralAIAgent | None = None
    tech_engine = None
    decision_matrix: DecisionMatrix | None = None

    if config.mode in ("paper", "live"):
        try:
            # ── Paper Exchange ──
            paper_exchange = PaperExchange(initial_capital=100_000.0)
            await paper_exchange.start()
            register_paper_exchange(paper_exchange)
            logger.info("PaperExchange initialized ($100,000)")

            # ── Decision Matrix ──
            decision_matrix = DecisionMatrix()
            register_decision_matrix(decision_matrix)

            # ── AI Agent ──
            ai_agent = CentralAIAgent()
            await ai_agent.start()
            # Enregistrer dans _instances pour que get_ai_agent() le trouve
            from src.utils.singleton import _instances
            _instances["ai_agent"] = ai_agent

            # ── Technical Engine ──
            from src.analysis.technical.engine import TechnicalAnalysisEngine
            tech_engine = TechnicalAnalysisEngine()
            await tech_engine.start()
            _instances["technical"] = tech_engine

            # ── Background tasks ──
            bg_tasks.append(
                asyncio.create_task(_market_collector_loop(interval=60))
            )
            bg_tasks.append(
                asyncio.create_task(
                    _analysis_and_trading_loop(
                        ai_agent=ai_agent,
                        tech_engine=tech_engine,
                        decision_matrix=decision_matrix,
                        paper_exchange=paper_exchange,
                        interval=300,
                    )
                )
            )

            logger.info("Background services started (%d tasks)", len(bg_tasks))
        except Exception as exc:
            logger.error("Failed to start background services: %s", exc)

    yield

    # ===================== SHUTDOWN =====================
    logger.info("Arrêt des services background…")
    for task in bg_tasks:
        task.cancel()
    if bg_tasks:
        await asyncio.gather(*bg_tasks, return_exceptions=True)

    if tech_engine:
        await tech_engine.stop()
    if ai_agent:
        await ai_agent.stop()
    if paper_exchange:
        await paper_exchange.stop()

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
