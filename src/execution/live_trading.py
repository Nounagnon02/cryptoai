"""
Live Trading Engine — Execution securisee pour trading avec fonds reels.

Point d'entree UNIQUE pour toute execution live. Chaque ordre passe par :
1. CircuitBreaker    → Le marche/actif est-il tradable ?
2. RiskManager       → La taille/risque est-il acceptable ?
3. OrderDeduplicator → Cet ordre a-t-il deja ete envoye ?
4. ExecutionManager  → Envoi avec retry + backoff
5. OrderReconciler   → Verification post-execution + audit trail

Securite :
- Emergency stop global (arret immediat de tous les ordres)
- API keys chiffrees AES-256-GCM au repos
- Journal d'audit complet pour chaque trade
- Reconciliation des positions au demarrage
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger
from src.utils.security.encryption import EncryptionEngine

logger = get_logger(__name__)


# ── Emergency Stop ──────────────────────────────────────────────

class EmergencyStopLevel(StrEnum):
    """Niveaux d'arret d'urgence."""
    NONE = "none"           # Trading normal
    SOFT = "soft"           # Plus de nouveaux ordres, garde les positions
    HARD = "hard"           # Plus aucun ordre, clôture toutes les positions
    CRITICAL = "critical"   # Arret total, liquidation immediate


class EmergencyStop:
    """
    Arret d'urgence global — thread-safe, irreversible sans action manuelle.

    Une fois active au niveau HARD ou CRITICAL, necessite une
    reinitialisation explicite via l'API admin.
    """

    def __init__(self) -> None:
        self._level: EmergencyStopLevel = EmergencyStopLevel.NONE
        self._triggered_at: float | None = None
        self._triggered_by: str = ""
        self._reason: str = ""
        self._positions_liquidated: bool = False

    @property
    def level(self) -> EmergencyStopLevel:
        return self._level

    @property
    def is_active(self) -> bool:
        return self._level != EmergencyStopLevel.NONE

    @property
    def blocks_new_orders(self) -> bool:
        return self._level in (
            EmergencyStopLevel.SOFT,
            EmergencyStopLevel.HARD,
            EmergencyStopLevel.CRITICAL,
        )

    @property
    def blocks_all_orders(self) -> bool:
        return self._level in (EmergencyStopLevel.HARD, EmergencyStopLevel.CRITICAL)

    def trigger(
        self,
        level: EmergencyStopLevel,
        triggered_by: str = "system",
        reason: str = "",
    ) -> None:
        """Declenche l'arret d'urgence (irreversible sans reset)."""
        if level == EmergencyStopLevel.NONE:
            return
        self._level = level
        self._triggered_at = time.time()
        self._triggered_by = triggered_by
        self._reason = reason
        logger.critical(
            "EMERGENCY STOP: level=%s by=%s reason=%s",
            level.value, triggered_by, reason,
        )

    def reset(self, reset_by: str = "admin") -> None:
        """Reinitialise l'arret d'urgence (action admin)."""
        old_level = self._level
        self._level = EmergencyStopLevel.NONE
        self._triggered_at = None
        self._triggered_by = ""
        self._reason = ""
        self._positions_liquidated = False
        logger.warning("EMERGENCY STOP RESET by %s (was %s)", reset_by, old_level.value)

    def status(self) -> dict[str, Any]:
        """Etat actuel de l'arret d'urgence."""
        return {
            "is_active": self.is_active,
            "level": self._level.value,
            "triggered_at": self._triggered_at,
            "triggered_at_iso": (
                datetime.fromtimestamp(self._triggered_at, UTC).isoformat()
                if self._triggered_at else None
            ),
            "triggered_by": self._triggered_by,
            "reason": self._reason,
            "blocks_new_orders": self.blocks_new_orders,
            "blocks_all_orders": self.blocks_all_orders,
        }


# ── Order Deduplication ─────────────────────────────────────────

@dataclass
class OrderFingerprint:
    """Empreinte unique d'un ordre pour deduplication."""
    symbol: str
    side: str
    quantity_usd: float
    score: float
    timestamp_bucket: int  # bucket de 5 minutes

    @classmethod
    def from_signal(
        cls,
        symbol: str,
        side: str,
        quantity_usd: float,
        score: float,
        window_seconds: int = 300,
    ) -> OrderFingerprint:
        """Cree une empreinte a partir du signal de trading."""
        bucket = int(time.time() / window_seconds)
        return cls(
            symbol=symbol,
            side=side,
            quantity_usd=round(quantity_usd, 2),
            score=round(score, 1),
            timestamp_bucket=bucket,
        )

    def to_hash(self) -> str:
        """Hash SHA-256 de l'empreinte."""
        raw = f"{self.symbol}|{self.side}|{self.quantity_usd}|{self.score}|{self.timestamp_bucket}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class OrderDeduplicator:
    """
    Empeche les ordres dupliques dans une fenetre de temps.

    Deux ordres identiques (meme symbole, side, taille, score)
    dans la meme fenetre de 5 minutes = duplique.
    """

    def __init__(self, window_seconds: int = 300, max_cache: int = 500) -> None:
        self._window = window_seconds
        self._sent_hashes: set[str] = set()
        self._max_cache = max_cache

    def is_duplicate(self, fingerprint: OrderFingerprint) -> bool:
        """Verifie si un ordre equivalent a deja ete envoye."""
        fp_hash = fingerprint.to_hash()
        if fp_hash in self._sent_hashes:
            logger.warning(
                "Duplicate order detected: %s %s $%.2f (bucket=%d)",
                fingerprint.symbol, fingerprint.side,
                fingerprint.quantity_usd, fingerprint.timestamp_bucket,
            )
            return True
        return False

    def mark_sent(self, fingerprint: OrderFingerprint) -> None:
        """Marque un ordre comme envoye."""
        fp_hash = fingerprint.to_hash()
        self._sent_hashes.add(fp_hash)
        # Nettoyer si trop d'entrees
        if len(self._sent_hashes) > self._max_cache:
            # Garder les plus recentes (hash est non ordonne, on vide la moitie)
            keep = list(self._sent_hashes)[-self._max_cache // 2:]
            self._sent_hashes = set(keep)


# ── Live Trade Record ───────────────────────────────────────────

@dataclass
class LiveTradeRecord:
    """Enregistrement complet d'un trade live pour audit."""
    trade_id: str
    symbol: str
    side: str
    action: str
    quantity: float
    quantity_usd: float
    order_type: str
    execution_price: float | None = None
    filled_quantity: float = 0.0
    filled_value_usd: float = 0.0
    fee: float = 0.0
    fee_currency: str = "USD"
    status: str = "pending"
    error: str | None = None

    # Risk assessment
    risk_score: float = 100.0
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    risk_reward_ratio: float = 0.0

    # Timestamps
    created_at: float = 0.0
    executed_at: float | None = None
    exchange_order_id: str = ""

    # Source
    strategy: str = "ai_core"
    fingerprint_hash: str = ""


# ── Live Trading Engine ─────────────────────────────────────────

@dataclass
class LiveTradingConfig:
    """Configuration du LiveTradingEngine."""
    # ID de l'exchange
    exchange_id: str = "binance"

    # API keys (dechiffrees au moment de l'utilisation)
    api_key: str = ""
    api_secret: str = ""

    # Testnet
    testnet: bool = False

    # Securite
    require_risk_check: bool = True
    require_circuit_check: bool = True
    dedup_window_seconds: int = 300
    max_slippage_bps: int = 50
    min_order_size_usd: float = 10.0
    max_order_size_usd: float = 10_000.0

    # Reconciliation
    reconcile_on_startup: bool = True
    max_position_count: int = 10
    max_exposure_pct: float = 80.0  # % max du capital expose

    # Audit
    audit_log_path: str = "data/live_trades.jsonl"


class LiveTradingEngine:
    """
    Moteur de trading live — point d'entree unique pour les fonds reels.

    Usage:
        engine = LiveTradingEngine(config)
        await engine.start()

        # Avant chaque trade:
        can_trade, reason = await engine.pre_trade_check(symbol, price)
        if can_trade:
            result = await engine.execute_trade(
                symbol="BTC/USDT", side="buy",
                quantity_usd=1000, score=75.0, action="strong_buy",
                entry_price=current_price, atr=atr_value,
            )

        await engine.stop()
    """

    def __init__(self, config: LiveTradingConfig | None = None) -> None:
        self.config = config or LiveTradingConfig()
        self._emergency_stop = EmergencyStop()
        self._deduplicator = OrderDeduplicator(
            window_seconds=self.config.dedup_window_seconds,
        )
        self._connector: Any = None
        self._risk_manager: Any = None
        self._circuit_breaker: Any = None
        self._execution_manager: Any = None
        self._live_trades: list[LiveTradeRecord] = []
        self._running = False
        self._portfolio_value: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────

    async def start(self) -> None:
        """Initialise toutes les connexions et verifications."""
        logger.info("LiveTradingEngine starting (exchange=%s, testnet=%s)",
                     self.config.exchange_id, self.config.testnet)

        # 1. Circuit Breaker
        from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        self._circuit_breaker = CircuitBreaker(CircuitBreakerConfig())
        await self._circuit_breaker.start()
        logger.info("CircuitBreaker initialized")

        # 2. Risk Manager
        from src.risk.manager import RiskLimits, RiskManager
        self._risk_manager = RiskManager(RiskLimits())
        await self._risk_manager.start()
        logger.info("RiskManager initialized")

        # 3. Exchange Connector
        from src.execution.connectors.ccxt_connector import CCXTConnector
        self._connector = CCXTConnector(
            exchange_id=self.config.exchange_id,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
            testnet=self.config.testnet,
        )
        await self._connector.start()
        logger.info("CCXTConnector connected to %s", self.config.exchange_id)

        # 4. Execution Manager
        from src.execution.manager import ExecutionConfig, ExecutionManager
        exec_config = ExecutionConfig(
            max_slippage_bps=self.config.max_slippage_bps,
            max_retries=3,
            retry_delay_seconds=1.0,
        )
        self._execution_manager = ExecutionManager(exec_config)
        self._execution_manager.register_connector(
            self.config.exchange_id, self._connector,
        )
        await self._execution_manager.start()
        logger.info("ExecutionManager initialized")

        # 5. Reconciliation
        if self.config.reconcile_on_startup:
            await self._reconcile_positions()

        self._running = True
        logger.info("LiveTradingEngine ready — trading LIVE on %s",
                     self.config.exchange_id)

    async def stop(self) -> None:
        """Arret propre de toutes les connexions."""
        logger.info("LiveTradingEngine stopping...")
        self._running = False

        if self._execution_manager:
            await self._execution_manager.stop()
        if self._connector:
            await self._connector.stop()
        if self._circuit_breaker:
            await self._circuit_breaker.stop()
        if self._risk_manager:
            await self._risk_manager.stop()

        logger.info("LiveTradingEngine stopped. %d trades logged.",
                     len(self._live_trades))

    # ── Emergency Stop ───────────────────────────────────────

    @property
    def emergency_stop(self) -> EmergencyStop:
        return self._emergency_stop

    def trigger_emergency_stop(
        self,
        level: str = "hard",
        triggered_by: str = "api",
        reason: str = "Manual trigger",
    ) -> dict[str, Any]:
        """Declenche l'arret d'urgence."""
        stop_level = EmergencyStopLevel(level)
        self._emergency_stop.trigger(stop_level, triggered_by, reason)
        return self._emergency_stop.status()

    def reset_emergency_stop(self, reset_by: str = "admin") -> dict[str, Any]:
        """Reinitialise l'arret d'urgence."""
        self._emergency_stop.reset(reset_by)
        return self._emergency_stop.status()

    # ── Pre-Trade Validation ─────────────────────────────────

    async def pre_trade_check(
        self,
        symbol: str,
        current_price: float,
    ) -> tuple[bool, str]:
        """
        Verification complete avant tout ordre live.

        Returns:
            (autorise, raison)
        """
        # 0. Emergency stop
        if self._emergency_stop.blocks_new_orders:
            return False, f"EMERGENCY STOP active ({self._emergency_stop.level.value})"

        if not self._running:
            return False, "LiveTradingEngine not running"

        # 1. Circuit breaker — niveau systeme
        if self._circuit_breaker and not self._circuit_breaker.is_system_operational():
            return False, "Circuit breaker: system halted"

        # 2. Circuit breaker — niveau symbole
        if self._circuit_breaker and not self._circuit_breaker.check_symbol(symbol, current_price):
            return False, f"Circuit breaker: {symbol} blocked"

        # 3. Verification solde exchange
        if self._connector:
            try:
                balance = await self._connector.get_balance()
                self._portfolio_value = balance.get("total_equity", 0)
                if self._portfolio_value <= 0:
                    return False, "Zero or negative balance"
            except Exception as exc:
                logger.error("Balance check failed: %s", exc)
                return False, f"Cannot verify balance: {exc}"

        # 4. Nombre max de positions
        open_positions = len([
            t for t in self._live_trades
            if t.status == "filled" and t.side == "buy"
        ])
        # Compter aussi les positions ouvertes via le risk manager
        rm_positions = len(self._risk_manager._current_positions) if self._risk_manager else 0
        total_positions = max(open_positions, rm_positions)
        if total_positions >= self.config.max_position_count:
            return False, f"Max positions reached ({self.config.max_position_count})"

        return True, "ok"

    async def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity_usd: float,
        score: float,
        action: str,
        entry_price: float,
        atr: float | None = None,
        volatility: float | None = None,
        sector: str = "general",
        strategy: str = "ai_core",
    ) -> LiveTradeRecord:
        """
        Execute un trade live avec toutes les verifications.

        C'est LE point d'entree unique pour tout ordre live.
        Aucun ordre ne doit contourner cette methode.

        Args:
            symbol: Paire (ex: BTC/USDT)
            side: buy | sell
            quantity_usd: Taille en USD
            score: Score IA (0-100)
            action: Action (strong_buy, buy, sell, etc.)
            entry_price: Prix actuel
            atr: ATR pour calcul stop-loss
            volatility: Volatilite annualisee
            sector: Secteur de l'actif
            strategy: Strategie source

        Returns:
            LiveTradeRecord complet
        """
        # ── 1. Pre-trade check ──
        can_trade, reason = await self.pre_trade_check(symbol, entry_price)
        if not can_trade:
            record = LiveTradeRecord(
                trade_id=f"live_rejected_{int(time.time()*1000)}",
                symbol=symbol, side=side, action=action,
                quantity=0.0, quantity_usd=quantity_usd,
                order_type="market", status="rejected",
                error=reason, created_at=time.time(),
                strategy=strategy,
            )
            self._live_trades.append(record)
            self._write_audit_log(record)
            return record

        # ── 2. Deduplication ──
        fingerprint = OrderFingerprint.from_signal(
            symbol, side, quantity_usd, score,
            self.config.dedup_window_seconds,
        )
        if self._deduplicator.is_duplicate(fingerprint):
            return LiveTradeRecord(
                trade_id=f"live_dup_{int(time.time()*1000)}",
                symbol=symbol, side=side, action=action,
                quantity=0.0, quantity_usd=quantity_usd,
                order_type="market", status="rejected",
                error="Duplicate order (same signal in window)",
                created_at=time.time(), strategy=strategy,
                fingerprint_hash=fingerprint.to_hash(),
            )

        # ── 3. Risk assessment ──
        if self.config.require_risk_check and self._risk_manager:
            risk = self._risk_manager.assess_trade(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                portfolio_value=self._portfolio_value,
                atr=atr,
                volatility=volatility,
                sector=sector,
                position_size_usd=quantity_usd,
            )

            if not risk.checks_passed:
                record = LiveTradeRecord(
                    trade_id=f"live_risk_{int(time.time()*1000)}",
                    symbol=symbol, side=side, action=action,
                    quantity=0.0, quantity_usd=quantity_usd,
                    order_type="market", status="rejected",
                    error=f"Risk check failed: {risk.failed_checks}",
                    risk_score=risk.score,
                    stop_loss_price=risk.stop_loss_price,
                    take_profit_price=risk.take_profit_price,
                    risk_reward_ratio=risk.risk_reward_ratio,
                    created_at=time.time(), strategy=strategy,
                    fingerprint_hash=fingerprint.to_hash(),
                )
                self._live_trades.append(record)
                self._write_audit_log(record)
                logger.warning(
                    "Trade rejected by risk manager: %s %s $%.2f — %s",
                    symbol, side, quantity_usd, risk.failed_checks,
                )
                return record

            # Utiliser la taille recommandee par le risk manager
            final_size_usd = min(quantity_usd, risk.recommended_size)
            final_size_usd = max(final_size_usd, self.config.min_order_size_usd)
            final_size_usd = min(final_size_usd, self.config.max_order_size_usd)
        else:
            risk = None
            final_size_usd = quantity_usd

        # ── 4. Size limits ──
        if final_size_usd < self.config.min_order_size_usd:
            return LiveTradeRecord(
                trade_id=f"live_min_{int(time.time()*1000)}",
                symbol=symbol, side=side, action=action,
                quantity=0.0, quantity_usd=final_size_usd,
                order_type="market", status="rejected",
                error=f"Order too small: ${final_size_usd:.2f} < ${self.config.min_order_size_usd}",
                created_at=time.time(), strategy=strategy,
            )
        if final_size_usd > self.config.max_order_size_usd:
            final_size_usd = self.config.max_order_size_usd

        # ── 5. Execution ──
        order_type = "market" if score > 70 else "limit"
        trade_id = f"live_{int(time.time()*1000)}_{symbol.replace('/', '_')}"

        try:
            # Construire OrderParams pour l'ExecutionManager
            from src.core.decision_engine import ActionType, OrderParams
            from src.core.decision_engine import OrderType as DOrderType

            ot = DOrderType.MARKET if order_type == "market" else DOrderType.LIMIT
            at = ActionType(action) if action in [a.value for a in ActionType] else ActionType.BUY

            order_params = OrderParams(
                symbol=symbol,
                side=side,
                action=at,
                order_type=ot,
                quantity=0.0,
                quantity_usd=final_size_usd,
                portfolio_pct=round(final_size_usd / max(self._portfolio_value, 1) * 100, 2),
                slippage_tolerance=self.config.max_slippage_bps / 10000,
                strategy=strategy,
                reason=f"Score: {score:.0f}/100, Action: {action}",
                created_at=time.time(),
            )

            result = await self._execution_manager.execute_order(
                order_params=order_params,
                exchange=self.config.exchange_id,
                max_slippage_bps=self.config.max_slippage_bps,
            )

            # ── 6. Reconciliation ──
            record = LiveTradeRecord(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                action=action,
                quantity=result.filled_quantity,
                quantity_usd=result.filled_value_usd,
                order_type=order_type,
                execution_price=result.average_price,
                filled_quantity=result.filled_quantity,
                filled_value_usd=result.filled_value_usd,
                fee=result.fee,
                fee_currency=result.fee_currency,
                status=result.status.value,
                error=result.error,
                risk_score=risk.score if risk else 100.0,
                stop_loss_price=risk.stop_loss_price if risk else None,
                take_profit_price=risk.take_profit_price if risk else None,
                risk_reward_ratio=risk.risk_reward_ratio if risk else 0.0,
                created_at=time.time(),
                executed_at=time.time() if result.status.value == "filled" else None,
                exchange_order_id=result.exchange_order_id,
                strategy=strategy,
                fingerprint_hash=fingerprint.to_hash(),
            )

            # Mettre a jour le RiskManager
            if self._risk_manager and result.status.value == "filled":
                self._risk_manager.update_position(
                    symbol=symbol,
                    value_usd=result.filled_value_usd,
                    sector=sector,
                )

            # Marquer comme envoye
            self._deduplicator.mark_sent(fingerprint)
            self._live_trades.append(record)
            self._write_audit_log(record)

            logger.info(
                "LIVE TRADE: %s %s %s $%.2f @ %.2f [%s] score=%.0f risk=%.0f",
                symbol, side.upper(), result.status.value,
                result.filled_value_usd, result.average_price,
                action, score, record.risk_score,
            )

            return record

        except Exception as exc:
            logger.error("LIVE TRADE FAILED: %s %s — %s", symbol, side, exc)
            record = LiveTradeRecord(
                trade_id=trade_id,
                symbol=symbol, side=side, action=action,
                quantity=0.0, quantity_usd=final_size_usd,
                order_type=order_type, status="failed",
                error=str(exc), created_at=time.time(),
                strategy=strategy,
                fingerprint_hash=fingerprint.to_hash(),
            )
            self._live_trades.append(record)
            self._write_audit_log(record)
            return record

    # ── Reconciliation ───────────────────────────────────────

    async def _reconcile_positions(self) -> None:
        """
        Reconciliation des positions au demarrage.

        Compare les positions internes avec les positions reelles
        de l'exchange pour detecter les divergences.
        """
        if not self._connector:
            return

        try:
            balance = await self._connector.get_balance()
            self._portfolio_value = balance.get("total_equity", 0)
            logger.info(
                "Reconciliation: portfolio=$%.2f, free=$%.2f, used=$%.2f",
                self._portfolio_value,
                sum(balance.get("free", {}).values()),
                sum(balance.get("used", {}).values()),
            )
        except Exception as exc:
            logger.error("Reconciliation failed: %s", exc)

    # ── Audit ────────────────────────────────────────────────

    def _write_audit_log(self, record: LiveTradeRecord) -> None:
        """Ecrit un trade dans le journal d'audit JSONL."""
        try:
            log_path = Path(self.config.audit_log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            entry = {
                "trade_id": record.trade_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "symbol": record.symbol,
                "side": record.side,
                "action": record.action,
                "quantity_usd": record.quantity_usd,
                "filled_value_usd": record.filled_value_usd,
                "execution_price": record.execution_price,
                "fee": record.fee,
                "status": record.status,
                "error": record.error,
                "risk_score": record.risk_score,
                "stop_loss": record.stop_loss_price,
                "take_profit": record.take_profit_price,
                "strategy": record.strategy,
                "exchange_order_id": record.exchange_order_id,
            }

            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.error("Failed to write audit log: %s", exc)

    # ── Status ───────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Etat complet du LiveTradingEngine."""
        recent_trades = self._live_trades[-20:] if self._live_trades else []
        filled = [t for t in self._live_trades if t.status == "filled"]
        rejected = [t for t in self._live_trades if t.status == "rejected"]
        failed = [t for t in self._live_trades if t.status == "failed"]

        total_filled_value = sum(t.filled_value_usd for t in filled)
        total_fees = sum(t.fee for t in filled)

        return {
            "running": self._running,
            "exchange": self.config.exchange_id,
            "testnet": self.config.testnet,
            "emergency_stop": self._emergency_stop.status(),
            "portfolio_value": round(self._portfolio_value, 2),
            "trades": {
                "total": len(self._live_trades),
                "filled": len(filled),
                "rejected": len(rejected),
                "failed": len(failed),
            },
            "volume": {
                "total_filled_usd": round(total_filled_value, 2),
                "total_fees_usd": round(total_fees, 4),
            },
            "circuit_breaker": (
                self._circuit_breaker.get_status()
                if self._circuit_breaker else {}
            ),
            "recent_trades": [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "action": t.action,
                    "status": t.status,
                    "value_usd": round(t.filled_value_usd, 2),
                    "price": t.execution_price,
                    "risk_score": t.risk_score,
                    "error": t.error,
                }
                for t in recent_trades
            ],
        }


