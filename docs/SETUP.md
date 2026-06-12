# Setup Guide — CryptoAI

> **Plateforme de trading crypto autonome pilotee par IA**
> Guide d'installation et de configuration complet.

---

## Table des matieres

1. [Prerequisites](#1-prerequisites)
2. [Installation Rapide](#2-installation-rapide)
3. [Configuration Detaillee](#3-configuration-detaillee)
4. [Infrastructure Docker](#4-infrastructure-docker)
5. [Base de Donnees](#5-base-de-donnees)
6. [Modes d'Execution](#6-modes-dexecution)
7. [Frontend Dashboard](#7-frontend-dashboard)
8. [Configuration Avancee](#8-configuration-avancee)
9. [Depannage](#9-depannage)
10. [Securite](#10-securite)

---

## 1. Prerequisites

### System Requirements

| Component | Minimum | Recommande |
|-----------|---------|------------|
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 8 GB | 16+ GB |
| **Disk** | 20 GB SSD | 50+ GB NVMe |
| **OS** | Linux (Ubuntu 22.04+) | Linux (Ubuntu 24.04+) |
| **Network** | 50 Mbps | 100+ Mbps |

### Software Dependencies

| Software | Version | Verification |
|----------|---------|--------------|
| **Python** | 3.12+ | `python3 --version` |
| **Docker** | 24+ | `docker --version` |
| **Docker Compose** | 2.24+ | `docker compose version` |
| **Node.js** | 20+ (LTS) | `node --version` |
| **npm** | 10+ | `npm --version` |
| **Git** | 2.40+ | `git --version` |
| **Make** | 4.3+ | `make --version` |

### Installation des Prerequisites

**Ubuntu / Debian :**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
    docker.io docker-compose-v2 nodejs npm git make curl

# Verifier les versions
python3 --version   # >= 3.12
docker --version    # >= 24
docker compose version  # >= 2.24
node --version      # >= 20
npm --version       # >= 10
```

**macOS :**
```bash
# Homebrew
brew install python@3.12 docker docker-compose node@20 git make

# Docker Desktop (alternative)
# https://www.docker.com/products/docker-desktop/
```

**Windows (WSL2) :**
```powershell
# Installer WSL2 + Ubuntu 24.04
wsl --install -d Ubuntu-24.04

# Dans WSL, suivre les instructions Ubuntu ci-dessus
# Installer Docker Desktop avec integration WSL2 activee
```

---

## 2. Installation Rapide

```bash
# Étape 1 : Cloner le depot
git clone https://github.com/your-org/cryptoai.git
cd cryptoai

# Étape 2 : Setup complet (venv + dependances + hooks)
make setup

# Étape 3 : Configurer l'environnement
cp .env.example .env
# Editer .env avec vos cles API (optionnel pour paper trading)

# Étape 4 : Demarrer l'infrastructure (TimescaleDB + Redis + monitoring)
docker compose up -d

# Étape 5 : Initialiser la base de donnees
make db-upgrade

# Étape 6 : Lancer le paper trading
make run-paper

# Étape 7 : Ouvrir le dashboard (dans un autre terminal)
cd frontend && npm install && npm run dev
# -> http://localhost:3000
```

---

## 3. Configuration Detaillee

### 3.1 Environnement Virtuel Python

```bash
# Creer l'environnement virtuel
python3 -m venv .venv

# Activer
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Installer les dependances de production
pip install -e .

# Installer les dependances de developpement (tests, linting, pre-commit)
pip install -e ".[dev]"

# Verifier l'installation
python -c "import cryptoai; print('OK')"
```

### 3.2 Variables d'Environnement

Copier et editer le fichier `.env` :

```bash
cp .env.example .env
```

**Variables obligatoires (minimal pour paper trading) :**

```ini
# Mode d'execution (paper | live | backtest | worker)
MODE=paper

# Base de donnees (les valeurs ci-dessous sont les defauts Docker)
DATABASE_URL=postgresql+asyncpg://cryptoai:cryptoai_secret@localhost:5432/cryptoai
REDIS_URL=redis://localhost:6379/0

# JWT Secret (changer impérativement en production !)
JWT_SECRET=votre_secret_tres_long_et_aleatoire_32_caracteres_min

# Chiffrement (generer avec: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=votre_cle_fernet_32_bytes_base64
```

**Variables optionnelles (exchanges - requis pour live trading) :**

```ini
# Binance
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# Bybit
BYBIT_API_KEY=your_api_key
BYBIT_API_SECRET=your_api_secret

# OKX
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret

# Kraken
KRAKEN_API_KEY=your_api_key
KRAKEN_API_SECRET=your_api_secret

# Coinbase
COINBASE_API_KEY=your_api_key
COINBASE_API_SECRET=your_api_secret
```

**Variables optionnelles (notifications) :**

```ini
# Telegram Alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

**Variables optionnelles (paper trading defaults) :**

```ini
PAPER_INITIAL_CAPITAL=100000
PAPER_MAX_POSITION_PCT=0.25
PAPER_DAILY_LOSS_LIMIT_PCT=0.05
```

**Variables optionnelles (monitoring) :**

```ini
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
```

### 3.3 Configuration YAML

Le fichier `configs/default.yaml` contient la configuration centralisee du systeme. Il est charge automatiquement au demarrage et peut etre surcharge par des fichiers additionnels ou des variables d'environnement.

**Structure principale :**

```yaml
system:
  name: "CryptoAI"
  version: "1.0.0"
  mode: "${MODE}"  # Herite de .env

market:
  watchlist: ["BTC/USDT", "ETH/USDT", "SOL/USDT", ...]
  timeframes: ["1m", "5m", "15m", "1h", "4h", "1d"]
  exchanges: ["binance", "bybit", "okx"]

analysis:
  technical:
    enabled: true
    indicators: ["ema_9", "ema_21", "rsi_14", "macd", "adx", "bbands", ...]
  orderbook:
    enabled: true
    depth_levels: 10
  onchain:
    enabled: true
  news:
    enabled: true

ai_agent:
  fusion_method: "weighted"
  weights:
    technical: 0.35
    onchain: 0.20
    sentiment: 0.15
    orderbook: 0.15
    risk: 0.15

risk:
  max_daily_loss_pct: 5.0
  max_weekly_loss_pct: 12.0
  max_monthly_loss_pct: 20.0
  max_drawdown_pct: 25.0
  stop_loss_atr_multiplier: 2.0
  min_risk_reward_ratio: 1.5
  kelly_fraction: 0.25

portfolio:
  max_position_pct: 25.0
  max_sector_pct: 40.0
  min_cash_reserve_pct: 15.0
  rebalance_threshold_pct: 5.0
  strategies:
    trend_following: { weight: 0.30 }
    momentum: { weight: 0.25 }
    mean_reversion: { weight: 0.20 }
    swing_trading: { weight: 0.25 }

execution:
  paper_initial_capital: 100000
  slippage_model: "conservative"
  max_retries: 3
  rate_limit_per_second: 5
  rate_limit_per_minute: 100

backtesting:
  default_initial_capital: 100000
  default_slippage_bps: 10
  crisis_slippage_bps: 30
```

---

## 4. Infrastructure Docker

### 4.1 Services

Le `docker-compose.yml` definit 7 services :

| Service | Image | Role | Port(s) |
|---------|-------|------|---------|
| **postgres** | timescale/timescaledb:2.17-pg16 | Base de donnees time-series | 5432 |
| **redis** | redis:7.4-alpine | Cache temps reel | 6379 |
| **api** | cryptoai-api (build local) | API REST FastAPI | 8000 |
| **worker** | cryptoai-worker (build local) | Collecte + analyse background | - |
| **frontend** | node:20-alpine | Dashboard Next.js | 3000 |
| **prometheus** | prom/prometheus:v2.55.0 | Metriques | 9090 |
| **grafana** | grafana/grafana:v11.3.0 | Visualisation | 3001 |

### 4.2 Demarrage et Arret

```bash
# Demarrer tous les services
docker compose up -d

# Demarrer la base de donnees uniquement (dev)
docker compose up -d postgres redis

# Demarrer avec rebuild des images
docker compose up -d --build

# Voir les logs
docker compose logs -f           # Tous les services
docker compose logs -f api       # Service specifique
docker compose logs -f postgres  # Logs base de donnees

# Arreter
docker compose down

# Arreter et supprimer les volumes (perte des donnees !)
docker compose down -v

# Reconstruire les images
docker compose build

# Verifier l'etat
docker compose ps
```

### 4.3 Persistance des Donnees

Les volumes suivants sont montes pour la persistence :

```yaml
volumes:
  postgres_data:    # Donnees TimescaleDB (historique de prix, trades)
  redis_data:       # Cache Redis (ordre book, transactions en cours)
  prometheus_data:  # Metriques de monitoring
  grafana_data:     # Configuration et dashboards Grafana
```

Pour sauvegarder les donnees :

```bash
# Backup TimescaleDB
docker exec cryptoai-postgres-1 pg_dump -U cryptoai cryptoai > backup_$(date +%Y%m%d).sql

# Restore TimescaleDB
cat backup.sql | docker exec -i cryptoai-postgres-1 psql -U cryptoai cryptoai
```

---

## 5. Base de Donnees

### 5.1 TimescaleDB

La base de donnees utilise **TimescaleDB 2.17** (extension PostgreSQL 16) pour le stockage des donnees time-series.

**Tables principales :**

| Table | Description |
|-------|-------------|
| `ohlcv` | Bougies OHLCV (hypertable, partitionnee par timestamp et symbol) |
| `trades` | Transactions executees |
| `orders` | Ordres soumis |
| `signals` | Signaux generes par les strategies |
| `decisions` | Decisions de l'IA |
| `metrics` | Metriques de performance |
| `portfolio_snapshots` | Etat du portefeuille dans le temps |

### 5.2 Migrations

```bash
# Appliquer les migrations
make db-upgrade

# Creer une nouvelle migration (apres modification du schema)
make db-migrate msg="add_user_preferences_table"

# Revenir en arriere (derniere migration)
make db-rollback

# Reinitialiser la base (dev uniquement)
# ATTENTION : detruit toutes les donnees
docker compose down -v
docker compose up -d postgres
make db-upgrade
```

### 5.3 Connexion Directe

```bash
# Via psql dans le conteneur
docker exec -it cryptoai-postgres-1 psql -U cryptoai -d cryptoai

# Via votre client local (si le port 5432 est expose)
psql -h localhost -U cryptoai -d cryptoai
# Mot de passe : cryptoai_secret

# Exemple de requete
SELECT time_bucket('1 hour', timestamp) AS hour,
       symbol,
       FIRST(close, timestamp) AS open,
       MAX(high) AS high,
       MIN(low) AS low,
       LAST(close, timestamp) AS close,
       SUM(volume) AS volume
FROM ohlcv
WHERE timestamp >= NOW() - INTERVAL '7 days'
  AND symbol = 'BTC/USDT'
GROUP BY hour, symbol
ORDER BY hour DESC;
```

---

## 6. Modes d'Execution

### 6.1 Paper Trading (Recommandee pour demarrer)

Simule le trading avec capital fictif. Aucun fonds reel n'est engage.

```bash
# Lancer le systeme complet en mode paper
make run-paper
# Equivalent : python -m src.main --mode paper

# Lancer l'API uniquement
make run
# Equivalent : uvicorn src.api.app:app --reload --port 8000

# Lancer le worker de collecte (dans un autre terminal)
make run-worker
```

**Ce qui se passe :**
1. Le systeme initialise les connecteurs (PaperExchange avec $100k fictif)
2. Les collecteurs de donnees simulent les flux de marche
3. Les 4 moteurs d'analyse tournent sur les donnees simulees
4. L'IA Core genere des decisions
5. Les ordres sont executes via PaperExchange
6. Les metriques de performance sont calculees en continu

### 6.2 Live Trading (Production)

Engage des fonds reels. Necessite des cles API d'exchange configurees.

```bash
# 1. Verifier la configuration
python -m src.main --mode check

# 2. Lancer en mode live (apres verification approfondie en paper)
make run-live
# Equivalent : python -m src.main --mode live
```

**AVERTISSEMENT :** Testez extensivement en mode `paper` avant de passer en `live`. Commencez avec des montants faibles.

### 6.3 Backtesting

Analyse historique sur des donnees passees.

```bash
# Backtest simple
make backtest -- --strategy trend_following --symbol BTC/USDT --timeframe 1h
# Equivalent : python -m src.backtesting.cli --strategy trend_following --symbol BTC/USDT

# Comparaison de strategies
make backtest -- --compare --strategies trend_following,momentum --symbol BTC/USDT

# Walk-forward optimization
make backtest -- --walk-forward --strategy trend_following --symbol BTC/USDT --splits 3

# Mode crise (slippage et volatilite eleves)
make backtest -- --crisis --strategy momentum --symbol BTC/USDT

# Export des resultats
make backtest -- --strategy trend_following --output results.json
```

**Options disponibles :**

| Option | Valeurs | Defaut | Description |
|--------|---------|--------|-------------|
| `--strategy` | `trend_following`, `momentum`, `mean_reversion`, `swing_trading` | `trend_following` | Strategie a tester |
| `--strategies` | Liste separee par des virgules | - | Mode comparaison |
| `--symbol` | `BTC/USDT`, `ETH/USDT`, ... | `BTC/USDT` | Paire de trading |
| `--timeframe` | `1m`, `5m`, `1h`, `4h`, `1d` | `1h` | Timeframe |
| `--start` | `YYYY-MM-DD` | -6 mois | Date de debut |
| `--end` | `YYYY-MM-DD` | Aujourd'hui | Date de fin |
| `--initial-capital` | Nombre | 100000 | Capital initial |
| `--compare` | Flag | false | Mode comparaison |
| `--walk-forward` | Flag | false | Walk-forward |
| `--splits` | Nombre | 3 | Splits walk-forward |
| `--crisis` | Flag | false | Mode crise |
| `--output` | Fichier | - | Export (JSON/CSV) |

### 6.4 Mode Developpement

```bash
# Demarrer l'infrastructure (DB)
docker compose up -d postgres redis

# Lancer l'API avec hot-reload
make dev
# Equivalent : uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

# Dans un autre terminal, lancer un worker de collecte
python -m src.main --mode worker

# Tests
make test        # Tous les tests
make test-unit   # Tests unitaires
make test-cov    # Tests avec couverture
```

---

## 7. Frontend Dashboard

### 7.1 Demarrage

```bash
cd frontend

# Installer les dependances
npm install

# Lancer en developpement (hot-reload)
npm run dev
# -> http://localhost:3000

# Build production
npm run build
npm start
# -> http://localhost:3000
```

### 7.2 Pages du Dashboard

| URL | Description |
|-----|-------------|
| `/` | Vue d'ensemble du portefeuille |
| `/dashboard` | Dashboard principal avec graphiques |
| `/strategies` | Performance des strategies |
| `/trades` | Historique des transactions |
| `/risk` | Metriques de risque |
| `/backtesting` | Interface de backtesting |
| `/settings` | Configuration utilisateur |

### 7.3 Configuration Frontend

Les variables d'environnement pour le frontend sont definies dans `frontend/.env.local` :

```env
NEXT_PUBLIC_API_URL=http://localhost:8000  # URL de l'API backend
NEXT_PUBLIC_WS_URL=ws://localhost:8000     # WebSocket (si implemente)
```

---

## 8. Configuration Avancee

### 8.1 Personnalisation des Strategies

Editer `configs/default.yaml` pour ajuster les parametres des strategies :

```yaml
portfolio:
  strategies:
    trend_following:
      weight: 0.30           # Poids dans l'allocation (total = 1.0)
      params:
        ema_fast: 9           # EMA rapide
        ema_slow: 21          # EMA lente
        ema_trend: 200        # EMA de tendance long terme
        adx_threshold: 25     # Seuil ADX pour tendance
    momentum:
      weight: 0.25
      params:
        rsi_period: 14        # Periode RSI
        rsi_overbought: 70    # Seuil surachat
        rsi_oversold: 30      # Seuil survente
        volume_ma_period: 20  # Periode MA volume
    mean_reversion:
      weight: 0.20
      params:
        bb_period: 20         # Periode Bollinger
        bb_std: 2.0           # Ecarts-types Bollinger
        rsi_period: 14
        rsi_extreme: 30       # Seuil extreme RSI
    swing_trading:
      weight: 0.25
      params:
        fast_tf: "1h"         # Timeframe rapide
        slow_tf: "4h"         # Timeframe lente
        confluence_min: 2     # Minimum de confirmations requises
```

### 8.2 Ajustement du Risk Management

```yaml
risk:
  # Limites de pertes
  max_daily_loss_pct: 5.0        # Perte max journaliere (5% du capital)
  max_weekly_loss_pct: 12.0      # Perte max hebdomadaire
  max_monthly_loss_pct: 20.0     # Perte max mensuelle
  max_drawdown_pct: 25.0         # Drawdown max absolu

  # Stop Loss
  stop_loss_atr_multiplier: 2.0  # Multiplicateur ATR (2x = dynamique)
  stop_loss_fixed_pct: 5.0       # Stop loss fixe (5%)
  hard_stop_loss_pct: 10.0       # Stop loss dur (10%, jamais depasse)

  # Take Profit
  min_risk_reward_ratio: 1.5     # Ratio R/R minimum (1.5:1)

  # Position Sizing (Kelly Criterion)
  kelly_fraction: 0.25           # Fraction du Kelly (25% = conservateur)
  estimated_win_rate: 0.55       # Win rate estime (55%)

  # Circuit Breaker
  circuit_breaker:
    level1_drawdown_pct: -3.0    # -3% en 1 minute
    level2_drawdown_pct: -5.0    # -5% en 5 minutes
    level3_drawdown_pct: -8.0    # -8% en 1 heure
    volatility_multiplier: 5.0   # x5 ATR = volatilite extreme
    cooldown_minutes: 30         # Cooldown apres declenchement
```

### 8.3 Configuration des Analyses

```yaml
analysis:
  technical:
    enabled: true
    indicators:
      trend: ["ema_9", "ema_21", "ema_50", "ema_200", "adx", "ichimoku", "supertrend"]
      momentum: ["rsi_14", "macd", "stoch_rsi", "williams_r", "roc"]
      volatility: ["bbands", "atr_14", "donchian_20", "keltner"]
      volume: ["obv", "volume_sma", "mfi", "vwap"]

  orderbook:
    enabled: true
    depth_levels: 10           # Niveaux de profondeur
    min_spread_pct: 0.01       # Spread minimum
    imbalance_threshold: 0.3   # Seuil de desequilibre

  onchain:
    enabled: true
    whale_threshold_usd: 100000  # Transactions > $100k
    exchange_flow_tracking: true

  news:
    enabled: true
    sources: ["twitter", "reddit", "telegram", "news_api"]
    sentiment_threshold: 0.2   # Seuil de sentiment
```

### 8.4 Multi-Exchange

Le systeme supporte 5 exchanges simultanement :

```yaml
market:
  exchanges:
    - name: binance
      weight: 0.30        # Poids dans l'agregation des prix
      rate_limit: 1200     # Requetes par minute
    - name: bybit
      weight: 0.25
      rate_limit: 600
    - name: okx
      weight: 0.20
      rate_limit: 600
    - name: kraken
      weight: 0.15
      rate_limit: 300
    - name: coinbase
      weight: 0.10
      rate_limit: 300
```

### 8.5 Monitoring (Prometheus + Grafana)

**Acces aux interfaces :**

| Service | URL | Credentials (default) |
|---------|-----|----------------------|
| Prometheus | `http://localhost:9090` | - |
| Grafana | `http://localhost:3001` | `admin` / `admin` |

**Dashboards Grafana pre-configures :**

- **Overview** : Vue d'ensemble du systeme
- **Trading Performance** : PnL, Sharpe, Drawdown
- **Risk Metrics** : VaR, exposition, limites
- **Market Data** : Flux de donnees, latence
- **System Health** : CPU, RAM, connexions DB

---

## 9. Depannage

### 9.1 Problemes Courants

#### Erreur : `ModuleNotFoundError: No module named 'src'`

```bash
# Verifier que vous etes a la racine du projet
pwd  # doit afficher .../cryptoai

# Activer l'environnement virtuel
source .venv/bin/activate

# Installer le package en mode editable
pip install -e .
```

#### Erreur : `Cannot connect to PostgreSQL`

```bash
# Verifier que le conteneur tourne
docker ps | grep postgres

# Verifier les logs
docker compose logs postgres

# Si pas de connexion, redemarrer
docker compose restart postgres

# Verifier les credentials dans .env
grep DATABASE_URL .env
```

#### Erreur : `docker compose` command not found

```bash
# Docker Compose V2 est integre a Docker
# Verifier la version de Docker
docker --version  # Doit etre >= 24

# Utiliser le plugin
docker compose up -d  # Note : pas de tiret entre docker et compose
```

#### Erreur : Port deja utilise

```bash
# Verifier quel service utilise le port
sudo lsof -i :5432     # PostgreSQL
sudo lsof -i :6379     # Redis
sudo lsof -i :8000     # API
sudo lsof -i :3000     # Frontend

# Changer le port dans docker-compose.yml ou .env
```

#### Erreur : `make: command not found`

```bash
# Installer make
sudo apt install -y make  # Ubuntu/Debian
brew install make         # macOS
```

#### Erreur : Permissions Docker

```bash
# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER
# Deconnexion/reconnexion requise, ou executer :
newgrp docker
```

#### Erreur : Memoire insuffisante pour Docker

```bash
# Limiter la memoire des conteneurs dans docker-compose.yml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 2G
```

### 9.2 Commandes de Diagnostic

```bash
# Verifier l'etat du systeme
curl http://localhost:8000/health
curl http://localhost:8000/health/ready

# Verifier la base de donnees
docker exec cryptoai-postgres-1 pg_isready -U cryptoai

# Verifier Redis
docker exec cryptoai-redis-1 redis-cli ping
# Devrait repondre : PONG

# Logs en temps reel
docker compose logs -f --tail=100

# Tester l'API
curl -s http://localhost:8000/api/v1/market/ticker/BTC/USDT | jq .
```

### 9.3 Clean Reset

```bash
# Arreter tout et nettoyer
make clean-all

# Reconstruire depuis zero
docker compose down -v           # Supprime les volumes
make clean                       # Nettoie les artefacts
make setup                       # Reinstalle
docker compose up -d             # Redemarre l'infra
make db-upgrade                  # Reinitialise les tables
make run-paper                   # Relance
```

---

## 10. Securite

### 10.1 Bonnes Pratiques

1. **Changez tous les mots de passe par defaut** dans `.env`
2. **Ne committez jamais** le fichier `.env` (il est dans `.gitignore`)
3. **Utilisez des cles API restreintes** pour les exchanges (sans withdraw)
4. **Activez 2FA** sur vos comptes exchanges
5. **Limitez les permissions** des cles API au minimum requis (lecture + trading, pas de retrait)
6. **Surveillez les logs** regulierement pour des activites suspectes
7. **Mettez a jour** regulierement les dependances (`pip install -e . --upgrade`)

### 10.2 Gestion des Secrets

Les cles API sont chiffrees au repos avec AES-256-GCM :

```bash
# Generer une cle de chiffrement
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Stocker la cle dans .env
ENCRYPTION_KEY=...cle_generee...
```

### 10.3 Checklist Pre-Production

Avant de passer en mode `live` :

- [ ] Backtesting approfondi sur au moins 6 mois de donnees
- [ ] Walk-forward optimization realisee
- [ ] Paper trading operationnel pendant au moins 2 semaines
- [ ] Limites de risque configurees et testees
- [ ] Circuit breaker verifie
- [ ] Monitoring en place (Prometheus + Grafana)
- [ ] Alertes configurees (Telegram)
- [ ] Contrats d'exchange verifies (fees, limites)
- [ ] Plan de rollback documente
- [ ] Capital risque limite (ne jamais engager plus que ce qu'on peut perdre)

---

<p align="center">
  <i>Configure avec rigueur, opere avec discipline</i>
</p>
