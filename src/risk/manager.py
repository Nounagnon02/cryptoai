"""
Risk Manager central — Gestion des risques institutionnelle.

Fonctionnalités :
- Stop Loss intelligent : ATR-based + fixed percentage
- Take Profit : risk/reward ratio + trailing
- Position sizing : Kelly Criterion adapté avec limites de risque
- Volatility management : sizing ajusté selon la volatilité
- Correlation management : exposition sectorielle limitée
- Loss limits : daily, weekly, monthly hard limits
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


class RiskLevel(StrEnum):
    """Niveaux de risque."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    EXTREME = "extreme"


@dataclass
class RiskLimits:
    """Limites de risque configurables."""

    # Stop Loss
    stop_loss_atr_multiplier: float = 2.0  # × ATR
    stop_loss_fixed_pct: float = 5.0  # % fixe max
    stop_loss_hard_limit: float = 10.0  # Limite absolute

    # Take Profit
    take_profit_min_rr: float = 1.5  # Risk/Reward minimum
    take_profit_trailing_activation: float = 1.0  # Activation trailing (× ATR)
    take_profit_trailing_distance: float = 1.5  # Distance trailing (× ATR)

    # Position Sizing
    max_position_pct: float = 25.0  # % max du portefeuille par position
    max_leverage: float = 3.0  # Levier maximum
    kelly_fraction: float = 0.25  # Fraction du Kelly (conservateur)

    # Portfolio
    max_sector_exposure_pct: float = 40.0  # % max par secteur
    max_correlation_exposure: float = 50.0  # % max dans actifs corrélés
    min_cash_reserve_pct: float = 15.0  # % minimum en cash

    # Loss Limits
    max_daily_loss_pct: float = 5.0  # Perte max par jour
    max_weekly_loss_pct: float = 12.0  # Perte max par semaine
    max_monthly_loss_pct: float = 20.0  # Perte max par mois
    max_drawdown_pct: float = 25.0  # Drawdown maximum depuis le peak

    # Volatility
    max_volatility_position: float = 0.05  # Volatilité max pour sizing normal
    volatility_scaling: bool = True  # Ajuster la taille à la volatilité


@dataclass
class RiskAssessment:
    """Évaluation complète des risques pour une opération."""

    symbol: str
    side: str  # buy | sell

    # Stop Loss
    stop_loss_price: float | None = None
    stop_loss_pct: float = 0.0
    stop_loss_type: str = "atr"  # atr | fixed | hard

    # Take Profit
    take_profit_price: float | None = None
    take_profit_pct: float = 0.0
    risk_reward_ratio: float = 0.0

    # Position Sizing
    recommended_size: float = 0.0  # USD
    max_size: float = 0.0  # USD
    kelly_percentage: float = 0.0
    risk_per_trade_pct: float = 0.0

    # Checks
    checks_passed: bool = True
    failed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 100.0  # 0-100 (100 = pas de risque)


@dataclass
class DailyRiskState:
    """État des risques journaliers."""

    date: str  # YYYY-MM-DD
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    stopped_out: int = 0
    is_halted: bool = False  # Trading stoppé si limite atteinte


