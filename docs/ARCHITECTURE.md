# CryptoAI — Architecture Technique

> **Version:** 1.0.0 — **Date:** 2026-06-12

---

## 1. Overview

CryptoAI est une plateforme de trading crypto autonome conçue selon une **architecture modulaire orientée data-flow**. Le système est bâti autour de quatre principes fondamentaux :

1. **Modularité stricte** — Chaque module a une responsabilité unique, clairement définie, et communique via des interfaces typées.
2. **Async-first** — L'ensemble du système est construit sur `asyncio` pour une gestion efficace des I/O (WebSocket, API exchanges, bases de données).
3. **Defense in Depth** — Les contrôles de risque sont en couches : validations au niveau trade, gestion des limites par stratégie, circuit breaker global.
4. **Transparence totale** — Chaque décision est enregistrée avec son raisonnement complet, ses sources, et son contexte de risque — aucune décision n'est une boîte noire.

Le système fonctionne selon un cycle de décision qui s'exécute à chaque tick de marché (1 seconde) et produit des rapports consolidés quotidiennement.

---

## 2. System Diagram

```
                                    ┌──────────────────────────────────────┐
                                    │         MARKET DATA LAYER           │
                                    │                                      │
                    ┌───────────────┼──────────────────────────────────────┼───────────────┐
                    │               │                                      │               │
                    ▼               ▼                                      ▼               ▼
            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
            │   CCXT/REST  │ │  WebSocket   │ │  On-Chain    │ │   News / Social API  │
            │   Providers  │ │  Streams     │ │  APIs        │ │   (Twitter, Reddit)  │
            │   (REST)     │ │  (WS)        │ │  (DeFiLlama) │ │                      │
            └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘
                   │                │                │                     │
                   ▼                ▼                ▼                     ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │                        DATA INGESTION PIPELINE                      │
            │        OHLCV · Ticker · OrderBook · Trades · Metrics · Articles    │
            │                    TimescaleDB + Redis Streams                      │
            └──────┬──────────────┬────────────────┬────────────────┬─────────────┘
                   │              │                │                │
                   ▼              ▼                ▼                ▼
            ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────────┐
            │ Technical│ │ OrderBook│ │  On-Chain    │ │   Sentiment      │
            │ Analysis │ │ Analysis │ │  Analysis    │ │   Analysis       │
            │          │ │          │ │              │ │                  │
            │• 30+ ind.│ │• Depth   │ │• Whale       │ │• News scoring    │
            │• Multi-TF │ │• Imbal. │ │  Tracking    │ │• Social scoring  │
            │• Patterns│ │• Slipp. │ │• Exchange    │ │• Telegram        │
            │          │ │• Spoof  │ │  Flow        │ │• Trend detection │
            └─────┬────┘ └────┬─────┘ └──────┬───────┘ └────────┬─────────┘
                  │           │               │                  │
                  ▼           ▼               ▼                  ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                   FEATURE FUSION ENGINE                     │
            │                                                             │
            │    Source  │ Weight  │ Score  │ Direction  │ Confidence     │
            │    ────────┼─────────┼────────┼────────────┼────────────    │
            │    Technical│  0.35  │  0-100 │ bullish    │    0.85        │
            │    Orderbook│  0.15  │  0-100 │ neutral    │    0.60        │
            │    On-chain │  0.20  │  0-100 │ bearish    │    0.70        │
            │    Sentiment│  0.15  │  0-100 │ bullish    │    0.55        │
            │    Risk     │  0.15  │  0-100 │ --         │    --          │
            │                                                             │
            │    → Fusion: Score pondéré + Consensus + Divergence        │
            └────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                     DECISION MATRIX                         │
            │                                                             │
            │        Score Range      →    Action        Max Alloc        │
            │        ─────────────────────────────────────────────        │
            │        > 80  + bullish  → STRONG_BUY     20.0%              │
            │        > 65  + bullish  → BUY            10.0%              │
            │        > 55  + bullish  → REINFORCE       5.0%              │
            │        45-55            → HOLD            0.0%              │
            │        < 35  + bearish  → REDUCE          0.0%              │
            │        < 20  + bearish  → SELL            0.0%              │
            │        < 0   + bearish  → STRONG_SELL     0.0%              │
            │                                                             │
            │    + Sizing: Confidence × Strength × Volatility × Orders   │
            └────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                     RISK MANAGER                            │
            │                                                             │
            │   1. Loss Limits  → Daily (-5%) / Weekly (-12%) / DD (25%) │
            │   2. Stop Loss    → ATR-based (×2.0) / Fixed (5%) / Hard    │
            │   3. Take Profit  → Risk/Reward (≥1.5) + Trailing + Partial│
            │   4. Kelly Sizing → Win-rate (55%) × Fraction (25%)         │
            │   5. Exposure     → Per position (25%) / Sector (40%)       │
            │   6. Circuit Brkr → 1m/5m/1h drawdown / Vol spike          │
            └────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                PORTFOLIO MANAGER                            │
            │                                                             │
            │   Strategy   │ Target │ Current │ PnL(d) │ Sharpe         │
            │   ───────────┼────────┼─────────┼────────┼───────          │
            │   Trend Foll.│  30%   │  28.5%  │ +1.2%  │  1.45           │
            │   Momentum   │  25%   │  26.1%  │ +2.1%  │  1.62           │
            │   Mean Rev.  │  20%   │  19.3%  │ -0.3%  │  0.88           │
            │   Swing Tr.  │  25%   │  26.0%  │ +1.8%  │  1.35           │
            │                                                             │
            │   → Auto-rebalance si drift > 5% · Cash reserve: 15-20%   │
            └────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
            ┌─────────────────────────────────────────────────────────────┐
            │                  EXECUTION ENGINE                            │
            │                                                             │
            │    ┌──────────────────────┐  ┌──────────────────────┐       │
            │    │   PaperExchange      │  │   CCXT Connectors    │       │
            │    │   (Simulation)       │  │   (Live Trading)     │       │
            │    │                      │  │                      │       │
            │    │  • Slippage sim.     │  │  • Binance           │       │
            │    │  • Fees 0.1%         │  │  • Bybit             │       │
            │    │  • Partial fills     │  │  • OKX               │       │
            │    │  • Delay sim.        │  │  • Kraken            │       │
            │    │  • Paper PnL         │  │  • Coinbase          │       │
            │    └──────────────────────┘  └──────────────────────┘       │
            │                                                             │
            │   + ExecutionManager: Retry (×3) · Backoff · Rate Limit    │
            │   + Order Types: Market / Limit / Stop / TWAP / VWAP       │
            └─────────────────────────────────────────────────────────────┘
```