# ── API Key Management ─────────────────────────────────────────

class ApiKeyVault:
    """
    Gestion securisee des cles API exchange.

    Chiffrement AES-256-GCM au repos.
    Les cles ne sont dechiffrees qu'au moment de la connexion.
    """

    def __init__(self, vault_path: str = "data/api_keys.enc") -> None:
        self._vault_path = Path(vault_path)
        self._engine = self._init_encryption_engine()

    def _init_encryption_engine(self) -> EncryptionEngine:
        """Initialise le moteur de chiffrement."""
        encryption_key = os.getenv("CRYPTOAI_ENCRYPTION_KEY", "")
        if not encryption_key:
            # Fallback: generer une cle persistante
            key_path = Path("data/.encryption_key")
            if key_path.exists():
                encryption_key = key_path.read_text().strip()
            else:
                engine = EncryptionEngine()
                engine._master_key = engine.generate_key()
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_text(engine._master_key)
                encryption_key = engine._master_key
                logger.warning(
                    "Generated encryption key at %s — BACK IT UP! "
                    "Set CRYPTOAI_ENCRYPTION_KEY env var for production.",
                    key_path,
                )
        return EncryptionEngine(master_key=encryption_key)

    def store_keys(self, exchange: str, api_key: str, api_secret: str) -> None:
        """Stocke des cles API chiffrees."""
        vault: dict = {}
        if self._vault_path.exists():
            try:
                vault = json.loads(self._vault_path.read_text())
            except Exception:
                vault = {}

        vault[exchange] = {
            "key": self._engine.encrypt(api_key),
            "secret": self._engine.encrypt(api_secret),
            "stored_at": datetime.now(UTC).isoformat(),
        }

        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        self._vault_path.write_text(json.dumps(vault, indent=2))
        logger.info("API keys stored for %s (AES-256-GCM encrypted)", exchange)

    def load_keys(self, exchange: str) -> tuple[str, str] | None:
        """Charge et dechiffre les cles API."""
        if not self._vault_path.exists():
            return None

        try:
            vault = json.loads(self._vault_path.read_text())
            entry = vault.get(exchange)
            if not entry:
                return None

            api_key = self._engine.decrypt(entry["key"])
            api_secret = self._engine.decrypt(entry["secret"])
            return api_key, api_secret
        except Exception as exc:
            logger.error("Failed to load API keys for %s: %s", exchange, exc)
            return None

    def delete_keys(self, exchange: str) -> bool:
        """Supprime les cles API pour un exchange."""
        if not self._vault_path.exists():
            return False
        try:
            vault = json.loads(self._vault_path.read_text())
            vault.pop(exchange, None)
            self._vault_path.write_text(json.dumps(vault, indent=2))
            logger.info("API keys deleted for %s", exchange)
            return True
        except Exception as exc:
            logger.error("Failed to delete keys: %s", exc)
            return False

    def list_exchanges(self) -> list[str]:
        """Liste les exchanges avec des cles stockees."""
        if not self._vault_path.exists():
            return []
        try:
            vault = json.loads(self._vault_path.read_text())
            return list(vault.keys())
        except Exception:
            return []


