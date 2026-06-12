"""
Gestion centralisée de la configuration.

Charge la configuration depuis :
1. Fichier YAML (configs/default.yaml)
2. Variables d'environnement (.env)
3. Override CLI

Utilise Pydantic Settings pour la validation et le typage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyConfig(BaseSettings):
    """Configuration d'une stratégie de trading."""

    enabled: bool = True
    weight: float = 0.25
    params: dict[str, Any] = {}


class StopLossConfig(BaseSettings):
    """Configuration du stop loss intelligent."""

    default_pct: float = 5.0
    atr_multiplier: float = 2.0
    trailing_activation_pct: float = 10.0
    min_hodl_hours: int = 1


class TakeProfitConfig(BaseSettings):
    """Configuration du take profit intelligent."""

    risk_reward_ratio: float = 2.0
    partial_take_profits: list[dict[str, float]] = [
        {"at_pct": 25.0, "size_pct": 33.0},
        {"at_pct": 50.0, "size_pct": 33.0},
        {"at_pct": 100.0, "size_pct": 34.0},
    ]


class CircuitBreakerConfig(BaseSettings):
    """Configuration du système anti-catastrophe."""

    market_crash_pct: float = -8.0
    volatility_spike: float = 15.0
    cooldown_minutes: int = 60
    max_triggers_per_day: int = 2


class RiskConfig(BaseSettings):
    """Configuration de la gestion des risques."""

    max_position_size_pct: float = 25.0
    max_leverage: float = 1.0
    max_open_positions: int = 10
    max_exposure_per_asset_pct: float = 30.0
    max_exposure_sector_pct: float = 50.0
    max_daily_loss_pct: float = 5.0
    max_weekly_loss_pct: float = 15.0
    max_monthly_loss_pct: float = 30.0
    max_correlation: float = 0.7
    stop_loss: StopLossConfig = StopLossConfig()
    take_profit: TakeProfitConfig = TakeProfitConfig()
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    correlation_pairs: list[list[str]] = [["BTC", "ETH"], ["SOL", "AVAX"], ["ADA", "XRP"]]


class ExecutionConfig(BaseSettings):
    """Configuration du moteur d'exécution."""

    order_type: str = "limit"
    retry_attempts: int = 3
    retry_delay_seconds: int = 1
    order_timeout_seconds: int = 30
    min_order_size_usd: int = 10
    max_order_size_usd: int = 10000
    slippage_tolerance: float = 0.002


class AIConfig(BaseSettings):
    """Configuration de l'agent IA central."""

    fusion_method: str = "weighted"
    min_confidence_to_trade: int = 65
    max_signals_per_decision: int = 10
    explanation_detail: str = "full"
    weights: dict[str, float] = {
        "technical": 0.35,
        "onchain": 0.20,
        "sentiment": 0.15,
        "orderbook": 0.15,
        "risk": 0.15,
    }


class CryptoAIConfig(BaseSettings):
    """
    Configuration centrale du système CryptoAI.

    Charge depuis YAML + variables d'environnement.
    Validation et typage automatiques via Pydantic.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── Mode système ─────────────────────────────────
    mode: str = Field(default="paper", description="paper | live | backtest")
    log_level: str = Field(default="INFO", description="DEBUG | INFO | WARN | ERROR")
    log_format: str = Field(default="json", description="json | text")

    # ─── Base de données ──────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://cryptoai:changeme@localhost:5432/cryptoai",
        description="URL de connexion PostgreSQL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="URL de connexion Redis",
    )

    # ─── Exchanges ───────────────────────────────────
    binance_api_key: str = Field(default="", description="Binance API Key")
    binance_api_secret: str = Field(default="", description="Binance API Secret")
    bybit_api_key: str = Field(default="", description="Bybit API Key")
    bybit_api_secret: str = Field(default="", description="Bybit API Secret")

    # ─── Watchlist ───────────────────────────────────
    watchlist: list[str] = Field(
        default=[
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
            "XRP/USDT", "ADA/USDT", "DOGE/USDT", "LINK/USDT",
            "AVAX/USDT", "SUI/USDT", "APT/USDT", "TON/USDT",
        ]
    )
    timeframes: list[str] = Field(
        default=["1m", "5m", "15m", "1h", "4h", "1d", "1w"]
    )

    # ─── Sous-configs ────────────────────────────────
    risk: RiskConfig = RiskConfig()
    execution: ExecutionConfig = ExecutionConfig()
    ai: AIConfig = AIConfig()
    strategies: dict[str, StrategyConfig] = {
        "trend_following": StrategyConfig(weight=0.30),
        "momentum": StrategyConfig(weight=0.25),
        "mean_reversion": StrategyConfig(weight=0.20),
        "swing_trading": StrategyConfig(weight=0.25),
    }

    # ─── JWT & Security ──────────────────────────────
    jwt_secret: str = Field(default="changeme_in_prod", min_length=16)
    encryption_key: str = Field(default="")
    api_rate_limit: int = Field(default=100, ge=1, le=10000)
    api_rate_window: int = Field(default=60, ge=1)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("paper", "live", "backtest"):
            raise ValueError(f"Mode invalide: {v}. Choisir: paper, live, backtest")
        return v

    @classmethod
    def from_yaml(cls, yaml_path: str = "configs/default.yaml") -> CryptoAIConfig:
        """Charge la config depuis un fichier YAML puis applique les overrides ENV."""
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f)

        # Aplatir la structure YAML en flat dict pour Pydantic
        flat: dict[str, Any] = {}

        # Mapping YAML → champ config
        mappings = {
            "system.mode": "mode",
            "system.log_level": "log_level",
            "system.log_format": "log_format",
            "market.watchlist": "watchlist",
            "market.timeframes": "timeframes",
        }

        for yaml_key, config_field in mappings.items():
            parts = yaml_key.split(".")
            val = raw
            for part in parts:
                val = val.get(part, {}) if isinstance(val, dict) else {}
            if isinstance(val, (list, str, int, float, bool)):
                flat[config_field] = val

        return cls(**flat)


# Singleton global
config: CryptoAIConfig = CryptoAIConfig()


def reload_config(yaml_path: str = "configs/default.yaml") -> CryptoAIConfig:
    """Recharge la configuration (utile pour hot-reload)."""
    global config
    config = CryptoAIConfig.from_yaml(yaml_path)
    return config