---

## 3. Module Deep-Dive

### 3.1 Configuration Layer (`src/config.py`)

**Responsabilités :**
- Point d'accès centralisé et typé à toute la configuration du système
- Chargement hiérarchique : defaults → YAML (`configs/default.yaml`) → `.env` → CLI overrides
- Validation stricte via Pydantic V2 avec `field_validator`

**Classes clés :**

| Classe | Rôle | Champs critiques |
|--------|------|-----------------|
| `CryptoAIConfig` | Configuration racine (singleton global) | `mode`, `watchlist`, `timeframes` |
| `RiskConfig` | Paramètres de risque | `max_position_size_pct`, `max_daily_loss_pct` |
| `ExecutionConfig` | Paramètres d'exécution | `order_type`, `retry_attempts`, `slippage_tolerance` |
| `AIConfig` | Paramètres IA | `fusion_method`, `weights`, `min_confidence_to_trade` |
| `StrategyConfig` | Config par stratégie | `enabled`, `weight`, `params` |
| `StopLossConfig` | Stop Loss intelligent | `default_pct`, `atr_multiplier` |
| `TakeProfitConfig` | Take Profit | `risk_reward_ratio`, `partial_take_profits` |
| `CircuitBreakerConfig` | Protection anti-crash | `max_drawdown_5m`, `cooldown_minutes` |

**Dépendances :** Tous les modules (lecture seule)

**Gestion d'erreurs :** Validation au chargement — mode invalide, clés manquantes, valeurs hors limites levées immédiatement.

---

### 3.2 Market Data Layer (`src/data/`)

**Responsabilités :**
- Acquisition unifiée des données de marché (REST + WebSocket)
- Normalisation des données au format interne (Pydantic V2)
- Cache temps réel (Redis) et historique (TimescaleDB)

**Classes clés :**

| Classe | Rôle |
|--------|------|
| `BaseProvider` (ABC) | Interface abstraite pour tous les providers de données |
| `CCXTProvider` | Implémentation CCXT (REST) pour Binance, Bybit, OKX, etc. |
| `WebSocketManager` | Gestionnaire de connexions WebSocket en temps réel |
| `DatabaseManager` | Point d'accès unifié PostgreSQL/TimescaleDB + Redis |

