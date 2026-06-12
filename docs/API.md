# API Documentation — CryptoAI

> **Plateforme de trading crypto autonome pilotee par IA**
> Documentation complete de l'API REST.

**Base URL :** `http://localhost:8000`

**Documentation interactive :**
- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`

---

## Table des Matieres

1. [Authentication](#1-authentication)
2. [Health](#2-health)
3. [Market Data](#3-market-data)
4. [Portfolio](#4-portfolio)
5. [Risk](#5-risk)
6. [AI Decisions](#6-ai-decisions)
7. [Execution](#7-execution)
8. [Performance](#8-performance)
9. [Settings](#9-settings)
10. [Schemas](#10-schemas)
11. [Error Handling](#11-error-handling)
12. [Rate Limiting](#12-rate-limiting)

---

## 1. Authentication

### 1.1 Login

Authentifie un utilisateur et retourne un token JWT.

```
POST /api/v1/auth/login
```

**Request Body :**
```json
{
  "username": "trader",
  "password": "your_secure_password"
}
```

**Response (200) :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Response (401) :**
```json
{
  "error": "AUTH_FAILED",
  "message": "Identifiants invalides",
  "code": "INVALID_CREDENTIALS"
}
```

### 1.2 Refresh Token

Refraichit un token expire.

```
POST /api/v1/auth/refresh
```

**Headers :**
```
Authorization: Bearer <token>
```

**Response (200) :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 1.3 API Key Management

Cree ou revoque une cle API pour l'acces automatise.

```
POST   /api/v1/auth/api-keys
GET    /api/v1/auth/api-keys
DELETE /api/v1/auth/api-keys/{key_id}
```

---

## 2. Health

Endpoints de verification de l'etat du systeme. Ne necessitent pas d'authentification. Prefixe : `/`

### 2.1 Health Check

Verification de base que l'API est en ligne.

```
GET /health
```

**Response (200) :**
```json
{
  "status": "ok",
  "timestamp": "2026-06-12T10:30:00Z",
  "version": "1.0.0"
}
```

### 2.2 Readiness Check

Verification que tous les services (base de donnees, Redis, WebSocket) sont operationnels.

```
GET /health/ready
```

**Response (200) :**
```json
{
  "status": "ready",
  "timestamp": "2026-06-12T10:30:00Z",
  "checks": {
    "database": true,
    "redis": true,
    "websocket": true
  }
}
```

### 2.3 System Metrics

Metriques systeme de base.

```
GET /health/metrics
```

**Response (200) :**
```json
{
  "uptime_seconds": 84321,
  "active_connections": 5,
  "memory_usage_mb": 128,
  "cpu_percent": 12.5,
  "requests_total": 1542,
  "errors_total": 3
}
```

---

## 3. Market Data

Endpoints de donnees marche en temps reel et historique. Prefixe : `/api/v1/market`

### 3.1 Get Ticker

Recupere le ticker temps reel pour un symbole.

```
GET /api/v1/market/ticker/{symbol}
```

**Path Parameters :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Symbole de trading (ex: `BTC/USDT`) |

**Exemple :**
```bash
curl http://localhost:8000/api/v1/market/ticker/BTC/USDT
```

**Response (200) :**
```json
{
  "symbol": "BTC/USDT",
  "data": {
    "bid": "67500.50",
    "ask": "67501.00",
    "last": "67500.80",
    "baseVolume": "12450.5",
    "quoteVolume": "840321000",
    "high24h": "68200.00",
    "low24h": "66800.00",
    "change24h": "1.25",
    "timestamp": "1702483200000"
  },
  "timestamp": "2026-06-12T10:30:00Z"
}
```

**Response (404) :**
```json
{
  "detail": "Ticker non disponible"
}
```

### 3.2 Get Order Book

Recupere le carnet d'ordres pour un symbole.

```
GET /api/v1/market/orderbook/{symbol}
```

**Path Parameters :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Symbole de trading (ex: `BTC/USDT`) |

**Exemple :**
```bash
curl http://localhost:8000/api/v1/market/orderbook/BTC/USDT
```

**Response (200) :**
```json
{
  "symbol": "BTC/USDT",
  "data": {
    "bids": [
      ["67500.50", "12.5"],
      ["67500.00", "8.3"],
      ["67499.50", "15.1"]
    ],
    "asks": [
      ["67501.00", "10.2"],
      ["67501.50", "7.8"],
      ["67502.00", "14.3"]
    ],
    "timestamp": "1702483200000",
    "spread": 0.50,
    "mid_price": 67500.75,
    "imbalance": 0.12,
    "total_bid_volume": 843.5,
    "total_ask_volume": 721.3
  },
  "timestamp": "2026-06-12T10:30:00Z"
}
```

### 3.3 Get OHLCV

Recupere les donnees OHLCV historiques.

```
GET /api/v1/market/ohlcv/{symbol}
```

**Path Parameters :**

| Parametre | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Symbole de trading (ex: `BTC/USDT`) |

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `timeframe` | string | `1h` | Timeframe (`1m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d`, `1w`) |
| `limit` | integer | `100` | Nombre de bougies (min: 1, max: 1000) |

**Exemple :**
```bash
curl "http://localhost:8000/api/v1/market/ohlcv/BTC/USDT?timeframe=1h&limit=50"
```

**Response (200) :**
```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "data": [
    {
      "timestamp": "2026-06-12T09:00:00Z",
      "open": 67400.00,
      "high": 67550.00,
      "low": 67380.00,
      "close": 67500.80,
      "volume": 1250.5
    },
    {
      "timestamp": "2026-06-12T08:00:00Z",
      "open": 67350.00,
      "high": 67420.00,
      "low": 67200.00,
      "close": 67400.00,
      "volume": 980.3
    }
  ]
}
```

### 3.4 Get Watchlist

Retourne la liste des symboles surveilles.

```
GET /api/v1/market/watchlist
```

**Exemple :**
```bash
curl http://localhost:8000/api/v1/market/watchlist
```

**Response (200) :**
```json
{
  "watchlist": [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "ADA/USDT",
    "XRP/USDT",
    "DOT/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "MATIC/USDT",
    "ATOM/USDT",
    "UNI/USDT"
  ],
  "count": 12
}
```

---

## 4. Portfolio

Endpoints de gestion du portefeuille. Prefixe : `/api/v1/portfolio`

### 4.1 Get Portfolio State

Etat actuel du portefeuille.

```
GET /api/v1/portfolio
```

**Headers :**
```
Authorization: Bearer <token>
```

**Response (200) :**
```json
{
  "total_equity_usd": 101234.50,
  "cash_usd": 25308.62,
  "positions_value_usd": 75925.88,
  "cash_reserve_pct": 25.0,
  "positions": [
    {
      "symbol": "BTC/USDT",
      "strategy": "trend_following",
      "quantity": 0.85,
      "entry_price": 65200.00,
      "current_price": 67500.80,
      "value_usd": 57375.68,
      "unrealized_pnl_usd": 1955.68,
      "unrealized_pnl_pct": 3.53,
      "weight_pct": 18.9,
      "stop_loss": 64200.00,
      "take_profit": 70000.00
    },
    {
      "symbol": "ETH/USDT",
      "strategy": "momentum",
      "quantity": 8.5,
      "entry_price": 3450.00,
      "current_price": 3580.00,
      "value_usd": 30430.00,
      "unrealized_pnl_usd": 1105.00,
      "unrealized_pnl_pct": 3.77,
      "weight_pct": 10.0,
      "stop_loss": 3380.00,
      "take_profit": 3800.00
    }
  ],
  "strategy_allocations": {
    "trend_following": { "target_pct": 30.0, "actual_pct": 28.5, "status": "ok" },
    "momentum": { "target_pct": 25.0, "actual_pct": 24.0, "status": "ok" },
    "mean_reversion": { "target_pct": 20.0, "actual_pct": 0.0, "status": "no_signal" },
    "swing_trading": { "target_pct": 25.0, "actual_pct": 22.5, "status": "ok" }
  },
  "daily_pnl_usd": 450.25,
  "daily_pnl_pct": 0.45
}
```

### 4.2 Get Allocation Targets

Allocations cibles par strategie.

```
GET /api/v1/portfolio/allocations
```

### 4.3 Update Allocation Targets

Met a jour les allocations cibles.

```
PUT /api/v1/portfolio/allocations
```

**Request Body :**
```json
{
  "trend_following": 0.25,
  "momentum": 0.25,
  "mean_reversion": 0.25,
  "swing_trading": 0.25
}
```

### 4.4 Get Position Details

Details d'une position specifique.

```
GET /api/v1/portfolio/positions/{symbol}
```

### 4.5 Trigger Rebalance

Declenche un rebalancement manuel du portefeuille.

```
POST /api/v1/portfolio/rebalance
```

---

## 5. Risk

Endpoints de gestion des risques. Prefixe : `/api/v1/risk`

### 5.1 Get Risk State

Etat actuel des metriques de risque.

```
GET /api/v1/risk
```

**Headers :**
```
Authorization: Bearer <token>
```

**Response (200) :**
```json
{
  "max_drawdown_pct": 8.5,
  "daily_loss_pct": 1.2,
  "weekly_loss_pct": 3.8,
  "monthly_loss_pct": 5.1,
  "var_95_pct": 2.3,
  "cvar_95_pct": 3.1,
  "circuit_breaker": {
    "state": "CLOSED",
    "triggers_today": 0,
    "level_1_triggered": false,
    "level_2_triggered": false,
    "level_3_triggered": false
  },
  "limits": {
    "max_daily_loss_pct": 5.0,
    "max_weekly_loss_pct": 12.0,
    "max_monthly_loss_pct": 20.0,
    "max_drawdown_pct": 25.0,
    "max_position_pct": 25.0,
    "max_sector_pct": 40.0,
    "min_cash_reserve_pct": 15.0
  },
  "stop_losses_active": 2,
  "take_profits_active": 1
}
```

### 5.2 Get Risk Limits

Limites de risque configurees.

```
GET /api/v1/risk/limits
```

### 5.3 Update Risk Limits

Met a jour les limites de risque.

```
PUT /api/v1/risk/limits
```

**Request Body :**
```json
{
  "max_daily_loss_pct": 5.0,
  "max_weekly_loss_pct": 12.0,
  "max_monthly_loss_pct": 20.0,
  "max_drawdown_pct": 25.0
}
```

### 5.4 Get Circuit Breaker State

Etat du circuit breaker.

```
GET /api/v1/risk/circuit-breaker
```

### 5.5 Reset Circuit Breaker

Reinitialise manuellement le circuit breaker.

```
POST /api/v1/risk/circuit-breaker/reset
```

### 5.6 Exposure Analysis

Analyse detaillee des exposures.

```
GET /api/v1/risk/exposure
```

---

## 6. AI Decisions

Endpoints du noyau IA. Prefixe : `/api/v1/ai`

### 6.1 Get Current Decision

Decision actuelle de l'IA pour un symbole.

```
GET /api/v1/ai/decision/{symbol}
```

**Headers :**
```
Authorization: Bearer <token>
```

**Response (200) :**
```json
{
  "symbol": "BTC/USDT",
  "timestamp": "2026-06-12T10:30:00Z",
  "action": "BUY",
  "confidence": 72.5,
  "sizing_pct": 10.0,
  "signals": {
    "technical": {
      "score": 68,
      "trend": "bullish",
      "strength": "moderate",
      "key_indicators": {
        "ema_9_21": "bullish_cross",
        "rsi_14": 58.3,
        "adx": 28.5,
        "bb_position": "middle"
      }
    },
    "orderbook": {
      "score": 75,
      "imbalance": 0.32,
      "spread": 0.05,
      "support_resistance": {
        "support": 67000,
        "resistance": 68000
      }
    },
    "onchain": {
      "score": 45,
      "whale_activity": "neutral",
      "exchange_netflow": "outflow_1000_btc"
    },
    "sentiment": {
      "score": 82,
      "overall": "positive",
      "sources": {
        "twitter": 0.75,
        "reddit": 0.68,
        "news": 0.85
      }
    }
  },
  "risk_assessment": {
    "max_position_size": 25000.00,
    "stop_loss_price": 66150.78,
    "take_profit_price": 69750.00,
    "risk_reward_ratio": 2.15
  },
  "explanation": "Tendance haussiere confirmee par croisement EMA 9/21 avec ADX a 28.5 (>25). Le carnet d'ordres montre un desequilibre acheteur significatif (0.32). Le sentiment Twitter est fortement positif suite a l'annonce du partenariat. Position sizing a 10% du capital (confiance : 72.5/100). Stop loss a 2.0x ATR ($66,150.78), take profit a 2.15:1 ($69,750.00)."
}
```

### 6.2 Get Decision History

Historique des decisions IA.

```
GET /api/v1/ai/decisions
```

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `symbol` | string | - | Filtrer par symbole |
| `limit` | integer | `50` | Nombre de decisions |
| `offset` | integer | `0` | Pagination |

### 6.3 Get Feature Fusion Scores

Scores de fusion des features pour un symbole.

```
GET /api/v1/ai/fusion/{symbol}
```

**Response (200) :**
```json
{
  "symbol": "BTC/USDT",
  "timestamp": "2026-06-12T10:30:00Z",
  "fused_score": 68.5,
  "weights": {
    "technical": 0.35,
    "onchain": 0.20,
    "sentiment": 0.15,
    "orderbook": 0.15,
    "risk": 0.15
  },
  "contributions": {
    "technical": 23.8,
    "onchain": 9.0,
    "sentiment": 12.3,
    "orderbook": 11.2,
    "risk": 12.2
  },
  "divergence_detected": false,
  "consensus_level": "high"
}
```

### 6.4 Get Signal Sources

Signaux bruts de chaque source d'analyse.

```
GET /api/v1/ai/signals/{symbol}
```

---

## 7. Execution

Endpoints d'execution des ordres. Prefixe : `/api/v1/execution`

### 7.1 Execute Order

Soumet un ordre d'execution.

```
POST /api/v1/execution/orders
```

**Headers :**
```
Authorization: Bearer <token>
```

**Request Body :**
```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "limit",
  "quantity": 0.5,
  "price": 67000.00,
  "time_in_force": "GTC",
  "reduce_only": false,
  "post_only": true,
  "strategy": "trend_following",
  "client_order_id": "tf-btc-20260612-001"
}
```

**Response (201) :**
```json
{
  "order_id": "ord_abc123def456",
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "limit",
  "quantity": 0.5,
  "filled_quantity": 0.0,
  "price": 67000.00,
  "status": "SUBMITTED",
  "created_at": "2026-06-12T10:30:00Z"
}
```

### 7.2 Get Order Status

Verifie le statut d'un ordre.

```
GET /api/v1/execution/orders/{order_id}
```

### 7.3 Cancel Order

Annule un ordre.

```
DELETE /api/v1/execution/orders/{order_id}
```

### 7.4 Get Open Orders

Liste tous les ordres ouverts.

```
GET /api/v1/execution/orders
```

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `symbol` | string | - | Filtrer par symbole |
| `strategy` | string | - | Filtrer par strategie |

### 7.5 Get Order History

Historique des ordres executes.

```
GET /api/v1/execution/orders/history
```

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `symbol` | string | - | Filtrer par symbole |
| `limit` | integer | `50` | Nombre d'ordres |
| `offset` | integer | `0` | Pagination |

### 7.6 Get Exchange Status

Statut des connexions aux exchanges.

```
GET /api/v1/execution/exchanges
```

**Response (200) :**
```json
{
  "exchanges": [
    {
      "name": "binance",
      "connected": true,
      "latency_ms": 45,
      "rate_limit_remaining": 1150,
      "mode": "live"
    },
    {
      "name": "bybit",
      "connected": true,
      "latency_ms": 52,
      "rate_limit_remaining": 580,
      "mode": "paper"
    }
  ]
}
```

---

## 8. Performance

Endpoints de metriques de performance. Prefixe : `/api/v1/performance`

### 8.1 Get Performance Summary

Resume des performances globales.

```
GET /api/v1/performance
```

**Headers :**
```
Authorization: Bearer <token>
```

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `period` | string | `30d` | Periode (`1d`, `7d`, `30d`, `90d`, `1y`, `all`) |

**Response (200) :**
```json
{
  "period": "30d",
  "total_return_pct": 4.25,
  "total_return_usd": 4250.00,
  "cagr": 18.5,
  "total_trades": 24,
  "win_rate": 62.5,
  "profit_factor": 1.85,
  "sharpe_ratio": 1.42,
  "sortino_ratio": 1.88,
  "calmar_ratio": 1.65,
  "max_drawdown_pct": 8.2,
  "max_drawdown_usd": 8200.00,
  "avg_win_usd": 425.00,
  "avg_loss_usd": 185.00,
  "largest_win_usd": 1250.00,
  "largest_loss_usd": 450.00,
  "avg_holding_time_hours": 18.5,
  "best_day": "2026-06-08",
  "worst_day": "2026-06-03"
}
```

### 8.2 Get Equity Curve

Courbe d'equity cumulee.

```
GET /api/v1/performance/equity-curve
```

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `period` | string | `30d` | Periode |
| `granularity` | string | `1d` | Granularite (`1h`, `1d`) |

### 8.3 Get Trade History

Historique des trades.

```
GET /api/v1/performance/trades
```

**Query Parameters :**

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `strategy` | string | - | Filtrer par strategie |
| `symbol` | string | - | Filtrer par symbole |
| `limit` | integer | `50` | Nombre de trades |
| `offset` | integer | `0` | Pagination |

**Response (200) :**
```json
{
  "trades": [
    {
      "trade_id": "trd_001",
      "symbol": "BTC/USDT",
      "strategy": "trend_following",
      "side": "buy",
      "entry_price": 65200.00,
      "exit_price": 67800.00,
      "quantity": 1.0,
      "pnl_usd": 2600.00,
      "pnl_pct": 3.99,
      "entry_time": "2026-06-10T08:00:00Z",
      "exit_time": "2026-06-12T10:00:00Z",
      "holding_hours": 50.0,
      "exit_reason": "take_profit"
    }
  ],
  "total": 24,
  "page": 1,
  "per_page": 50
}
```

### 8.4 Performance by Strategy

Performance detaillee par strategie.

```
GET /api/v1/performance/strategies
```

### 8.5 Get Metrics Detail

Metriques detaillees (VaR, CVaR, Ulcer Index, etc.).

```
GET /api/v1/performance/metrics
```

---

## 9. Settings

Endpoints de configuration. Prefixe : `/api/v1/settings`

### 9.1 Get System Config

Configuration actuelle du systeme.

```
GET /api/v1/settings/config
```

**Headers :**
```
Authorization: Bearer <token>
```

### 9.2 Update System Config

Met a jour la configuration (partielle).

```
PATCH /api/v1/settings/config
```

### 9.3 Get Strategy Params

Parametres actuels des strategies.

```
GET /api/v1/settings/strategies
```

### 9.4 Update Strategy Params

Met a jour les parametres d'une strategie.

```
PUT /api/v1/settings/strategies/{strategy_name}
```

### 9.5 Get Watchlist Settings

Configuration de la watchlist.

```
GET /api/v1/settings/watchlist
```

### 9.6 Update Watchlist

Met a jour la watchlist.

```
PUT /api/v1/settings/watchlist
```

**Request Body :**
```json
{
  "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
}
```

---

## 10. Schemas

### 10.1 Order Types

```typescript
enum OrderType {
  MARKET       = "market",        // Execution immediate au meilleur prix
  LIMIT        = "limit",         // Execution au prix limite ou meilleur
  STOP_LOSS    = "stop_loss",     // Ordre stop declenche a un prix
  STOP_LIMIT   = "stop_limit",    // Ordre limite post-declenchement
  TRAILING_STOP = "trailing_stop", // Stop suiveur
  TWAP         = "twap",          // Execution averagee dans le temps
  VWAP         = "vwap"           // Execution ponderee par le volume
}
```

### 10.2 Order Status

```typescript
enum OrderStatus {
  PENDING   = "pending",    // En attente de soumission
  SUBMITTED = "submitted",  // Soumis a l'exchange
  PARTIAL   = "partial",    // Partiellement rempli
  FILLED    = "filled",     // Completement rempli
  CANCELLED = "cancelled",  // Annule par l'utilisateur
  REJECTED  = "rejected",   // Rejete par l'exchange
  EXPIRED   = "expired",    // Expire
  FAILED    = "failed"      // Erreur interne
}
```

### 10.3 Action Types

```typescript
enum ActionType {
  STRONG_BUY  = "strong_buy",   // Achat agressif (confiance >= 80)
  BUY         = "buy",          // Achat standard (confiance >= 65)
  REINFORCE   = "reinforce",    // Renforcement position existante
  HOLD        = "hold",         // Attendre (confiance < 40)
  REDUCE      = "reduce",       // Reduction partielle
  SELL        = "sell",         // Vente standard (confiance >= 65)
  STRONG_SELL = "strong_sell"   // Vente agressive (confiance >= 80)
}
```

### 10.4 Standard Error Response

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Un ou plusieurs champs sont invalides",
    "details": [
      {
        "field": "quantity",
        "code": "INVALID_VALUE",
        "message": "La quantite doit etre superieure a 0"
      }
    ],
    "traceId": "abc123def456"
  }
}
```

