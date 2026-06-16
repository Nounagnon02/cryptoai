"""Endpoints pour les paramètres de l'application."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from src.utils.security.encryption import EncryptionEngine

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

SETTINGS_PATH = Path(os.getenv("CRYPTOAI_SETTINGS_PATH", "data/settings.json"))

# Récupération de la clé de chiffrement — jamais de valeur par défaut en dur
_ENCRYPTION_KEY = os.getenv("CRYPTOAI_ENCRYPTION_KEY", "")
_ENCRYPTION_ENGINE: EncryptionEngine | None = None


def _get_encryption_engine() -> EncryptionEngine:
    """Retourne le moteur de chiffrement AES-256-GCM."""
    global _ENCRYPTION_ENGINE
    if _ENCRYPTION_ENGINE is None:
        if not _ENCRYPTION_KEY:
            # Générer une clé aléatoire persistante pour le développement
            key_path = SETTINGS_PATH.parent / ".encryption_key"
            if key_path.exists():
                _ENCRYPTION_ENGINE = EncryptionEngine(master_key=key_path.read_text().strip())
            else:
                _ENCRYPTION_ENGINE = EncryptionEngine()
                _ENCRYPTION_ENGINE._master_key = _ENCRYPTION_ENGINE.generate_key()
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_text(_ENCRYPTION_ENGINE._master_key)
                logger.warning("Generated new encryption key at %s — back it up!", key_path)
        else:
            _ENCRYPTION_ENGINE = EncryptionEngine(master_key=_ENCRYPTION_KEY)
    return _ENCRYPTION_ENGINE


class StrategySetting(BaseModel):
    name: str
    label: str
    enabled: bool = True
    allocation: float = Field(..., ge=0, le=100)


class RiskSetting(BaseModel):
    max_drawdown_pct: float = Field(25.0, ge=5, le=50)
    max_position_size_pct: float = Field(10.0, ge=2, le=30)


class ApiKeySetting(BaseModel):
    exchange: str
    key_preview: str = ""
    has_key: bool = False


class SettingsResponse(BaseModel):
    strategies: list[StrategySetting]
    risk: RiskSetting
    api_keys: list[ApiKeySetting]
    trading_mode: str = "paper"  # paper | live


class SettingsUpdate(BaseModel):
    strategies: list[StrategySetting] | None = None
    risk: RiskSetting | None = None
    trading_mode: str | None = None  # paper | live


def _default_settings() -> dict:
    return {
        "strategies": [
            {"name": "trend_following", "label": "Trend Following",
             "enabled": True, "allocation": 30},
            {"name": "momentum", "label": "Momentum",
             "enabled": True, "allocation": 25},
            {"name": "mean_reversion", "label": "Mean Reversion",
             "enabled": False, "allocation": 20},
            {"name": "swing_trading", "label": "Swing Trading",
             "enabled": True, "allocation": 25},
        ],
        "risk": {
            "max_drawdown_pct": 25.0,
            "max_position_size_pct": 10.0,
        },
        "trading_mode": "paper",
        "api_keys": [],
    }


def _load_settings() -> dict:
    """Charge les paramètres depuis le fichier JSON."""
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH) as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load settings: %s", exc)
    return _default_settings()


def _save_settings(data: dict) -> None:
    """Sauvegarde les paramètres dans le fichier JSON."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Settings saved to %s", SETTINGS_PATH)
    except Exception as exc:
        logger.error("Failed to save settings: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to save settings",
        ) from exc


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Récupère les paramètres actuels."""
    from src.config import config as app_config

    data = _load_settings()
    strategies = [StrategySetting(**s) for s in data.get("strategies", [])]
    risk = RiskSetting(**data.get("risk", {}))
    api_keys = [
        ApiKeySetting(
            exchange=e["exchange"],
            key_preview=e["key"][:6] + "••••••••••" if e.get("key") else "",
            has_key=bool(e.get("key")),
        )
        for e in data.get("api_keys", [])
    ]
    # Use the actual running mode from config, not saved file (file may be stale)
    trading_mode = app_config.mode if app_config.mode in ("paper", "live") else "paper"
    return SettingsResponse(
        strategies=strategies, risk=risk, api_keys=api_keys, trading_mode=trading_mode
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdate):
    """Met à jour les paramètres."""
    data = _load_settings()
    if update.strategies is not None:
        data["strategies"] = [s.model_dump() for s in update.strategies]
    if update.risk is not None:
        data["risk"] = update.risk.model_dump()
    if update.trading_mode is not None:
        if update.trading_mode not in ("paper", "live"):
            raise HTTPException(status_code=422, detail="trading_mode must be 'paper' or 'live'")
        data["trading_mode"] = update.trading_mode
    _save_settings(data)
    return await get_settings()


# ─── API Key Management ──────────────────────────────────────────


class ApiKeyAddRequest(BaseModel):
    exchange: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field(..., min_length=1, max_length=512)
    api_secret: str = Field(..., min_length=1, max_length=512)


class ApiKeyTestRequest(BaseModel):
    exchange: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field(..., min_length=1, max_length=512)
    api_secret: str = Field(..., min_length=1, max_length=512)


class ApiKeyTestResponse(BaseModel):
    success: bool
    message: str
    exchange: str


@router.put("/keys", response_model=SettingsResponse)
async def add_api_key(req: ApiKeyAddRequest):
    """Ajoute ou met à jour une clé API pour un exchange (AES-256-GCM)."""
    data = _load_settings()
    api_keys_list: list[dict] = data.get("api_keys", [])

    engine = _get_encryption_engine()
    encrypted_key = engine.encrypt(req.api_key)
    encrypted_secret = engine.encrypt(req.api_secret)

    # Remplacer ou ajouter
    existing = next((k for k in api_keys_list if k["exchange"] == req.exchange), None)
    if existing:
        existing["key"] = encrypted_key
        existing["secret"] = encrypted_secret
    else:
        api_keys_list.append({
            "exchange": req.exchange,
            "key": encrypted_key,
            "secret": encrypted_secret,
        })

    data["api_keys"] = api_keys_list
    _save_settings(data)
    logger.info("API key saved for %s (AES-256-GCM encrypted)", req.exchange)
    return await get_settings()


@router.delete("/keys/{exchange}", response_model=SettingsResponse)
async def delete_api_key(exchange: str):
    """Supprime une clé API."""
    data = _load_settings()
    api_keys_list: list[dict] = data.get("api_keys", [])
    data["api_keys"] = [k for k in api_keys_list if k["exchange"] != exchange]
    _save_settings(data)
    logger.info("API key deleted for %s", exchange)
    return await get_settings()


@router.post("/keys/test", response_model=ApiKeyTestResponse)
async def test_api_key(req: ApiKeyTestRequest):
    """Teste la connectivité d'une clé API exchange (via POST body)."""
    try:
        from src.execution.connectors.ccxt_connector import create_connector

        connector = create_connector(
            exchange_name=req.exchange,
            api_key=req.api_key,
            api_secret=req.api_secret,
            testnet=True,
        )
        await connector.start()
    except Exception as exc:
        return ApiKeyTestResponse(
            success=False,
            message=f"Connection failed: {exc}",
            exchange=req.exchange,
        )

    try:
        balance = await connector.get_balance()
        await connector.stop()
        return ApiKeyTestResponse(
            success=True,
            message=f"Connected. Balance: {len(balance)} assets.",
            exchange=req.exchange,
        )
    except Exception as exc:
        await connector.stop()
        return ApiKeyTestResponse(
            success=False,
            message=f"Auth failed or invalid keys: {exc}",
            exchange=req.exchange,
        )