**Modèles de données (Pydantic V2, `src/data/market/schema.py`) :**

| Modèle | Description | Propriétés calculées |
|--------|-------------|---------------------|
| `OHLCV` | Bougie (Open/High/Low/Close/Volume) | `spread`, `body` |
| `Ticker` | Données temps réel | `spread_pct` |
| `Trade` | Transaction exécutée | — |
| `OrderBookLevel` | Niveau du carnet d'ordres | `value_usd` |
| `OrderBook` | Snapshot L2 complet | `spread`, `mid_price`, `imbalance`, `total_bid_volume`, `total_ask_volume` |

**Gestion d'erreurs :**
- `ProviderError` pour les échecs de collecte
- `RateLimitError` avec `retry_after` pour le rate limiting
- `WebSocketError` pour les pertes de connexion (reconnect automatique configurable)

---

### 3.3 Analysis Engines (`src/analysis/`)

Quatre moteurs d'analyse indépendants qui produisent des signaux standardisés.

#### 3.3.1 Technical Analysis (`src/analysis/technical/`)

**Responsabilités :**
- Calcul vectorisé de 30+ indicateurs techniques via Pandas
- Agrégation multi-timeframe (poids croissant avec la durée)
- Détection de patterns (Supertrend, Donchian, Pivot Points)

**Indicateurs calculés :**

| Catégorie | Indicateurs |
|-----------|-------------|
| Trend | EMA (9/21/50/200), SMA (20/50), MACD, Ichimoku, ADX, Supertrend, Donchian |
| Momentum | RSI (14), Stochastic RSI, ROC, Williams %R, MFI |
| Volatility | Bollinger Bands, ATR (14), Keltner Channels, BB Width |
| Volume | OBV, VWAP, Volume Profile, MFI, Volume Ratio |

**Agrégateur multi-timeframe :** Timeframes courts (1m = 5%) vs longs (1d = 25%) — les timeframes longs ont plus de poids.

**Gestion d'erreurs :** `InsufficientDataError` si moins de barres que la période de calcul requise.

#### 3.3.2 Order Book Analysis (`src/analysis/orderbook/`)

**Responsabilités :**
- Analyse en temps réel du carnet d'ordres L2
- Calcul du déséquilibre bid/ask (pression acheteuse vs vendeuse)
- Estimation du slippage pour différentes tailles d'ordre
- Détection de manipulation (spoofing, layering)

**Gestion d'erreurs :** Données insuffisantes si le carnet a moins que le nombre de niveaux configuré.

#### 3.3.3 On-Chain Analysis (`src/analysis/onchain/`)

**Responsabilités :**
- Suivi des transactions de whales (> $500k)
- Analyse des flux entre exchanges (netflow)
- Scoring on-chain (activité réseau, holders, TVL)

**Gestion d'erreurs :** Fallback gracieux si les APIs on-chain sont indisponibles.

#### 3.3.4 Sentiment Analysis (`src/analysis/news/`)

**Responsabilités :**
- Agrégation multi-source (news, Twitter, Reddit, Telegram)
- Scoring de sentiment (positif/négatif/neutre) par source
- Détection de tendances émergentes

**Gestion d'erreurs :** Source indisponible = ignorée, les autres sources compensent.

---

### 3.4 AI Core (`src/core/`)

#### 3.4.1 Feature Fusion Engine (`src/core/ai_agent.py`)

**Responsabilités :**
- Fusion pondérée des signaux des 4 sources d'analyse
- Détection de divergence entre sources
- Calcul du niveau de consensus (low / moderate / strong / unanimous)

**Poids par défaut des sources :**

| Source | Poids |
|--------|-------|
| Technical | 35% |
| On-Chain | 20% |
| Order Book | 15% |
| Sentiment (News) | 15% |
| Sentiment (Social) | 15% |

**Fonctionnement :**
1. Normaliser les poids aux seules sources disponibles
2. Calculer le score pondéré : `Σ(score_source × poids_normalisé)`
3. Déterminer la direction : bullish (> 60), bearish (< 40), neutral (entre)
4. Calculer la force : `|score - 50| / 50`
5. Détecter la divergence : directions opposées parmi les sources
6. Calculer le consensus : proportion de sources alignées

#### 3.4.2 Confidence Scorer (`src/core/ai_agent.py`)