### 10.5 Pagination

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "perPage": 50,
    "total": 150,
    "totalPages": 3,
    "hasNext": true,
    "hasPrev": false
  }
}
```

---

## 11. Error Handling

### 11.1 Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INTERNAL_ERROR` | 500 | Erreur interne du serveur |
| `VALIDATION_FAILED` | 400 | Validation des entrees echouee |
| `INVALID_SYMBOL` | 400 | Symbole de trading invalide |
| `INVALID_TIMEFRAME` | 400 | Timeframe invalide |
| `NOT_FOUND` | 404 | Ressource non trouvee |
| `AUTH_FAILED` | 401 | Authentification echouee |
| `TOKEN_EXPIRED` | 401 | Token expire |
| `AUTHZ_DENIED` | 403 | Permission insuffisante |
| `RATE_LIMITED` | 429 | Trop de requetes |
| `ORDER_REJECTED` | 400 | Ordre rejete par l'exchange |
| `RISK_LIMIT_EXCEEDED` | 400 | Limite de risque depassee |
| `CIRCUIT_BREAKER_OPEN` | 503 | Circuit breaker ouvert |
| `INSUFFICIENT_FUNDS` | 400 | Fonds insuffisants |
| `INSUFFICIENT_DATA` | 400 | Donnees insuffisantes pour l'analyse |