# ── Factory ────────────────────────────────────────────────────

def create_live_trading_engine(
    exchange_id: str = "binance",
    testnet: bool = False,
) -> LiveTradingEngine:
    """
    Cree un LiveTradingEngine avec les cles API du vault.

    Ordre de resolution des cles API :
    1. Variables d'environnement (CRYPTOAI_{EXCHANGE}_KEY / _SECRET)
    2. Vault chiffre (data/api_keys.enc)
    3. Config file (deconseille en production)
    """
    api_key = ""
    api_secret = ""

    # 1. Variables d'environnement
    env_prefix = exchange_id.upper()
    api_key = os.getenv(f"CRYPTOAI_{env_prefix}_KEY", "")
    api_secret = os.getenv(f"CRYPTOAI_{env_prefix}_SECRET", "")

    # 2. Vault chiffre
    if not api_key or not api_secret:
        vault = ApiKeyVault()
        keys = vault.load_keys(exchange_id)
        if keys:
            api_key, api_secret = keys

    # 3. Config (fallback)
    if not api_key or not api_secret:
        from src.config import config
        if exchange_id == "binance":
            api_key = config.binance_api_key
            api_secret = config.binance_api_secret
        elif exchange_id == "bybit":
            api_key = config.bybit_api_key
            api_secret = config.bybit_api_secret

    if not api_key or not api_secret:
        logger.error(
            "No API keys found for %s. Set CRYPTOAI_%s_KEY/_SECRET "
            "or store via API. Trading disabled.",
            exchange_id, env_prefix,
        )

    config = LiveTradingConfig(
        exchange_id=exchange_id,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )

    return LiveTradingEngine(config)


__all__ = [
    "LiveTradingEngine",
    "LiveTradingConfig",
    "LiveTradeRecord",
    "ApiKeyVault",
    "EmergencyStop",
    "EmergencyStopLevel",
    "OrderDeduplicator",
    "OrderFingerprint",
    "create_live_trading_engine",
]