**Responsabilités :**
- Score de confiance 0-100 basé sur :
  - Consensus : unanimous (+20), strong (+10), moderate (0), low (-10)
  - Force du signal : ×15
  - Confiance moyenne des sources : ×15
  - Pénalité divergence : -15
  - Pénalité risques : -5 par risque
  - Cap direction neutre : max 30

#### 3.4.3 Decision Matrix (`src/core/decision_engine.py`)

**Responsabilités :**
- Mapping score/direction/confiance → action de trading
- Calcul de la taille de position (Kelly adapté + limites)
- Génération des paramètres d'ordre

**Actions :**

| Action | Conditions | Allocation max |
|--------|-----------|----------------|
| `STRONG_BUY` | Score > 75, confiance > 60 | 20% du capital |
| `BUY` | Score > 60, confiance > 40 | 10% |
| `REINFORCE` | Score > 55, confiance > 30 | 5% |
| `HOLD` | Score neutre ou confiance < 20 | 0% |
| `REDUCE` | Score < 45, confiance > 30 | Réduire 50% |
| `SELL` | Score < 40, confiance > 40 | Vendre 50% |
| `STRONG_SELL` | Score < 25, confiance > 60 | Vendre tout |

#### 3.4.4 Explanation Engine (`src/core/ai_agent.py`)

Génère pour chaque décision une explication en langage naturel incluant :
- Décision et score global
- Analyse par source avec contribution
- Raisonnement et consensus
- Risques identifiés

---

### 3.5 Risk Manager (`src/risk/manager.py`)

**Responsabilités :**
- Validation pré-trade : chaque ordre passe par 7 vérifications
- Calcul dynamique du stop loss (ATR-based ou fixed %)
- Calcul du take profit (min risk/reward 1.5:1)
- Position sizing via Kelly Criterion adapté
- Limites de perte (daily / weekly / monthly / drawdown)
- Gestion de la corrélation et de l'exposition secteur

**Méthodes clés :**

| Méthode | Rôle |
|---------|------|
| `assess_trade()` | Évaluation complète des risques d'un trade |
| `_calculate_stop_loss()` | SL ATR × 2.0 ou fixed 5% (hard limit 10%) |
| `_calculate_take_profit()` | TP avec min RR 1.5:1 |
| `_calculate_kelly()` | Kelly fractionné (25%) avec win-rate 55% estimé |
| `_check_loss_limits()` | Vérifie que daily/weekly/drawdown limits OK |
| `record_trade_result()` | Met à jour le PnL et les statistiques journalières |

**Hiérarchie des vérifications :**
1. Limites de perte (arrêt immédiat si dépassées)
2. Stop loss optimal
3. Take profit optimal
4. Taille Kelly
5. Ajustement volatilité
6. Ajustement exposition secteur
7. Risk/Reward ≥ 1.0

---

### 3.6 Circuit Breaker (`src/risk/circuit_breaker.py`)

**Responsabilités :**
- Arrêt automatique du trading en conditions dangereuses
- 3 niveaux de protection : par actif, par volatilité, systémique

**Niveaux de déclenchement :**

| Niveau | Fenêtre | Seuil | Action |
|--------|---------|-------|--------|
| N1 - Drawdown 1m | 1 minute | -3% | Blacklist actif (60 min) |
| N2 - Drawdown 5m | 5 minutes | -5% | Blacklist actif + alerte |
| N3 - Drawdown 1h | 1 heure | -8% | Arrêt trading + alerte critique |
| Vol spike | ATR | ×5 normale | Blacklist + alerte |
| Systémique | Global | 3 triggers actif | Arrêt total système |

**États :** `CLOSED` (normal) → déclenchement → `OPEN` (arrêté) → cooldown → `HALF_OPEN` (test) → `CLOSED`

---

### 3.7 Portfolio Manager (`src/portfolio/manager.py`)

**Responsabilités :**
- Allocation de capital entre les 4 stratégies
- Rebalancing automatique (threshold ≥ 5% drift + min 24h interval)
- Suivi des performances par stratégie
- Gestion des expositions (sectorielle, top 3 positions)
- Cash reserve management (min 15%, target 20%)

**Limites d'allocation :**

| Limite | Valeur |
|--------|--------|
| Max single position | 25% du portefeuille |
| Max top 3 positions | 50% |
| Max secteur | 40% |
| Cash reserve min | 15% |
| Rebalance threshold | 5% drift |
| Rebalance min interval | 24h |
| Max drawdown | 25% depuis peak |

