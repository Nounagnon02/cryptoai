"""
Paper Trading — Exchange simulé pour validation.

Simule un exchange réel avec :
- Capital fictif avec historique complet
- Mêmes décisions qu'en production (même code path)
- Simulation slippage et fees
- Logs complets pour analyse
- Dashboard dédié paper vs live
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.execution.connectors import BaseConnector
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PaperTrade:
    """Trade simulé."""

    trade_id: str
    symbol: str
    side: str  # buy | sell
    quantity: float
    price: float
    value_usd: float
    fee: float
    fee_currency: str
    timestamp: float
    status: str  # open | closed
    pnl: float = 0.0
    pnl_pct: float = 0.0
    close_price: float | None = None
    close_timestamp: float | None = None
    strategy: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperState:
    """État du paper trading."""

    initial_capital: float
    current_capital: float
    cash_reserve: float
    open_positions: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_fees: float
    total_pnl: float
    total_pnl_pct: float
    win_rate: float
    sharpe_ratio: float


class PaperExchange(BaseConnector):
    """
    Exchange simulé pour paper trading.

    Simule le comportement d'un vrai exchange :
    - Slippage aléatoire proportionnel à la taille de l'ordre
    - Frais configurables (0.1% par défaut)
    - Exécution partielle possible
    - Délai d'exécution simulé
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        fee_rate: float = 0.001,  # 0.1%
        slippage_model: str = "conservative",  # conservative | moderate | aggressive
    ) -> None:
        self._initial_capital = initial_capital
        self._cash_reserve = initial_capital
        self._positions: dict[str, PaperTrade] = {}
        self._closed_trades: list[PaperTrade] = []
        self._fee_rate = fee_rate
        self._slippage_model = slippage_model

        # Prix simulés (pour suivi PnL non-réalisé)
        self._prices: dict[str, float] = {}

    async def start(self) -> None:
        """Démarre le paper trading."""
        logger.info(
            "PaperExchange started (capital=%.2f, fee=%.1f%%)",
            self._initial_capital, self._fee_rate * 100,
        )

    async def stop(self) -> None:
        """Arrête le paper trading."""
        logger.info("PaperExchange stopped")

    async def create_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        quantity_usd: float,
        order_type: str,  # noqa: ARG002
        limit_price: float | None = None,
        stop_price: float | None = None,  # noqa: ARG002
        slippage_bps: int = 10,
    ) -> dict[str, Any]:
        """
        Simule la création d'un ordre.

        Applique slippage et fees, vérifie le capital disponible.
        """
        # Simuler le prix d'exécution
        base_price = limit_price or self._prices.get(symbol, 100.0)

        # Slippage simulé
        if self._slippage_model == "conservative":
            slippage_pct = random.uniform(0, slippage_bps / 10000 * 1.5)
        elif self._slippage_model == "moderate":
            slippage_pct = random.uniform(0, slippage_bps / 10000 * 0.8)
        else:  # aggressive
            slippage_pct = random.uniform(0, slippage_bps / 10000 * 0.3)

        if side == "buy":
            exec_price = base_price * (1 + slippage_pct)
        else:
            exec_price = base_price * (1 - slippage_pct)

        # Calculer la quantité
        if quantity > 0:
            final_quantity = quantity
            final_value = quantity * exec_price
        else:
            final_value = min(quantity_usd, self._cash_reserve)
            final_quantity = final_value / exec_price

        # Vérifier le capital
        if side == "buy" and final_value > self._cash_reserve:
            logger.warning("Insufficient funds: need %.2f, have %.2f", final_value, self._cash_reserve)
            final_value = self._cash_reserve
            final_quantity = final_value / exec_price

        # Frais
        fee = final_value * self._fee_rate
        self._cash_reserve -= fee

        # Exécution
        trade_id = f"paper_{int(time.time() * 1000)}_{symbol}_{side}"

        if side == "buy":
            self._cash_reserve -= final_value
            self._positions[symbol] = PaperTrade(
                trade_id=trade_id,
                symbol=symbol,
                side="buy",
                quantity=final_quantity,
                price=exec_price,
                value_usd=final_value,
                fee=fee,
                fee_currency="USD",
                timestamp=datetime.now(UTC).timestamp(),
                status="open",
                strategy="default",
            )
        else:
            # Sell — fermer la position si elle existe
            position = self._positions.pop(symbol, None)
            if position:
                pnl = (exec_price - position.price) * position.quantity
                pnl_pct = (exec_price - position.price) / position.price * 100

                closed_trade = PaperTrade(
                    trade_id=trade_id,
                    symbol=symbol,
                    side="sell",
                    quantity=position.quantity,
                    price=exec_price,
                    value_usd=final_value,
                    fee=fee,
                    fee_currency="USD",
                    timestamp=datetime.now(UTC).timestamp(),
                    status="closed",
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    close_price=exec_price,
                    close_timestamp=datetime.now(UTC).timestamp(),
                )
                self._closed_trades.append(closed_trade)
                self._cash_reserve += final_value

        self._prices[symbol] = exec_price

        logger.info(
            "Paper %s %s: %.4f @ %.2f (slippage=%.4f%%, fee=%.4f)",
            side.upper(), symbol, final_quantity, exec_price,
            slippage_pct * 100, fee,
        )

        return {
            "exchange_id": trade_id,
            "status": "filled" if final_quantity > 0 else "rejected",
            "filled_quantity": final_quantity,
            "filled_value_usd": final_value,
            "average_price": exec_price,
            "fee": fee,
            "fee_currency": "USD",
            "slippage_pct": slippage_pct * 100,
        }

    async def cancel_order(self, exchange_order_id: str) -> bool:
        """Simule l'annulation d'un ordre."""
        logger.info("Paper cancel order %s", exchange_order_id)
        return True

    async def get_order(self, exchange_order_id: str) -> dict[str, Any]:
        """Simule la récupération d'un ordre."""
        return {
            "exchange_id": exchange_order_id,
            "status": "filled",
        }

    async def get_balance(self) -> dict[str, float]:
        """Retourne le solde simulé."""
        positions_value = sum(
            pos.value_usd for pos in self._positions.values()
        )
        total_equity = self._cash_reserve + positions_value
        open_pnl = self._calculate_open_pnl()

        return {
            "total_equity": total_equity,
            "cash": self._cash_reserve,
            "positions_value": positions_value,
            "open_pnl": open_pnl,
            "initial_capital": self._initial_capital,
            "total_pnl": total_equity - self._initial_capital,
        }

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Retourne un ticker simulé."""
        base_price = self._prices.get(symbol, 100.0)
        return {
            "symbol": symbol,
            "last": base_price,
            "bid": base_price * 0.999,
            "ask": base_price * 1.001,
            "volume": random.uniform(1000, 10000),
            "timestamp": datetime.now(UTC).timestamp(),
        }

    def update_price(self, symbol: str, price: float) -> None:
        """Met à jour un prix simulé (appelé par le market data engine)."""
        self._prices[symbol] = price

        # Mettre à jour la valeur des positions ouvertes
        if symbol in self._positions:
            pos = self._positions[symbol]
            pos.value_usd = pos.quantity * price

    def _calculate_open_pnl(self) -> float:
        """Calcule le PnL non-réalisé des positions ouvertes."""
        total = 0.0
        for symbol, pos in self._positions.items():
            current_price = self._prices.get(symbol, pos.price)
            total += (current_price - pos.price) * pos.quantity
        return total

    def get_state(self) -> PaperState:
        """État complet du paper trading."""
        positions_value = sum(
            pos.value_usd for pos in self._positions.values()
        )
        total_equity = self._cash_reserve + positions_value
        total_pnl = total_equity - self._initial_capital
        total_pnl_pct = (total_pnl / self._initial_capital) * 100

        total_trades = len(self._closed_trades)
        winning = sum(1 for t in self._closed_trades if t.pnl > 0)
        losing = total_trades - winning
        total_fees = sum(t.fee for t in self._closed_trades)

        # Sharpe ratio simplifié
        if self._closed_trades:
            returns = [t.pnl_pct for t in self._closed_trades]
            avg_return = sum(returns) / len(returns)
            std = (
                (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                if len(returns) > 1 else 1.0
            )
            sharpe = (avg_return / max(std, 0.01)) * (252 ** 0.5)  # Annualisé
        else:
            sharpe = 0.0

        return PaperState(
            initial_capital=self._initial_capital,
            current_capital=total_equity,
            cash_reserve=self._cash_reserve,
            open_positions=len(self._positions),
            total_trades=total_trades,
            winning_trades=winning,
            losing_trades=losing,
            total_fees=total_fees,
            total_pnl=total_pnl,
            total_pnl_pct=round(total_pnl_pct, 2),
            win_rate=round(winning / max(total_trades, 1) * 100, 1),
            sharpe_ratio=round(sharpe, 2),
        )

    def get_summary(self) -> dict[str, Any]:
        """Résumé formaté pour le dashboard."""
        state = self.get_state()
        return {
            "mode": "paper",
            "initial_capital": round(state.initial_capital, 2),
            "current_capital": round(state.current_capital, 2),
            "total_pnl": round(state.total_pnl, 2),
            "total_pnl_pct": state.total_pnl_pct,
            "cash_reserve": round(state.cash_reserve, 2),
            "open_positions": state.open_positions,
            "total_trades": state.total_trades,
            "win_rate": state.win_rate,
            "sharpe_ratio": state.sharpe_ratio,
            "total_fees": round(state.total_fees, 4),
        }
