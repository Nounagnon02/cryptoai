"""
Application FastAPI principale.

Configure le middleware, les routes, et le cycle de vie.
Documentation auto-générée via OpenAPI/Swagger.

Démarre les services background :
  - MarketCollector : ticker + OHLCV toutes les 60s
  - AI Analysis : analyse technique + IA toutes les 5 min
  - Safety Layer : RiskManager + CircuitBreaker (tous modes)
  - Paper Trading : exécution simulée (mode paper)
  - Live Trading : exécution réelle via CCXT (mode live)

Sécurité Live Trading :
  - Emergency stop global
  - CircuitBreaker (drawdown, volatilité)
  - RiskManager (taille, stop-loss, exposition)
  - Order deduplication (idempotence)
  - Audit trail JSONL
  - API keys chiffrées AES-256-GCM
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.auth import JWTAuthMiddleware
from src.api.routes import (
    ai,
    backtesting,
    execution,
    health,
    market,
    performance,
    portfolio,
    risk,
    screener,
    settings,
    stream,
    trades,
    trading,
)
from src.config import config
from src.core.ai_agent import CentralAIAgent, SourceSignal
from src.core.decision_engine import DecisionMatrix
from src.data.market.provider import CCXTProvider
from src.execution.paper import PaperExchange
from src.utils.exceptions import CryptoAIError
from src.utils.logging import get_logger, setup_logging
from src.utils.security.rate_limiter import default_limiter
from src.utils.singleton import (
    _instances,
    get_live_market_data,
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
    onchain_scorer,
    social_scorer,
    news_scorer,
    decision_matrix: DecisionMatrix,
    paper_exchange: PaperExchange | None,
    live_trading_engine=None,
    risk_manager=None,
    circuit_breaker=None,
    interval: int = 300,
) -> None:
    """
    Analyse technique + IA + décision + exécution toutes les `interval` secondes.

    Pipeline de sécurité (chaque ordre) :
      1. CircuitBreaker → symbole tradable ?
      2. RiskManager → taille/risque acceptable ?
      3. LiveTradingEngine (mode live) ou PaperExchange (mode paper)
      4. Audit log
    """
    mode = config.mode
    logger.info(
        "Analysis & trading loop started (interval=%ds, mode=%s)",
        interval, mode,
    )
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

                        current_price = float(df_1h["close"].iloc[-1])

                        # ── 2. Analyse technique ──
                        work = {"1h": df_1h, "4h": df_4h}
                        tech_score = await tech_engine.analyze(symbol, work)

                        # ── 3. Multi-source signals ──
                        signals: dict[str, SourceSignal] = {
                            "technical": SourceSignal(
                                source="technical",
                                score=tech_score.total_score,
                                direction=tech_score.direction,
                                weight=0.35,
                                confidence=0.75,
                                key_signals=tech_score.key_signals,
                            ),
                        }

                        # 3a. On-chain analysis
                        try:
                            onchain_score = onchain_scorer.compute_score(symbol)
                            signals["onchain"] = SourceSignal(
                                source="onchain",
                                score=onchain_score.total_score,
                                direction=onchain_score.direction,
                                weight=0.20,
                                confidence=0.6,
                                key_signals=onchain_score.key_signals,
                                warnings=onchain_score.warnings,
                            )
                        except Exception as exc:
                            logger.debug("On-chain skip %s: %s", symbol, exc)

                        # 3b. Social sentiment
                        try:
                            social_score = await social_scorer.compute_score(symbol)
                            signals["social"] = SourceSignal(
                                source="social",
                                score=social_score.total_score,
                                direction=social_score.direction,
                                weight=0.15,
                                confidence=0.5,
                                key_signals=social_score.signals,
                                warnings=social_score.warnings,
                            )
                        except Exception as exc:
                            logger.debug("Social skip %s: %s", symbol, exc)

                        # 3c. News analysis
                        try:
                            news_score = await news_scorer.compute_score(symbol)
                            signals["news"] = SourceSignal(
                                source="news",
                                score=news_score.total_score,
                                direction=news_score.direction,
                                weight=0.15,
                                confidence=0.5,
                                key_signals=news_score.signals,
                                warnings=news_score.warnings,
                            )
                        except Exception as exc:
                            logger.debug("News skip %s: %s", symbol, exc)

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

                        # ── 6. Circuit Breaker check (BOTH paper and live) ──
                        if decision.order and circuit_breaker:
                            if not circuit_breaker.is_system_operational():
                                logger.warning(
                                    "Circuit breaker: system halted — skipping %s", symbol,
                                )
                                continue
                            if not circuit_breaker.check_symbol(symbol, current_price):
                                logger.warning(
                                    "Circuit breaker: %s blocked at $%.2f", symbol, current_price,
                                )
                                continue

                        # ── 7. Risk Manager check (BOTH paper and live) ──
                        if decision.order and risk_manager:
                            portfolio_value = 100_000.0  # default
                            if paper_exchange:
                                ps = paper_exchange.get_state()
                                portfolio_value = ps.current_capital
                            elif live_trading_engine:
                                live_status = live_trading_engine.get_status()
                                portfolio_value = live_status.get("portfolio_value", 100_000.0)

                            # Compute ATR for better risk assessment
                            atr_val = None
                            try:
                                if df_1h is not None and len(df_1h) >= 14:
                                    high_low = df_1h["high"] - df_1h["low"]
                                    atr_val = float(high_low.rolling(14).mean().iloc[-1])
                            except Exception:
                                pass

                            risk_assessment = risk_manager.assess_trade(
                                symbol=symbol,
                                side=decision.order.side,
                                entry_price=current_price,
                                portfolio_value=portfolio_value,
                                atr=atr_val,
                                position_size_usd=decision.order.quantity_usd,
                            )

                            if not risk_assessment.checks_passed:
                                logger.warning(
                                    "Risk check FAILED for %s %s: %s — $%.2f rejected",
                                    symbol, decision.order.side,
                                    risk_assessment.failed_checks,
                                    decision.order.quantity_usd,
                                )
                                continue

                            # Adjust size per risk recommendation
                            decision.order.quantity_usd = min(
                                decision.order.quantity_usd,
                                risk_assessment.recommended_size,
                            )

                        # ── 8. Execution ──
                        if decision.order:
                            if mode == "live" and live_trading_engine:
                                # ── LIVE TRADING ──
                                atr_val = None
                                try:
                                    if df_1h is not None and len(df_1h) >= 14:
                                        high_low = df_1h["high"] - df_1h["low"]
                                        atr_val = float(high_low.rolling(14).mean().iloc[-1])
                                except Exception:
                                    pass

                                record = await live_trading_engine.execute_trade(
                                    symbol=symbol,
                                    side=decision.order.side,
                                    quantity_usd=decision.order.quantity_usd,
                                    score=ai_result["score"],
                                    action=decision.action,
                                    entry_price=current_price,
                                    atr=atr_val,
                                    strategy="ai_core",
                                )

                                if record.status == "filled":
                                    logger.info(
                                        "✅ LIVE: %s %s $%.2f @ %.2f [%s]",
                                        symbol, decision.order.side.upper(),
                                        record.filled_value_usd,
                                        record.execution_price,
                                        decision.action,
                                    )
                                elif record.status == "rejected":
                                    logger.warning(
                                        "❌ LIVE REJECTED: %s %s — %s",
                                        symbol, decision.order.side, record.error,
                                    )

                            elif paper_exchange:
                                # ── PAPER TRADING ──
                                paper_exchange.update_price(symbol, current_price)
                                await paper_exchange.create_order(
                                    symbol=symbol,
                                    side=decision.order.side,
                                    quantity=0.0,
                                    quantity_usd=decision.order.quantity_usd,
                                    order_type=decision.order.order_type.value,
                                    slippage_bps=10,
                                )

                        # ── 9. Telegram alerts ──
                        if ai_result["score"] >= 80:
                            alerter = get_telegram_alerter()
                            await alerter.send_opportunity(
                                symbol=symbol,
                                score=ai_result["score"],
                                action=decision.action,
                                direction=ai_result["direction"],
                                explanation=ai_result.get("reason", ""),
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

            # Vérifier le drawdown pour les alertes (paper + live)
            state = paper_exchange.get_state()
            if state.total_pnl_pct <= -5.0:
                alerter = get_telegram_alerter()
                status = "critical" if state.total_pnl_pct <= -15.0 else "warning"
                await alerter.send_drawdown_alert(
                    drawdown_pct=abs(state.total_pnl_pct),
                    status=status,
                    current_capital=state.current_capital,
                    initial_capital=state.initial_capital,
                )

                # Auto-trigger circuit breaker on severe drawdown in live mode
                if (
                    mode == "live"
                    and live_trading_engine
                    and state.total_pnl_pct <= -20.0
                    and not live_trading_engine.emergency_stop.is_active
                ):
                    live_trading_engine.trigger_emergency_stop(
                        level="hard",
                        triggered_by="auto_drawdown",
                        reason=f"Drawdown {state.total_pnl_pct:.1f}% exceeds 20% threshold",
                    )
                    logger.critical(
                        "AUTO EMERGENCY STOP: drawdown %.1f%% triggered hard stop",
                        state.total_pnl_pct,
                    )

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

    # ── Startup validation ──
    _validate_startup()

    bg_tasks: list[asyncio.Task] = []
    paper_exchange: PaperExchange | None = None
    live_trading_engine = None
    ai_agent: CentralAIAgent | None = None
    tech_engine = None
    decision_matrix: DecisionMatrix | None = None
    risk_manager = None
    circuit_breaker = None
    onchain_scorer = None
    social_scorer = None
    news_scorer = None

    if config.mode in ("paper", "live"):
        try:
            # ── Risk Manager (always — both paper and live) ──
            from src.risk.manager import RiskLimits, RiskManager
            risk_manager = RiskManager(RiskLimits())
            await risk_manager.start()
            _instances["risk_manager"] = risk_manager
            logger.info("RiskManager initialized (safety checks active)")

            # ── Circuit Breaker (always — both paper and live) ──
            from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
            circuit_breaker = CircuitBreaker(CircuitBreakerConfig())
            await circuit_breaker.start()
            _instances["circuit_breaker"] = circuit_breaker
            logger.info("CircuitBreaker initialized (system protection active)")

            # ── Paper Exchange (always — tracks portfolio, PnL) ──
            paper_exchange = PaperExchange(initial_capital=100_000.0)
            await paper_exchange.start()
            register_paper_exchange(paper_exchange)
            _instances["paper_exchange"] = paper_exchange
            logger.info("PaperExchange initialized ($100,000)")

            # ── Decision Matrix ──
            decision_matrix = DecisionMatrix()
            register_decision_matrix(decision_matrix)
            _instances["decision_matrix"] = decision_matrix

            # ── AI Agent ──
            ai_agent = CentralAIAgent()
            await ai_agent.start()
            _instances["ai_agent"] = ai_agent
            logger.info("CentralAIAgent initialized (v2 calibrated)")

            # ── Technical Engine ──
            from src.analysis.technical.engine import TechnicalAnalysisEngine
            tech_engine = TechnicalAnalysisEngine()
            await tech_engine.start()
            _instances["technical"] = tech_engine

            # ── On-chain Engine ──
            from src.analysis.onchain.scorer import OnChainScorer
            onchain_scorer = OnChainScorer()
            _instances["onchain"] = onchain_scorer

            # ── Social Engine ──
            from src.analysis.social.scorer import SocialScorer
            social_scorer = SocialScorer()
            _instances["social"] = social_scorer

            # ── News Engine ──
            from src.analysis.news.scorer import NewsScorer
            news_scorer = NewsScorer()
            _instances["news"] = news_scorer

            # ── LIVE Trading Engine (mode live only) ──
            if config.mode == "live":
                api_key, api_secret = _load_api_keys()
                if not api_key or not api_secret:
                    logger.critical(
                        "LIVE MODE: No API keys available! Set CRYPTOAI_BINANCE_KEY/_SECRET "
                        "or store via Settings API. Trading DISABLED."
                    )
                    config.mode = "paper"  # fallback to paper
                else:
                    from src.execution.live_trading import LiveTradingConfig, LiveTradingEngine
                    live_config = LiveTradingConfig(
                        exchange_id="binance",
                        api_key=api_key,
                        api_secret=api_secret,
                        testnet=False,
                    )
                    live_trading_engine = LiveTradingEngine(live_config)
                    await live_trading_engine.start()
                    _instances["live_trading_engine"] = live_trading_engine
                    logger.info(
                        "⚠️  LiveTradingEngine initialized — REAL MONEY trading active on Binance"
                    )

            # ── Background tasks ──
            bg_tasks.append(
                asyncio.create_task(_market_collector_loop(interval=60))
            )
            bg_tasks.append(
                asyncio.create_task(
                    _analysis_and_trading_loop(
                        ai_agent=ai_agent,
                        tech_engine=tech_engine,
                        onchain_scorer=onchain_scorer,
                        social_scorer=social_scorer,
                        news_scorer=news_scorer,
                        decision_matrix=decision_matrix,
                        paper_exchange=paper_exchange,
                        live_trading_engine=live_trading_engine,
                        risk_manager=risk_manager,
                        circuit_breaker=circuit_breaker,
                        interval=300,
                    )
                )
            )

            logger.info(
                "Background services started (%d tasks, mode=%s, safety=ON)",
                len(bg_tasks), config.mode,
            )
        except Exception as exc:
            logger.critical("Failed to start background services: %s", exc, exc_info=True)

    yield

    # ===================== SHUTDOWN =====================
    logger.info("Arrêt des services background…")
    for task in bg_tasks:
        task.cancel()
    if bg_tasks:
        await asyncio.gather(*bg_tasks, return_exceptions=True)

    if live_trading_engine:
        await live_trading_engine.stop()
    if circuit_breaker:
        await circuit_breaker.stop()
    if risk_manager:
        await risk_manager.stop()
    if tech_engine:
        await tech_engine.stop()
    if ai_agent:
        await ai_agent.stop()
    if paper_exchange:
        await paper_exchange.stop()

    # Fermer le Telegram alerter
    global _telegram_alerter
    if _telegram_alerter is not None:
        await _telegram_alerter.close()
        _telegram_alerter = None

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
# Restrict origins in production mode for security
if config.mode == "live":
    _allowed_origins = (
        config.allowed_origins
        if hasattr(config, "allowed_origins") and config.allowed_origins
        else ["http://localhost:3000"]
    )
else:
    _allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─── JWT Authentication ──────────────────────────────────────
# Validate JWT secret in production
if config.mode == "live" and config.jwt_secret in ("changeme_in_prod", "", "changeme"):
    logger.critical(
        "JWT secret is default value in LIVE mode! "
        "Set CRYPTOAI_JWT_SECRET environment variable."
    )
app.add_middleware(JWTAuthMiddleware)

# ─── Inclusion des routeurs ──────────────────────────────────
app.include_router(health.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(risk.router)
app.include_router(ai.router)
app.include_router(performance.router)
app.include_router(execution.router)
app.include_router(settings.router)
app.include_router(stream.router)
app.include_router(trades.router)
app.include_router(screener.router)
app.include_router(backtesting.router)
app.include_router(trading.router)


# ─── Telegram Alerter (lazy) ───────────────────────────────────
_telegram_alerter = None


def get_telegram_alerter():
    """Retourne l'instance TelegramAlerter (initialisation lazy)."""
    global _telegram_alerter
    if _telegram_alerter is None:
        from src.notifications.telegram_bot import create_telegram_alerter
        _telegram_alerter = create_telegram_alerter()
    return _telegram_alerter


