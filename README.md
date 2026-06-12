# CryptoAI

**Plateforme de trading crypto autonome pilotée par IA — Niveau Hedge Fund**

[![Python 3.12](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-2.17-FDB515?style=for-the-badge&logo=timescale&logoColor=white)](https://www.timescale.com/)
[![Redis](https://img.shields.io/badge/Redis-7.4-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

---

## Architecture Overview

```
                     ┌──────────────────────────────────────────┐
                     │            FRONTEND (Next.js 14)          │
                     │        Dashboard · Recharts · Dark Mode   │
                     └────────────────────┬─────────────────────┘
                                          │ REST API
                     ┌────────────────────▼─────────────────────┐
                     │           API GATEWAY (FastAPI)            │
                     │     /api/v1/ · Auth · Rate Limiting       │
                     └────────────────────┬─────────────────────┘
                                          │
         ┌────────────────────────────────┼────────────────────────────┐
         │                                │                            │
┌────────▼────────┐  ┌───────────────────▼──┐  ┌───────────────────▼──┐
│   MARKET DATA    │  │   ANALYSIS ENGINES    │  │   AI CORE            │
│                  │  │                      │  │                      │
│ • CCXT Providers │  │ • Technical (30+     │  │ • Feature Fusion     │
│ • WebSocket      │  │   indicators)        │  │   Engine             │
│ • Order Book     │  │ • Order Book (depth, │  │ • Confidence Scorer  │
│ • On-Chain       │  │   imbalance,         │  │ • Decision Matrix    │
│ • News/Social    │  │   slippage, spoof)   │  │ • Explanation Engine │
│                  │  │ • On-Chain (whales,  │  │                      │
│                  │  │   exchange flows)    │  └──────────┬───────────┘
│                  │  │ • Sentiment (news,   │             │
│                  │  │   social, telegram)  │             │
└──────────────────┘  └──────────────────────┘             │
                                          │
         ┌────────────────────────────────┼────────────────────────────┐
         │                                │                            │
┌────────▼────────┐  ┌───────────────────▼──┐  ┌───────────────────▼──┐
│  RISK MANAGER    │  │  PORTFOLIO MANAGER   │  │  EXECUTION ENGINE    │
│                  │  │                      │  │                      │
│ • ATR Stop Loss  │  │ • Multi-Strategy     │  │ • Paper Exchange     │
│ • Kelly Sizing   │  │   Allocation         │  │ • CCXT Live          │
│ • Circuit        │  │ • Auto-Rebalancing   │  │ • TWAP/VWAP          │
│   Breaker        │  │ • Sector Exposure    │  │ • Retry + Backoff    │
│ • Loss Limits    │  │ • Cash Reserve       │  │ • Slippage Control   │
└──────────────────┘  └──────────────────────┘  └──────────────────────┘

         ┌──────────────────────────────────────────────────────────────┐
         │                    DATA LAYER                                │
         │   TimescaleDB (Historical) + Redis (Real-Time / Cache)      │
         └──────────────────────────────────────────────────────────────┘
```

---

## Key Features

###  Multi-Source Analysis
- **Technical Analysis** — 30+ indicateurs vectorisés (EMA, RSI, MACD, ADX, Bollinger, Ichimoku, Supertrend, Donchian, ...)
- **Order Book Analysis** — Profondeur, déséquilibre, slippage, détection de spoofing
- **On-Chain Analysis** — Whale tracking, exchange flows, métriques de réseau
- **Sentiment Analysis** — Agrégation news, Twitter, Reddit, Telegram avec scoring

###  4 Trading Strategies
| Strategy | Logic | Entry | Exit |
|----------|-------|-------|------|
| **Trend Following** | EMA crossovers + ADX (>25) + Supertrend | Trend confirmation | Trend reversal |
| **Momentum** | RSI + ROC + Stochastic RSI + Volume | Strong momentum building | Momentum fading |
| **Mean Reversion** | Bollinger Bands + RSI extremes | Oversold/overbought | Return to mean |
| **Swing Trading** | Multi-timeframe confluence (1h/4h) | Alignment across TFs | Divergence |

###  AI Core
- **Feature Fusion Engine** — Fusion pondérée des 4 sources d'analyse
- **Decision Matrix** — 7 actions (STRONG_BUY → STRONG_SELL) avec sizing automatique
- **Confidence Scorer** — Score 0-100 basé sur consensus, strength, et divergence
- **Explanation Engine** — Raisonnement en langage naturel pour chaque décision

###  Institutional Risk Management
- **Stop Loss** — ATR-based (dynamique) + fixed percentage + hard limit
- **Take Profit** — Risk/Reward ratio (≥ 1.5) + trailing + partial TPs
- **Position Sizing** — Kelly Criterion adapté (25% fraction, win-rate estimé)
- **Circuit Breaker** — Multi-niveau (1m/5m/1h drawdown, volatilité, systémique)
- **Loss Limits** — Daily (5%), Weekly (12%), Monthly (20%), Max Drawdown (25%)
- **Exposure Limits** — Par position (25%), secteur (40%), cash reserve (15%)

###  Comprehensive Backtesting
- **Engine** — Simulation historique complète via PaperExchange
- **30+ Metrics** — Sharpe, Sortino, Calmar, VaR (95%), CVaR, CAGR, Profit Factor, Ulcer Index, Risk of Ruin
- **Strategy Comparator** — Classement pondéré (Sharpe × Win Rate × Drawdown)
- **Walk-Forward Optimization** — Train/validation splits glissants
- **Crisis Scenarios** — Slippage et volatilité accrus en conditions extrêmes
- **Benchmark** — Buy & Hold comparison avec Alpha/Beta

###  Execution
- **Paper Trading** — Capital fictif ($100k default), slippage simulé, fees (0.1%)
- **Live Trading** — Via CCXT (Binance, Bybit, OKX, Kraken, Coinbase)
- **Advanced Orders** — Market, Limit, Stop Loss, Stop Limit, Trailing Stop, TWAP, VWAP

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-org/cryptoai.git
cd cryptoai

# 2. Setup (venv + dependencies + pre-commit hooks)
make setup

# 3. Configure environment
cp .env.example .env
# Éditer .env avec vos clés API (optionnel pour paper trading)

# 4. Start infrastructure (TimescaleDB + Redis + Prometheus + Grafana)
docker compose up -d

# 5. Run paper trading
make run-paper

# 6. Open dashboard
cd frontend && npm run dev
# → http://localhost:3000
```

---

## Project Structure

```
cryptoai/
├── src/
│   ├── main.py                     # Point d'entrée système
│   ├── config.py                   # Configuration centralisée (Pydantic)
│   │
│   ├── api/                        # API REST FastAPI
│   │   ├── app.py                  # Application FastAPI + middleware
│   │   └── routes/                 # Routes API
│   │       ├── health.py           # Health check
│   │       └── market.py           # Données marché
│   │
│   ├── data/                       # Couche de données
│   │   └── market/
│   │       ├── schema.py           # OHLCV, Ticker, OrderBook (Pydantic V2)
│   │       ├── provider.py         # BaseProvider + CCXTProvider
│   │       └── websocket.py        # WebSocketManager
│   │
│   ├── analysis/                   # Moteurs d'analyse
│   │   ├── technical/              # 30+ indicateurs techniques
│   │   ├── orderbook/              # Analyse du carnet d'ordres
│   │   ├── onchain/                # Données on-chain
│   │   └── news/                   # Sentiment news/social
│   │
│   ├── core/                       # IA Core
│   │   ├── ai_agent.py             # CentralAIAgent + FeatureFusionEngine
│   │   └── decision_engine.py      # DecisionMatrix + OrderGenerator
│   │
│   ├── risk/                       # Gestion des risques
│   │   ├── manager.py              # RiskManager (ATR, Kelly, checks)
│   │   └── circuit_breaker.py      # CircuitBreaker (3 niveaux)
│   │
│   ├── portfolio/                  # Gestion de portefeuille
│   │   ├── manager.py              # PortfolioManager + rebalancing
│   │   └── strategies/             # 4 stratégies de trading
│   │       ├── trend_following.py
│   │       ├── momentum.py
│   │       ├── mean_reversion.py
│   │       └── swing_trading.py
│   │
│   ├── execution/                  # Exécution des ordres
│   │   ├── manager.py              # ExecutionManager (retry, rate limit)
│   │   └── paper.py                # PaperExchange (simulateur)
│   │
│   ├── backtesting/                # Backtesting
│   │   ├── engine.py               # BacktestEngine + BacktestResult
│   │   ├── metrics.py              # PerformanceMetrics (30+ métriques)
│   │   ├── comparator.py           # StrategyComparator + WalkForward
│   │   └── cli.py                  # CLI backtesting
│   │
│   └── utils/                      # Utilitaires
│       ├── database.py             # DatabaseManager (PostgreSQL + Redis)
│       ├── exceptions.py           # Hiérarchie d'exceptions
│       ├── logging.py              # Logger structuré JSON
│       └── security/               # Encryption, rate limiter, validation
│
├── frontend/                       # Dashboard Next.js 14
├── configs/                        # Configuration YAML
├── data/                           # Scripts d'initialisation DB
├── docs/                           # Documentation
├── tests/                          # Tests unitaires + intégration
├── scripts/                        # Scripts auxiliaires
│
├── docker-compose.yml              # Infrastructure complète
├── Dockerfile                      # Build image backend
├── Makefile                        # Commandes raccourcies
├── pyproject.toml                  # Configuration Python
└── .env.example                    # Variables d'environnement
```

---

## Available Commands

```bash
# ─── Installation ──────────────────────────
make install          # Install production dependencies
make install-dev     # Install dev dependencies + pre-commit hooks

# ─── Code Quality ──────────────────────────
make lint            # Run ruff linter
make format          # Run ruff formatter
make typecheck       # Run mypy type checker

# ─── Tests ─────────────────────────────────
make test            # Run all tests
make test-cov        # Run tests with coverage report
make test-unit       # Unit tests only
make test-integration # Integration tests only

# ─── Running ───────────────────────────────
make dev             # Dev mode (API hot-reload + infra)
make run             # Full system in paper mode
make run-paper       # Paper trading (alias for run)
make run-live        # Live trading (⚠ real money)
make run-worker      # Background worker (collect + analyze)

# ─── Docker ────────────────────────────────
make docker-up       # Start all services
make docker-down     # Stop all services
make docker-build    # Build images
make docker-logs     # Tail logs

# ─── Database ──────────────────────────────
make db-upgrade      # Run migrations
make db-migrate      # Create new migration
make db-rollback     # Rollback last migration

# ─── Backtesting ───────────────────────────
make backtest        # Run CLI backtest

# ─── Cleanup ───────────────────────────────
make clean           # Remove build artifacts
make clean-all       # Full cleanup (including data)
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Language** | Python | 3.12+ |
| **Backend Framework** | FastAPI | 0.115+ |
| **Validation** | Pydantic V2 | 2.10+ |
| **Data Processing** | Pandas + NumPy | 2.2+ / 2.1+ |
| **Time-Series DB** | TimescaleDB (PostgreSQL) | 2.17 (PG16) |
| **Cache / Real-Time** | Redis | 7.4 |
| **Exchange Connectivity** | CCXT | 4.4+ |
| **Technical Analysis** | TA-Lib compatible (pandas) | — |
| **Machine Learning** | scikit-learn, statsmodels | 1.5+ / 0.14+ |
| **Async Runtime** | asyncio + anyio | — |
| **Security** | cryptography, python-jose, passlib | — |
| **Monitoring** | Prometheus + Grafana | 2.55 / 11.3 |
| **Frontend** | Next.js (React) | 14 |
| **Charts** | Recharts | — |
| **Container** | Docker Compose | 3.9 |
| **Testing** | pytest + pytest-asyncio | 8.3+ |
| **Linting** | Ruff + mypy | 0.7+ / 1.13+ |

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture technique détaillée |
| [SETUP.md](docs/SETUP.md) | Guide d'installation et configuration |
| [API.md](docs/API.md) | Documentation complète de l'API REST |
| `/docs` (Swagger UI) | Documentation interactive (http://localhost:8000/docs) |

---

## Security Notes

> **Warning:** Ce logiciel interagit avec des exchanges crypto réels. L'utilisation en mode `live` engage des fonds réels. Testez extensivement en mode `paper` avant de passer en production.

- Les clés API sont chiffrées au repos (AES-256-GCM)
- Authentification JWT avec tokens rotatifs
- Rate limiting par endpoint (100 req/min par défaut)
- Validation Pydantic stricte sur toutes les entrées
- Circuit breaker coupe automatiquement le trading en conditions extrêmes
- Logging structuré sans données sensibles (PII, clés, tokens)

---

## License

MIT License — voir [LICENSE](LICENSE) pour les détails.

---

<p align="center">
  <i>Developpé avec rigueur, opéré avec discipline — CryptoAI</i>
</p>
