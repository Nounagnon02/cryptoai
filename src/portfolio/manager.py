"""
Portfolio Manager — Gestion centralisée du portefeuille.

Responsabilités :
1. Allocation de capital entre stratégies
2. Rebalancing automatique (périodique + threshold-based)
3. Suivi des performances par stratégie
4. Gestion des positions globales (sector exposure, correlation)
5. Cash reserve management
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PortfolioLimits:
    """Limites globales du portefeuille."""

    # Concentration
    max_single_position_pct: float = 25.0
    max_top3_positions_pct: float = 50.0
    max_sector_exposure_pct: float = 40.0

    # Cash
    min_cash_reserve_pct: float = 15.0
    target_cash_reserve_pct: float = 20.0

    # Rebalancement
    rebalance_threshold_pct: float = 5.0  # Déclenchement si dérive > 5%
    rebalance_min_interval_hours: int = 24  # Min 24h entre rebalances

    # Stratégies
    max_strategies_active: int = 4
    min_allocation_per_strategy: float = 5.0  # % min par stratégie active
    max_allocation_single_strategy: float = 50.0  # % max pour une stratégie

    # Leverage
    max_portfolio_leverage: float = 2.0
    max_strategy_leverage: float = 1.5

    # Perf
    max_daily_loss_pct: float = 5.0
    max_weekly_loss_pct: float = 12.0
    max_monthly_loss_pct: float = 20.0
    max_drawdown_from_peak: float = 25.0


@dataclass
class StrategyAllocation:
    """Allocation à une stratégie."""

    strategy_name: str
    target_pct: float  # % du portefeuille
    current_pct: float
    pnl_daily: float
    pnl_weekly: float
    pnl_monthly: float
    sharpe_ratio: float
    is_active: bool = True
    last_rebalance: float = 0.0  # timestamp


@dataclass
class PortfolioState:
    """État complet du portefeuille."""

    # Valeurs
    total_value: float
    cash_reserve: float
    positions_value: float
    peak_value: float

    # Exposition
    positions_count: int
    sector_exposures: dict[str, float]
    leverage_used: float
    cash_reserve_pct: float

    # Stratégies
    strategies: dict[str, StrategyAllocation] = field(default_factory=dict)

    # Perf
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    drawdown_from_peak: float = 0.0

    # Flags
    needs_rebalance: bool = False
    is_halted: bool = False


@dataclass
class RebalanceAction:
    """Action de rebalancement."""

    symbol: str
    current_value: float
    target_value: float
    action: str  # buy | sell | hold
    difference: float
    reason: str


class PortfolioManager:
    """
    Gestionnaire de portefeuille central.

    Opère à un niveau au-dessus du RiskManager :
    - RiskManager valide chaque trade individuellement
    - PortfolioManager gère l'allocation globale et le rebalancement
    """

    def __init__(self, limits: PortfolioLimits | None = None) -> None:
        self.limits = limits or PortfolioLimits()

        # État
        self._total_value: float = 0.0
        self._cash_reserve: float = 0.0
        self._peak_value: float = 0.0
        self._positions: dict[str, dict[str, Any]] = {}
        self._sector_map: dict[str, str] = {}  # symbol → sector
        self._strategy_map: dict[str, str] = {}  # symbol → strategy_name
        self._strategies: dict[str, StrategyAllocation] = {}

        # Tracking PnL
        self._daily_initial_value: float = 0.0
        self._weekly_initial_value: float = 0.0
        self._monthly_initial_value: float = 0.0
        self._last_rebalance: float = 0.0

        self._running = False

    async def start(self) -> None:
        """Démarre le portfolio manager."""
        logger.info("PortfolioManager starting")
        self._running = True
        self._daily_initial_value = self._total_value
        self._weekly_initial_value = self._total_value
        self._monthly_initial_value = self._total_value
        logger.info("PortfolioManager started (value=%.2f)", self._total_value)

    async def stop(self) -> None:
        """Arrête le portfolio manager."""
        self._running = False
        logger.info("PortfolioManager stopped")

    def initialize(self, initial_capital: float) -> None:
        """Initialise le portefeuille avec un capital de départ."""
        self._total_value = initial_capital
        self._cash_reserve = initial_capital
        self._peak_value = initial_capital
        self._daily_initial_value = initial_capital
        self._weekly_initial_value = initial_capital
        self._monthly_initial_value = initial_capital
        logger.info("Portfolio initialized with %.2f", initial_capital)

    def register_strategy(
        self,
        name: str,
        target_pct: float,
        sharpe_ratio: float = 1.0,
    ) -> None:
        """
        Enregistre une stratégie pour l'allocation.

        Args:
            name: Nom de la stratégie
            target_pct: Pourcentage cible du portefeuille
            sharpe_ratio: Ratio de Sharpe attendu
        """
        if len(self._strategies) >= self.limits.max_strategies_active:
            logger.warning("Max strategies reached (%d)", self.limits.max_strategies_active)
            return

        target_pct = min(target_pct, self.limits.max_allocation_single_strategy)
        target_pct = max(target_pct, self.limits.min_allocation_per_strategy)

        self._strategies[name] = StrategyAllocation(
            strategy_name=name,
            target_pct=target_pct,
            current_pct=0.0,
            pnl_daily=0.0,
            pnl_weekly=0.0,
            pnl_monthly=0.0,
            sharpe_ratio=sharpe_ratio,
        )
        logger.info("Strategy '%s' registered (target=%.1f%%, sharpe=%.2f)",
                     name, target_pct, sharpe_ratio)

    def assign_position(
        self,
        symbol: str,
        value_usd: float,
        sector: str = "general",
        strategy: str = "default",
    ) -> None:
        """
        Assigne une position au portefeuille.

        Args:
            symbol: Actif
            value_usd: Valeur en USD
            sector: Secteur de l'actif
            strategy: Stratégie associée
        """
        self._positions[symbol] = {
            "value_usd": value_usd,
            "sector": sector,
            "strategy": strategy,
            "updated_at": datetime.now(UTC).timestamp(),
        }
        self._sector_map[symbol] = sector
        self._strategy_map[symbol] = strategy

        # Mettre à jour l'allocation de la stratégie
        total_strategy_value = sum(
            p["value_usd"] for p in self._positions.values()
            if p["strategy"] == strategy
        )
        if strategy in self._strategies:
            self._strategies[strategy].current_pct = (
                total_strategy_value / max(self._total_value, 1) * 100
            )

    def remove_position(self, symbol: str) -> None:
        """Retire une position fermée."""
        strategy = self._strategy_map.pop(symbol, "default")
        self._sector_map.pop(symbol, None)
        self._positions.pop(symbol, None)

        # Recalculer allocation stratégie
        if strategy in self._strategies:
            total_strategy_value = sum(
                p["value_usd"] for p in self._positions.values()
                if p["strategy"] == strategy
            )
            self._strategies[strategy].current_pct = (
                total_strategy_value / max(self._total_value, 1) * 100
            )

    def update_value(self, total_value: float, cash_reserve: float) -> None:
        """
        Met à jour la valeur totale du portefeuille.

        Met à jour peak, drawdown, et flags de perte.
        """
        self._total_value = total_value
        self._cash_reserve = cash_reserve

        if total_value > self._peak_value:
            self._peak_value = total_value

        # PnL périodes
        daily_pnl = total_value - self._daily_initial_value
        _weekly_pnl = total_value - self._weekly_initial_value
        _monthly_pnl = total_value - self._monthly_initial_value

        # Drawdown
        dd = (self._peak_value - total_value) / max(self._peak_value, 1) * 100

        # Vérifier les limites de perte
        if abs(daily_pnl) / max(self._daily_initial_value, 1) * 100 >= self.limits.max_daily_loss_pct:
            logger.warning("Daily loss limit reached: %.2f%%", daily_pnl)
            self._halt_trading("daily_loss_limit")

        if dd >= self.limits.max_drawdown_from_peak:
            logger.warning("Max drawdown reached: %.2f%%", dd)
            self._halt_trading("max_drawdown")

    def _halt_trading(self, reason: str) -> None:
        """Arrête le trading quand une limite est atteinte."""
        for strategy in self._strategies.values():
            strategy.is_active = False
        logger.critical("Trading halted: %s", reason)

    def check_allocation_limits(self, symbol: str, value_usd: float) -> tuple[bool, list[str]]:
        """
        Vérifie si l'ajout d'une position respecte les limites.

        Returns:
            (autorized, reasons) — True si autorisé
        """
        violations: list[str] = []
        position_pct = value_usd / max(self._total_value, 1) * 100

        # Limite individuelle
        if position_pct > self.limits.max_single_position_pct:
            violations.append(
                f"Position {symbol}: {position_pct:.1f}% > max {self.limits.max_single_position_pct}%"
            )

        # Top 3 positions
        sorted_positions = sorted(
            self._positions.items(),
            key=lambda x: abs(x[1]["value_usd"]),
            reverse=True,
        )
        top3_value = sum(abs(p[1]["value_usd"]) for p in sorted_positions[:2])
        top3_pct = (top3_value + value_usd) / max(self._total_value, 1) * 100
        if len(sorted_positions) >= 2 and top3_pct > self.limits.max_top3_positions_pct:
            violations.append(
                f"Top 3 positions: {top3_pct:.1f}% > max {self.limits.max_top3_positions_pct}%"
            )

        # Exposition secteur
        sector = self._sector_map.get(symbol, "general")
        sector_exposure = sum(
            abs(p["value_usd"]) for s, p in self._positions.items()
            if self._sector_map.get(s) == sector
        )
        new_sector_exposure = (sector_exposure + value_usd) / max(self._total_value, 1) * 100
        if new_sector_exposure > self.limits.max_sector_exposure_pct:
            violations.append(
                f"Sector {sector}: {new_sector_exposure:.1f}% > max {self.limits.max_sector_exposure_pct}%"
            )

        return len(violations) == 0, violations

    def check_rebalance_needed(self) -> list[RebalanceAction]:
        """
        Vérifie si un rebalancement est nécessaire.

        Compare les allocations actuelles aux cibles et génère
        des actions si la dérive dépasse le seuil configuré.
        """
        actions: list[RebalanceAction] = []

        # Vérifier l'intervalle minimum
        now = datetime.now(UTC).timestamp()
        if now - self._last_rebalance < self.limits.rebalance_min_interval_hours * 3600:
            return actions

        # Cash reserve
        cash_pct = self._cash_reserve / max(self._total_value, 1) * 100
        if cash_pct < self.limits.min_cash_reserve_pct:
            # Vendre des positions pour libérer du cash
            sell_value = (self.limits.target_cash_reserve_pct - cash_pct) / 100 * self._total_value
            for symbol, pos in sorted(
                self._positions.items(),
                key=lambda x: x[1]["value_usd"],
                reverse=True,
            ):
                if sell_value <= 0:
                    break
                actions.append(RebalanceAction(
                    symbol=symbol,
                    current_value=pos["value_usd"],
                    target_value=max(0, pos["value_usd"] - sell_value * 0.5),
                    action="sell",
                    difference=min(pos["value_usd"], sell_value * 0.5),
                    reason="Rebalance: cash reserve below minimum",
                ))
                sell_value -= pos["value_usd"] * 0.5

        # Vérifier les dérives par stratégie
        for strategy_name, alloc in self._strategies.items():
            drift = abs(alloc.current_pct - alloc.target_pct)
            if drift > self.limits.rebalance_threshold_pct and alloc.is_active:
                # Trouver les positions de cette stratégie
                strategy_positions = [
                    (s, p) for s, p in self._positions.items()
                    if p.get("strategy") == strategy_name
                ]

                if alloc.current_pct < alloc.target_pct and strategy_positions:
                    # Sous-exposé → acheter
                    pass  # La décision d'achat revient au Decision Engine
                elif alloc.current_pct > alloc.target_pct:
                    # Surexposé → vendre
                    for symbol, pos in strategy_positions:
                        reduction = pos["value_usd"] * (drift / 100)
                        actions.append(RebalanceAction(
                            symbol=symbol,
                            current_value=pos["value_usd"],
                            target_value=pos["value_usd"] - reduction,
                            action="sell",
                            difference=reduction,
                            reason=f"Strategy {strategy_name} overexposed by {drift:.1f}%",
                        ))

        if actions:
            self._last_rebalance = now
            logger.info("Rebalance needed: %d actions", len(actions))

        return actions

    def get_state(self) -> PortfolioState:
        """Retourne l'état complet du portefeuille."""
        # Calculer les PnL périodes
        daily_pnl = self._total_value - self._daily_initial_value
        weekly_pnl = self._total_value - self._weekly_initial_value
        monthly_pnl = self._total_value - self._monthly_initial_value

        # Drawdown
        dd = (self._peak_value - self._total_value) / max(self._peak_value, 1) * 100

        # Expositions sectorielles
        sector_exposures: dict[str, float] = {}
        for pos in self._positions.values():
            sector = pos.get("sector", "general")
            sector_exposures[sector] = sector_exposures.get(sector, 0) + abs(pos["value_usd"])

        # Normaliser en %
        total = max(self._total_value, 1)
        sector_exposures = {k: v / total * 100 for k, v in sector_exposures.items()}

        positions_value = sum(abs(p["value_usd"]) for p in self._positions.values())
        cash_pct = self._cash_reserve / total * 100

        # Vérifier si rebalancement nécessaire
        needs_rebalance = len(self.check_rebalance_needed()) > 0

        # Vérifier si halted (no strategies = not halted)
        is_halted = bool(self._strategies) and all(not s.is_active for s in self._strategies.values())

        return PortfolioState(
            total_value=self._total_value,
            cash_reserve=self._cash_reserve,
            positions_value=positions_value,
            peak_value=self._peak_value,
            positions_count=len(self._positions),
            sector_exposures=sector_exposures,
            leverage_used=positions_value / max(self._cash_reserve, 1),
            cash_reserve_pct=cash_pct,
            strategies=dict(self._strategies),
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            monthly_pnl=monthly_pnl,
            drawdown_from_peak=dd,
            needs_rebalance=needs_rebalance,
            is_halted=is_halted,
        )

    def get_summary(self) -> dict[str, Any]:
        """Résumé formaté pour le dashboard."""
        state = self.get_state()
        return {
            "total_value": round(state.total_value, 2),
            "peak_value": round(state.peak_value, 2),
            "cash_reserve": round(state.cash_reserve, 2),
            "cash_reserve_pct": round(state.cash_reserve_pct, 1),
            "positions_count": state.positions_count,
            "positions_value": round(state.positions_value, 2),
            "daily_pnl": round(state.daily_pnl, 2),
            "daily_pnl_pct": round(
                state.daily_pnl / max(self._daily_initial_value, 1) * 100, 2
            ),
            "drawdown": round(state.drawdown_from_peak, 2),
            "leverage": round(state.leverage_used, 2),
            "needs_rebalance": state.needs_rebalance,
            "strategies": {
                name: {
                    "target_pct": alloc.target_pct,
                    "current_pct": round(alloc.current_pct, 1),
                    "sharpe": round(alloc.sharpe_ratio, 2),
                    "is_active": alloc.is_active,
                }
                for name, alloc in self._strategies.items()
            },
            "sector_exposure": {
                sector: round(pct, 1)
                for sector, pct in state.sector_exposures.items()
            },
        }

    # --- PnL Tracking ---

    def record_pnl(self, pnl: float) -> None:
        """Enregistre un PnL réalisé et met à jour les tracking periods."""
        self._total_value += pnl

        # Vérifier si on change de jour
        # (Dans une implémentation complète, on reset daily/weekly/monthly
        #  en fonction des dates réelles)

    def reset_daily(self) -> None:
        """Reset du tracking journalier (appelé quotidiennement)."""
        self._daily_initial_value = self._total_value
        for strategy in self._strategies.values():
            strategy.pnl_daily = 0.0

    def reset_weekly(self) -> None:
        """Reset du tracking hebdomadaire."""
        self._weekly_initial_value = self._total_value
        for strategy in self._strategies.values():
            strategy.pnl_weekly = 0.0

    def reset_monthly(self) -> None:
        """Reset du tracking mensuel."""
        self._monthly_initial_value = self._total_value
        for strategy in self._strategies.values():
            strategy.pnl_monthly = 0.0