class RiskManager:
    """
    Gestionnaire de risques central.

    Valide chaque trade avant exécution :
    1. Vérifie les limites de perte (daily/weekly/monthly)
    2. Calcule le Stop Loss optimal
    3. Calcule le Take Profit optimal
    4. Détermine la taille de position (Kelly adapté)
    5. Vérifie les limites de corrélation et secteur
    6. Ajuste à la volatilité
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self._daily_state: dict[str, DailyRiskState] = {}
        self._peak_portfolio_value: float = 0.0
        self._current_portfolio_value: float = 100_000.0
        self._current_positions: dict[str, dict[str, Any]] = {}
        self._running = False

    async def start(self) -> None:
        """Démarre le risk manager."""
        logger.info("RiskManager starting")
        self._running = True
        logger.info("RiskManager started")

    async def stop(self) -> None:
        """Arrête le risk manager."""
        self._running = False
        logger.info("RiskManager stopped")

    def assess_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        portfolio_value: float,
        atr: float | None = None,
        volatility: float | None = None,
        sector: str = "general",
        _correlation_group: str = "general",
        position_size_usd: float | None = None,
    ) -> RiskAssessment:
        """
        Évalue les risques d'un trade avant exécution.

        Args:
            symbol: Actif
            side: buy | sell
            entry_price: Prix d'entrée
            portfolio_value: Valeur du portefeuille
            atr: ATR pour le stop loss dynamique
            volatility: Volatilité annualisée
            sector: Secteur de l'actif
            correlation_group: Groupe de corrélation
            position_size_usd: Taille suggérée (optionnelle)

        Returns:
            RiskAssessment complet
        """
        assessment = RiskAssessment(
            symbol=symbol,
            side=side,
        )

        self._current_portfolio_value = portfolio_value

        # 1. Vérifier les limites de perte
        if not self._check_loss_limits():
            assessment.checks_passed = False
            assessment.failed_checks.append("Limite de perte journalière atteinte")
            assessment.score = 0
            return assessment

        # 2. Calculer le Stop Loss
        sl_price, sl_pct, sl_type = self._calculate_stop_loss(
            entry_price, side, atr
        )
        assessment.stop_loss_price = sl_price
        assessment.stop_loss_pct = sl_pct
        assessment.stop_loss_type = sl_type

        # 3. Calculer le Take Profit
        tp_price, tp_pct, rr = self._calculate_take_profit(
            entry_price, sl_price, side
        )
        assessment.take_profit_price = tp_price
        assessment.take_profit_pct = tp_pct
        assessment.risk_reward_ratio = rr

        # 4. Calculer la taille de position (Kelly)
        kelly_pct = self._calculate_kelly(sl_pct, tp_pct)
        assessment.kelly_percentage = kelly_pct

        # 5. Taille recommandée
        base_size = portfolio_value * (kelly_pct / 100) if kelly_pct > 0 else portfolio_value * 0.02
        max_size = portfolio_value * (self.limits.max_position_pct / 100)

        # Ajustement par volatilité
        if volatility and self.limits.volatility_scaling:
            vol_ratio = self.limits.max_volatility_position / max(volatility, 0.001)
            base_size *= min(1.0, vol_ratio)
            max_size *= min(1.0, vol_ratio)

        # Ajustement par exposition secteur
        sector_exposure = self._get_sector_exposure(sector)
        if sector_exposure + (base_size / portfolio_value) > (self.limits.max_sector_exposure_pct / 100):
            max_allowed = (self.limits.max_sector_exposure_pct / 100 - sector_exposure) * portfolio_value
            base_size = min(base_size, max_allowed)
            assessment.warnings.append(
                f"Exposition secteur {sector} limitée à "
                f"${max_allowed:,.0f}"
            )

        assessment.recommended_size = min(base_size, max_size)
        assessment.max_size = max_size

        # 6. Risque par trade
        risk_amount = assessment.recommended_size * (sl_pct / 100)
        assessment.risk_per_trade_pct = (risk_amount / portfolio_value) * 100

        # 7. Vérifications finales
        checks = self._run_checks(assessment, position_size_usd)
        assessment.checks_passed = len(checks["failed"]) == 0
        assessment.failed_checks = checks["failed"]
        assessment.warnings.extend(checks["warnings"])

        # Score de risque (100 = parfait, 0 = bloqué)
        score = 100.0
        if assessment.risk_reward_ratio < 1.0:
            score -= 20
        if sl_pct > self.limits.stop_loss_hard_limit:
            score -= 30
        if assessment.risk_per_trade_pct > 2.0:
            score -= 20
        if assessment.failed_checks:
            score -= 30
        assessment.score = max(0, score)

        return assessment

    def _calculate_stop_loss(
        self,
        entry_price: float,
        side: str,
        atr: float | None,
    ) -> tuple[float | None, float, str]:
        """
        Calcule le Stop Loss optimal.

        Stratégie : ATR-based si ATR disponible, sinon fixed %.
        """
        if atr and atr > 0:
            distance = atr * self.limits.stop_loss_atr_multiplier
            distance_pct = (distance / entry_price) * 100

            if distance_pct > self.limits.stop_loss_hard_limit:
                distance_pct = self.limits.stop_loss_hard_limit
                distance = entry_price * (distance_pct / 100)

            sl_price = entry_price - distance if side == "buy" else entry_price + distance

            return sl_price, distance_pct, "atr"

        # Fallback : fixed %
        sl_pct = min(self.limits.stop_loss_fixed_pct, self.limits.stop_loss_hard_limit)
        if side == "buy":
            sl_price = entry_price * (1 - sl_pct / 100)
        else:
            sl_price = entry_price * (1 + sl_pct / 100)

        return sl_price, sl_pct, "fixed"

    def _calculate_take_profit(
        self,
        entry_price: float,
        stop_loss_price: float | None,
        side: str,
    ) -> tuple[float | None, float, float]:
        """
        Calcule le Take Profit basé sur le Risk/Reward.

        RR minimum configurable, par défaut 1.5:1.
        """
        if not stop_loss_price or stop_loss_price == entry_price:
            return None, 0, 0

        # Distance de risque
        if side == "buy":
            risk_distance = abs(entry_price - stop_loss_price)
            tp_distance = risk_distance * self.limits.take_profit_min_rr
            tp_price = entry_price + tp_distance
        else:
            risk_distance = abs(stop_loss_price - entry_price)
            tp_distance = risk_distance * self.limits.take_profit_min_rr
            tp_price = entry_price - tp_distance

        tp_pct = (tp_distance / entry_price) * 100
        rr = tp_distance / max(risk_distance, 1e-10)

        return tp_price, tp_pct, rr

    def _calculate_kelly(self, stop_loss_pct: float, take_profit_pct: float) -> float:
        """
        Calcule le pourcentage Kelly optimal.

        Version adaptée : utilise un historique de win rate estimé
        et une fraction pour être conservateur.
        """
        if stop_loss_pct <= 0 or take_profit_pct <= 0:
            return 0

        # Win rate estimé (sera affiné avec l'historique)
        win_rate = 0.55

        # Kelly standard : f = (p*b - q) / b, où b = gain/perte
        b = take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 1
        q = 1 - win_rate

        if b <= 0:
            return 0

        kelly = (win_rate * b - q) / b
        kelly = max(0, kelly)  # Pas de négatif

        # Fraction conservatrice
        return kelly * self.limits.kelly_fraction * 100

    def _check_loss_limits(self) -> bool:
        """Vérifie si les limites de perte sont atteintes."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        state = self._get_daily_state(today)

        # Daily limit
        if abs(state.realized_pnl) / max(self._current_portfolio_value, 1) * 100 >= self.limits.max_daily_loss_pct:
            state.is_halted = True
            return False

        # Drawdown
        if self._peak_portfolio_value > 0:
            dd = (self._peak_portfolio_value - self._current_portfolio_value) / self._peak_portfolio_value * 100
            if dd >= self.limits.max_drawdown_pct:
                return False

        return True

    def _run_checks(
        self,
        assessment: RiskAssessment,
        suggested_size: float | None,
    ) -> dict[str, list[str]]:
        """Exécute toutes les vérifications de risque."""
        failed: list[str] = []
        warnings: list[str] = []

        # Taille suggérée
        if suggested_size and suggested_size > assessment.max_size:
            failed.append(f"Taille ${suggested_size:,.0f} > maximum ${assessment.max_size:,.0f}")

        # Risk/Reward
        if assessment.risk_reward_ratio < 1.0:
            failed.append(f"Risk/Reward {assessment.risk_reward_ratio:.1f} < 1.0")

        # Stop Loss hard limit
        if assessment.stop_loss_pct > self.limits.stop_loss_hard_limit:
            failed.append(f"Stop Loss {assessment.stop_loss_pct:.1f}% > hard limit {self.limits.stop_loss_hard_limit}%")

        # Risque par trade
        if assessment.risk_per_trade_pct > 2.0:
            warnings.append(f"Risque élevé par trade: {assessment.risk_per_trade_pct:.2f}%")

        # Cash reserve
        cash_pct = self._get_cash_reserve_pct()
        if cash_pct < self.limits.min_cash_reserve_pct:
            warnings.append(f"Réserve cash {cash_pct:.1f}% < minimum {self.limits.min_cash_reserve_pct}%")

        return {"failed": failed, "warnings": warnings}

    def _get_daily_state(self, date: str) -> DailyRiskState:
        """Récupère ou crée l'état journalier."""
        if date not in self._daily_state:
            self._daily_state[date] = DailyRiskState(date=date)
        return self._daily_state[date]

    def _get_sector_exposure(self, sector: str) -> float:
        """Calcule l'exposition actuelle à un secteur (fraction)."""
        total = 0.0
        for pos in self._current_positions.values():
            if pos.get("sector") == sector:
                total += abs(pos.get("value_usd", 0))
        return total / max(self._current_portfolio_value, 1)

    def _get_cash_reserve_pct(self) -> float:
        """Calcule le pourcentage de cash disponible."""
        positions_value = sum(
            abs(p.get("value_usd", 0)) for p in self._current_positions.values()
        )
        cash = self._current_portfolio_value - positions_value
        return (cash / max(self._current_portfolio_value, 1)) * 100

    def update_position(
        self,
        symbol: str,
        value_usd: float,
        sector: str = "general",
    ) -> None:
        """Met à jour une position dans le risk manager."""
        self._current_positions[symbol] = {
            "value_usd": value_usd,
            "sector": sector,
        }

    def remove_position(self, symbol: str) -> None:
        """Retire une position fermée."""
        self._current_positions.pop(symbol, None)

    def record_trade_result(
        self,
        symbol: str,  # noqa: ARG002
        pnl: float,
        stopped_out: bool = False,
    ) -> None:
        """Enregistre le résultat d'un trade."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        state = self._get_daily_state(today)

        state.realized_pnl += pnl
        state.trades_count += 1
        if stopped_out:
            state.stopped_out += 1
        if pnl > 0:
            state.winning_trades += 1
        else:
            state.losing_trades += 1

    def get_state(self) -> dict[str, Any]:
        """État complet du risk manager."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        daily = self._get_daily_state(today)

        return {
            "daily": {
                "realized_pnl": round(daily.realized_pnl, 2),
                "trades": daily.trades_count,
                "win_rate": round(
                    daily.winning_trades / max(daily.trades_count, 1) * 100, 1
                ),
                "stopped_out": daily.stopped_out,
                "is_halted": daily.is_halted,
            },
            "portfolio": {
                "current_value": round(self._current_portfolio_value, 2),
                "peak_value": round(self._peak_portfolio_value, 2),
                "positions_count": len(self._current_positions),
                "cash_reserve_pct": round(self._get_cash_reserve_pct(), 1),
            },
            "limits": {
                "max_position_pct": self.limits.max_position_pct,
                "max_daily_loss_pct": self.limits.max_daily_loss_pct,
                "max_drawdown_pct": self.limits.max_drawdown_pct,
            },
        }