### 11.2 Global Error Handler

Toutes les erreurs non gerees retournent une reponse standardisee :

```json
{
  "error": "INTERNAL_ERROR",
  "message": "Une erreur interne est survenue",
  "timestamp": "2026-06-12T10:30:00Z"
}
```

---

## 12. Rate Limiting

### 12.1 Default Limits

| Endpoint Groupe | Limite | Fenetre |
|-----------------|--------|---------|
| `/health*` | 60 req/min | 1 minute |
| `/api/v1/market/*` | 100 req/min | 1 minute |
| `/api/v1/portfolio/*` | 60 req/min | 1 minute |
| `/api/v1/risk/*` | 60 req/min | 1 minute |
| `/api/v1/ai/*` | 30 req/min | 1 minute |
| `/api/v1/execution/*` | 20 req/min | 1 minute |
| `/api/v1/performance/*` | 30 req/min | 1 minute |
| `/api/v1/settings/*` | 20 req/min | 1 minute |

### 12.2 Headers

Les limites sont communiquees via les headers de reponse :

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1702483200
Retry-After: 30
```

### 12.3 Rate Limit Exceeded

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Trop de requetes. Veuillez reessayer dans 30 secondes.",
    "retryAfter": 30
  }
}
```

---

## Appendice : Specification OpenAPI

La specification OpenAPI complete est disponible de maniere interactive :

| Interface | URL |
|-----------|-----|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

---

<p align="center">
  <i>Developpe avec rigueur, opere avec discipline</i>
</p>