---

### 3.8 Execution Engine (`src/execution/`)

#### 3.8.1 Paper Exchange (`src/execution/paper.py`)

**Responsabilités :**
- Simulation réaliste d'un exchange crypto
- Slippage aléatoire paramétrable (conservative / moderate / aggressive)
- Frais configurables (0.1% par défaut)
- Exécution partielle et délai simulés
- Calcul complet PnL, Sharpe, Win Rate
- Capital initial par défaut : $100,000

#### 3.8.2 Execution Manager (`src/execution/manager.py`)

**Responsabilités :**
- Point d'entrée unique pour tous les ordres
- Retry avec exponential backoff (×3, ×1s → ×2s → ×4s)
- Rate limiting (5 req/s, 100 req/min)
- Protection slippage (max 0.5%)
- Vérification de remplissage avant confirmation
- Routing multi-exchange

**Types d'ordres supportés :** Market, Limit, Stop Loss, Stop Limit, Trailing Stop, TWAP, VWAP

---

### 3.9 Backtesting Engine (`src/backtesting/`)

#### 3.9.1 Backtest Engine (`src/backtesting/engine.py`)

**Responsabilités :**
- Simulation historique complète sur données OHLCV
- Utilise les vraies stratégies (même code qu'en production)
- Exécute via PaperExchange pour réalisme
- Calcule 30+ métriques de performance
- Supporte multi-timeframe et benchmark

**Configuration :**

| Paramètre | Default | Description |
|-----------|---------|-------------|
| `initial_capital` | $100,000 | Capital de départ |
| `fee_rate` | 0.1% | Frais de trading |
| `slippage_model` | conservative | Modèle de slippage |
| `warmup_bars` | 100 | Barres avant trading |
| `max_positions` | 5 | Positions simultanées max |
| `trading_days_per_year` | 365 | Jours annualisés |

#### 3.9.2 Performance Metrics (`src/backtesting/metrics.py`)

**Métriques disponibles (>30) :**

| Catégorie | Métriques |
|-----------|-----------|
| Rendement | Total Return (%), CAGR, Avg Daily Return |
| Risque | Sharpe Ratio, Sortino Ratio, Calmar Ratio |
| Drawdown | Max DD (%), Avg DD, DD Days, Ulcer Index |
| Trading | Win Rate, Profit Factor, Avg Win/Loss, Consecutive Wins |
| Value at Risk | VaR 95%, CVaR 95% |
| Robustesse | Recovery Factor, Risk of Ruin |
| Benchmark | Alpha, Beta, Information Ratio |

**Ratings qualitatifs :** Basés sur un score composite (8 facteurs) → POOR / ACCEPTABLE / GOOD / EXCELLENT

#### 3.9.3 Strategy Comparator (`src/backtesting/comparator.py`)

**Fonctionnalités :**
- Comparaison de multiples runs (mêmes données, stratégies différentes)
- Classement pondéré (Sharpe × Win Rate × Drawdown)
- Matrice de corrélation entre stratégies
- Walk-Forward Optimization (train/validation splits glissants)
- Rapport de comparaison formaté

#### 3.9.4 CLI (`src/backtesting/cli.py`)

**Modes :**
- `--strategy` : Backtest simple avec une stratégie
- `--compare` : Comparaison multiple stratégies
- `--walk-forward` : Walk-forward optimization
- `--crisis` : Simulation crise (slippage + volatilité accrus)

Génération de données OHLCV synthétiques par mouvement brownien géométrique.

---

### 3.10 Utils (`src/utils/`)

| Module | Responsabilités |
|--------|----------------|
| `database.py` | DatabaseManager : connexions PostgreSQL + Redis, pool management |
| `exceptions.py` | Hiérarchie d'exceptions : 15 classes de CryptoAIError à SecurityError |
| `logging.py` | Logger structuré JSON, support contexte, niveaux DEBUG → FATAL |
| `security/encryption.py` | Chiffrement AES-256-GCM pour clés API au repos |
| `security/rate_limiter.py` | Rate limiting par endpoint (sliding window) |
| `security/validator.py` | Validation d'input (sanitization, allow-lists) |

---

## 4. Data Flow

### 4.1 Cycle de Décision (1 seconde)

```
t=0s    Market Data Stream (WebSocket)
          ↓
t=0.1s  Data Ingestion → TimescaleDB + Redis
          ↓
t=0.2s  Technical Analysis (30s cache)
          ↓
t=0.3s  Order Book Analysis (5min cache)
          ↓
t=0.4s  On-Chain Analysis (15min cache)
          ↓
t=0.5s  Sentiment Analysis (10min cache)
          ↓
t=0.6s  Feature Fusion → FusedSignal
          ↓
t=0.7s  Confidence Scoring → Score 0-100
          ↓
t=0.8s  Decision Matrix → Action + Sizing
          ↓
t=0.9s  Risk Validation → RiskAssessment
          ↓
t=1.0s  Order Execution → PaperExchange / CCXT
```

### 4.2 Cycle de Rapports (quotidien)

```
t=00:00    → Portfolio snapshot
t=06:00    → Performance metrics update
t=12:00    → Strategy rebalance check
t=18:00    → Risk limits review
t=23:59    → Daily report generation (PnL, trades, metrics)
t=00:00+   → Reset daily limits
```

---

## 5. Risk Model

### 5.1 Couches de Protection

```
Layer 1 — Trade Level
├── Stop Loss (ATR × 2.0, min 5%)
├── Take Profit (RR ≥ 1.5)
├── Kelly Sizing (win-rate × fraction)
└── Risk/Reward ≥ 1.0

Layer 2 — Position Level
├── Max size: 25% of portfolio
├── Max leverage: 1.0 (paper) / 3.0 (max)
├── Max open positions: 10
└── Volatility scaling

Layer 3 — Portfolio Level
├── Sector exposure: max 40%
├── Correlation: max 70% between pairs
├── Cash reserve: min 15%
└── Top 3 positions: max 50%

Layer 4 — Catastrophe Level
├── Daily loss limit: 5%
├── Weekly loss limit: 12%
├── Monthly loss limit: 20%
├── Max drawdown: 25%
└── Circuit breaker (3 levels: asset, volatility, systemic)
```

---

## 6. Security Architecture

### 6.1 Chiffrement

| Donnée | Méthode | Standards |
|--------|---------|-----------|
| API Keys (stockage) | AES-256-GCM | `cryptography` library |
| Transport (API) | TLS 1.2+ | FastAPI + HTTPS |
| JWT Tokens | HS256 | `python-jose` |
| Passwords | bcrypt | `passlib` (cost ≥ 12) |

### 6.2 Authentification

- JWT Bearer dans header Authorization
- Token expiry : configurable (60 min par défaut)
- Refresh token : rotation automatique
- Rate limiting : 100 req/min par API key

### 6.3 Secrets Management

- Les clés API ne sont jamais dans le code source
- Pas de secrets dans les logs (filtrage automatique)
- Chiffrement AES-256-GCM au repos
- Rotation des clés recommandée tous les 30 jours

---

## 7. Scalability

### 7.1 Architecture Horizontale

```
                 ┌─────── LB ───────┐
                 │                  │
            ┌────┴────┐       ┌────┴────┐
            │  API     │  ···  │  API     │
            │  Worker  │       │  Worker  │
            └─────────┘       └─────────┘
                 │                  │
            ┌────┴──────────────────┴────┐
            │          Redis              │
            │   (Cache + Pub/Sub + Queue) │
            └─────────────────────────────┘
                 │                  │
            ┌────┴──────────────────┴────┐
            │     TimescaleDB (Write)     │
            │     TimescaleDB (Read)      │
            └─────────────────────────────┘
```

### 7.2 Stratégies de Scaling

| Composant | Stratégie | Notes |
|-----------|-----------|-------|
| API (FastAPI) | Horizontal (workers) | Uvicorn workers + Docker scale |
| Workers | Horizontal | `docker compose up --scale worker=N` |
| Redis | Cluster | Persistance AOF, LFU eviction |
| TimescaleDB | Read replicas | Écrire sur master, lire sur réplicas |
| WebSocket | Sticky sessions | Redis Pub/Sub pour broadcasting |

### 7.3 Caching Strategy

| Donnée | Cache | TTL | Stratégie |
|--------|-------|-----|-----------|
| OHLCV historique | TimescaleDB | — | Peristant |
| Ticker / Trade | Redis | 60s | Write-through |
| Order Book | Redis | 1s | Stream |
| Indicateurs tech. | Redis | 30s | Compute → Cache |
| Signaux AI | Memory | 1 cycle | Auto-expire |
| Positions | Memory | — | Journalisé DB |
