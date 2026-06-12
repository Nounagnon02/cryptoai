"""
Estimation du slippage pour l'exécution des ordres.

Calcule le slippage attendu en fonction de la taille de l'ordre,
de la liquidité du carnet, et de la volatilité récente.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.data.market.schema import OrderBook, OrderBookLevel
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SlippageEstimate:
    """Estimation complète du slippage."""

    symbol: str
    side: str  # buy | sell
    order_value_usd: float  # Valeur de l'ordre en USD

    # Slippage estimé
    expected_slippage_pct: float  # Slippage attendu en %
    expected_slippage_bps: float  # Slippage attendu en bps
    max_slippage_pct: float  # Slippage maximum possible

    # Execution
    expected_fill_price: float  # Prix moyen estimé
    levels_to_fill: int  # Nombre de niveaux traversés
    fill_ratio: float  # Ratio de remplissage (0-1)

    # Liquidité
    available_liquidity: float  # Liquidité disponible dans la direction
    liquidity_score: float  # 0-100

    # Recommandation
    is_safe: bool  # True si slippage acceptable
    recommendation: str  # market | limit | cancel
    estimated_gas_cost: float | None = None  # Pour DEX


class SlippageEstimator:
    """
    Estime le slippage pour l'exécution d'ordres.

    Calcule le coût d'impact sur le prix en fonction de :
    - La profondeur du carnet d'ordres
    - La taille de l'ordre
    - La volatilité récente
    - La liquidité disponible
    """

    # Seuils de slippage par stratégie (en bps)
    SAFE_SLIPPAGE = {
        "market": 20,  # Market order : max 20 bps
        "limit": 5,    # Limit order : max 5 bps
        "twap": 15,    # TWAP : max 15 bps
    }

    def estimate(
        self,
        order_book: OrderBook,
        side: str,
        order_value_usd: float,
        strategy: str = "market",
    ) -> SlippageEstimate:
        """
        Estime le slippage pour un ordre.

        Args:
            order_book: Carnet d'ordres actuel
            side: 'buy' ou 'sell'
            order_value_usd: Valeur de l'ordre en USD
            strategy: Type d'exécution (market, limit, twap)

        Returns:
            SlippageEstime complet
        """
        levels = order_book.asks if side == "buy" else order_book.bids

        if not levels:
            return SlippageEstimate(
                symbol=order_book.symbol,
                side=side,
                order_value_usd=order_value_usd,
                expected_slippage_pct=0,
                expected_slippage_bps=0,
                max_slippage_pct=0,
                expected_fill_price=0,
                levels_to_fill=0,
                fill_ratio=0,
                available_liquidity=0,
                liquidity_score=0,
                is_safe=False,
                recommendation="cancel",
            )

        best_price = levels[0].price

        # Simuler l'exécution
        avg_price, levels_filled, filled_value, remaining = self._simulate_fill(
            levels, order_value_usd
        )

        fill_ratio = (order_value_usd - remaining) / order_value_usd if order_value_usd > 0 else 0

        # Slippage
        slippage_pct = abs(avg_price - best_price) / best_price * 100 if best_price > 0 else 0
        slippage_bps = slippage_pct * 100

        # Liquidité disponible
        available_liquidity = filled_value
        liquidity_score = self._compute_liquidity_score(levels, order_value_usd)

        # Slippage max (pire cas : au prix le plus éloigné)
        max_slippage_pct = (
            abs(levels[-1].price if levels else best_price - best_price) / best_price * 100
            if best_price > 0 else 0
        )

        # Sécurité et recommandation
        safe_threshold = self.SAFE_SLIPPAGE.get(strategy, 20)
        is_safe = slippage_bps <= safe_threshold and fill_ratio >= 0.9

        if is_safe and fill_ratio >= 1.0:
            recommendation = "market"
        elif is_safe and fill_ratio >= 0.5:
            recommendation = "limit"
        else:
            recommendation = "cancel"

        return SlippageEstimate(
            symbol=order_book.symbol,
            side=side,
            order_value_usd=order_value_usd,
            expected_slippage_pct=round(slippage_pct, 4),
            expected_slippage_bps=round(slippage_bps, 2),
            max_slippage_pct=round(max_slippage_pct, 4),
            expected_fill_price=round(avg_price, 8),
            levels_to_fill=levels_filled,
            fill_ratio=round(fill_ratio, 4),
            available_liquidity=round(available_liquidity, 2),
            liquidity_score=liquidity_score,
            is_safe=is_safe,
            recommendation=recommendation,
        )

    def _simulate_fill(
        self,
        levels: list[OrderBookLevel],
        order_value: float,
    ) -> tuple[float, int, float, float]:
        """
        Simule le remplissage d'un ordre dans le carnet.

        Returns:
            (prix_moyen, niveaux_traversés, valeur_remplie, restant)
        """
        remaining = order_value
        total_value = 0.0
        total_quantity = 0.0
        levels_filled = 0

        for level in levels:
            if remaining <= 0:
                break

            level_value = level.value_usd
            if remaining >= level_value:
                total_value += level_value
                total_quantity += level_value / level.price if level.price > 0 else 0
                remaining -= level_value
                levels_filled += 1
            else:
                total_value += remaining
                total_quantity += remaining / level.price if level.price > 0 else 0
                remaining = 0
                levels_filled += 1
                break

        avg_price = total_value / total_quantity if total_quantity > 0 else 0
        return avg_price, levels_filled, total_value, remaining

    def _compute_liquidity_score(
        self,
        levels: list[OrderBookLevel],
        order_value: float,
    ) -> float:
        """Score de liquidité (0-100) pour un ordre donné."""
        if not levels:
            return 0

        # Liquidité disponible dans les 10 premiers niveaux
        available = sum(level.value_usd for level in levels[:10])

        if available <= 0:
            return 0

        # Ratio liquidité / taille ordre
        coverage = available / max(order_value, 1)

        if coverage >= 10:
            score = 100
        elif coverage >= 5:
            score = 80
        elif coverage >= 2:
            score = 60
        elif coverage >= 1:
            score = 40
        elif coverage >= 0.5:
            score = 20
        else:
            score = 10

        return score

    def estimate_max_safe_size(
        self,
        order_book: OrderBook,
        side: str,
        max_slippage_bps: float = 10,
    ) -> float:
        """
        Estime la taille maximum d'ordre pour un slippage donné.

        Args:
            order_book: Carnet d'ordres
            side: 'buy' ou 'sell'
            max_slippage_bps: Slippage maximum acceptable

        Returns:
            Valeur maximum de l'ordre en USD
        """
        levels = order_book.asks if side == "buy" else order_book.bids
        if not levels:
            return 0

        best_price = levels[0].price
        max_price_impact = max_slippage_bps / 10000  # bps → decimal

        cumulative_value = 0.0
        for level in levels:
            price_impact = abs(level.price - best_price) / best_price if best_price > 0 else 0
            if price_impact > max_price_impact:
                break
            cumulative_value += level.value_usd

        return cumulative_value