# ─── Startup validation ─────────────────────────────────────────

def _validate_startup() -> None:
    """Validation de sécurité au démarrage."""
    warnings: list[str] = []
    errors: list[str] = []

    # Check JWT secret
    if config.jwt_secret in ("changeme_in_prod", "", "changeme"):
        if config.mode == "live":
            errors.append("JWT secret is default value — must be changed for production")
        else:
            warnings.append("JWT secret is default value — change before going live")

    # Check encryption key
    if not config.encryption_key:
        warnings.append("No CRYPTOAI_ENCRYPTION_KEY set — API keys cannot be encrypted")

    # Check mode
    if config.mode == "live":
        api_key = os.getenv("CRYPTOAI_BINANCE_KEY", config.binance_api_key)
        if not api_key:
            errors.append("LIVE mode but no Binance API key configured")

    for msg in warnings:
        logger.warning("Startup warning: %s", msg)
    for msg in errors:
        logger.error("Startup ERROR: %s", msg)

    if errors:
        logger.critical(
            "%d startup errors — system may not be functional in live mode",
            len(errors),
        )


def _load_api_keys() -> tuple[str, str]:
    """
    Charge les clés API Binance de manière sécurisée.

    Ordre de résolution:
    1. Vault chiffré (data/api_keys.enc)
    2. Variables d'environnement (CRYPTOAI_BINANCE_KEY / _SECRET)
    3. Config file (déconseillé)
    """
    # 1. Vault chiffré
    try:
        from src.execution.live_trading import ApiKeyVault
        vault = ApiKeyVault()
        keys = vault.load_keys("binance")
        if keys and keys[0] and keys[1]:
            logger.info("API keys loaded from encrypted vault")
            return keys
    except Exception as exc:
        logger.debug("Vault key load skipped: %s", exc)

    # 2. Env vars
    api_key = os.getenv("CRYPTOAI_BINANCE_KEY", "")
    api_secret = os.getenv("CRYPTOAI_BINANCE_SECRET", "")
    if api_key and api_secret:
        logger.info("API keys loaded from environment variables")
        return api_key, api_secret

    # 3. Config (fallback — déconseillé)
    if config.binance_api_key and config.binance_api_secret:
        logger.warning("Using API keys from config file — INSECURE for production")
        return config.binance_api_key, config.binance_api_secret

    return "", ""


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
