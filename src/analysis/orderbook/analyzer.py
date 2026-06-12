"""
Analyseur de carnet d'ordres (Order Book).

Analyse la liquidité, les déséquilibres, les murs d'ordres,
et calcule des métriques avancées de microstructure de marché.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.data.market.schema import OrderBook, OrderBookLevel
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OrderBookMetrics:
    """Métriques extraites du carnet d'ordres."""

    symbol: str
    timestamp: float

    # Liquidité
    total_bid_volume: float  # Volume total bid (quote currency)
    total_ask_volume: float  # Volume total ask (quote currency)
    bid_ask_ratio: float  # Ratio bid/ask (>1 = pression acheteuse)

    # Distribution
    bid_concentration: float  # 0-1, concentration des bids aux meilleurs prix
    ask_concentration: float  # 0-1, concentration des asks
    depth_imbalance: float  # -1 (bearish) à +1 (bullish)

    # Walls
    bid_wall: float | None = None  # Prix du plus gros mur bid
    ask_wall: float | None = None  # Prix du plus gros mur ask
    wall_imbalance: float = 0.0  # Force relative des murs

    # Spread
    spread_pct: float = 0.0  # Spread en % du mid price
    spread_bps: float = 0.0  # Spread en basis points

    # Microstructure
    price_impact: float = 0.0  # Impact prix estimé pour $10k
    market_order_imbalance: float = 0.0  # Déséquilibre market orders

    # Signaux
    signal: str = "neutral"  # bullish | bearish | neutral
    signal_strength: float = 0.0  # 0-1
    warnings: list[str] = field(default_factory=list)


class OrderBookAnalyzer:
    """
    Analyse en temps réel du carnet d'ordres.

    Détecte :
    - Zones de liquidité (support/résistance dynamiques)
    - Déséquilibres offre/demande
    - Murs d'ordres (walls)
    - Concentrations aux niveaux de prix
    """

    def __init__(self) -> None:
        self._last_metrics: dict[str, OrderBookMetrics] = {}

    def analyze(self, order_book: OrderBook) -> OrderBookMetrics:
        """
        Analyse complète du carnet d'ordres.

        Args:
            order_book: Carnet d'ordres L2

        Returns:
            OrderBookMetrics avec signaux et avertissements
        """
        bids = order_book.bids
        asks = order_book.asks

        if not bids or not asks:
            return OrderBookMetrics(
                symbol=order_book.symbol,
                timestamp=order_book.timestamp,
                total_bid_volume=0,
                total_ask_volume=0,
                bid_ask_ratio=1.0,
                bid_concentration=0,
                ask_concentration=0,
                depth_imbalance=0,
            )

        # Volumes totaux
        total_bid_vol = sum(b.value_usd for b in bids)
        total_ask_vol = sum(a.value_usd for a in asks)

        # Ratio bid/ask
        bid_ask_ratio = total_bid_vol / total_ask_vol if total_ask_vol > 0 else float("inf")

        # Spread
        best_bid = bids[0].price
        best_ask = asks[0].price
        mid_price = (best_bid + best_ask) / 2
        spread_pct = ((best_ask - best_bid) / mid_price) * 100 if mid_price > 0 else 0
        spread_bps = spread_pct * 100

        # Concentration : proportion du volume total dans les 5 premiers niveaux
        bid_top5 = sum(b.value_usd for b in bids[:5])
        ask_top5 = sum(a.value_usd for a in asks[:5])
        bid_concentration = bid_top5 / total_bid_vol if total_bid_vol > 0 else 0
        ask_concentration = ask_top5 / total_ask_vol if total_ask_vol > 0 else 0

        # Depth imbalance : déséquilibre cumulé sur les N niveaux
        depth_levels = min(10, len(bids), len(asks))
        cum_bid = sum(b.value_usd for b in bids[:depth_levels])
        cum_ask = sum(a.value_usd for a in asks[:depth_levels])
        total_depth = cum_bid + cum_ask
        depth_imbalance = (cum_bid - cum_ask) / total_depth if total_depth > 0 else 0

        # Détection de murs (walls) : niveaux avec volume anormalement élevé
        bid_wall, ask_wall = self._detect_walls(bids, asks)
        wall_imbalance = self._compute_wall_imbalance(bid_wall, ask_wall, mid_price)

        # Signal directionnel
        signal, strength, warnings = self._compute_signal(
            bid_ask_ratio, depth_imbalance, wall_imbalance,
            bid_concentration, ask_concentration, spread_bps,
        )

        metrics = OrderBookMetrics(
            symbol=order_book.symbol,
            timestamp=order_book.timestamp,
            total_bid_volume=total_bid_vol,
            total_ask_volume=total_ask_vol,
            bid_ask_ratio=round(bid_ask_ratio, 4),
            bid_concentration=round(bid_concentration, 3),
            ask_concentration=round(ask_concentration, 3),
            depth_imbalance=round(depth_imbalance, 4),
            bid_wall=bid_wall,
            ask_wall=ask_wall,
            wall_imbalance=round(wall_imbalance, 4),
            spread_pct=round(spread_pct, 4),
            spread_bps=round(spread_bps, 2),
            price_impact=round(self._estimate_price_impact(bids, asks, 10_000), 4),
            market_order_imbalance=round(depth_imbalance, 4),
            signal=signal,
            signal_strength=strength,
            warnings=warnings,
        )

        self._last_metrics[order_book.symbol] = metrics
        return metrics

    def _detect_walls(
        self,
        bids: list[OrderBookLevel],
        asks: list[OrderBookLevel],
        threshold_mult: float = 3.0,
    ) -> tuple[float | None, float | None]:
        """
        Détecte les murs d'ordres (concentrations anormales de volume).

        Args:
            bids: Niveaux bid triés par prix décroissant
            asks: Niveaux ask triés par prix croissant
            threshold_mult: Multiplicateur pour détecter un mur

        Returns:
            (prix du mur bid, prix du mur ask)
        """
        bid_wall = None
        ask_wall = None

        if bids:
            bid_volumes = [b.value_usd for b in bids]
            bid_mean = sum(bid_volumes[:10]) / min(10, len(bid_volumes))
            bid_std = (sum((v - bid_mean) ** 2 for v in bid_volumes[:10]) / max(1, len(bid_volumes[:10]))) ** 0.5
            threshold = bid_mean + threshold_mult * max(bid_std, bid_mean * 0.1)

            for b in bids[:10]:
                if b.value_usd > threshold:
                    bid_wall = b.price
                    break

        if asks:
            ask_volumes = [a.value_usd for a in asks]
            ask_mean = sum(ask_volumes[:10]) / min(10, len(ask_volumes))
            ask_std = (sum((v - ask_mean) ** 2 for v in ask_volumes[:10]) / max(1, len(ask_volumes[:10]))) ** 0.5
            threshold = ask_mean + threshold_mult * max(ask_std, ask_mean * 0.1)

            for a in asks[:10]:
                if a.value_usd > threshold:
                    ask_wall = a.price
                    break

        return bid_wall, ask_wall

    def _compute_wall_imbalance(
        self,
        bid_wall: float | None,
        ask_wall: float | None,
        mid_price: float,
    ) -> float:
        """
        Calcule le déséquilibre des murs.

        Returns:
            -1 (mur ask dominant) à +1 (mur bid dominant)
        """
        if bid_wall and ask_wall:
            bid_dist = abs(bid_wall - mid_price) / mid_price
            ask_dist = abs(ask_wall - mid_price) / mid_price
            if bid_dist + ask_dist > 0:
                return (ask_dist - bid_dist) / (bid_dist + ask_dist)
        elif bid_wall:
            return 0.5
        elif ask_wall:
            return -0.5

        return 0.0

    def _compute_signal(
        self,
        bid_ask_ratio: float,
        depth_imbalance: float,
        wall_imbalance: float,
        bid_concentration: float,
        ask_concentration: float,
        spread_bps: float,
    ) -> tuple[str, float, list[str]]:
        """
        Calcule le signal directionnel basé sur l'order book.

        Returns:
            (direction, force, avertissements)
        """
        warnings: list[str] = []
        score = 0.0

        # Bid/Ask ratio
        if bid_ask_ratio > 1.5:
            score += 20
        elif bid_ask_ratio > 1.2:
            score += 10
        elif bid_ask_ratio < 0.67:
            score -= 20
        elif bid_ask_ratio < 0.83:
            score -= 10

        # Depth imbalance
        score += depth_imbalance * 30

        # Walls
        score += wall_imbalance * 20

        # Concentration (haute concentration = manipulation potentielle)
        if bid_concentration > 0.7:
            warnings.append("Haute concentration des bids (spoofing potentiel)")
        if ask_concentration > 0.7:
            warnings.append("Haute concentration des asks (spoofing potentiel)")

        # Spread anormal
        if spread_bps < 1:
            warnings.append("Spread extrêmement serré (marché très liquide)")
        elif spread_bps > 50:
            warnings.append("Spread large (liquidité faible)")

        # Direction
        if score > 15:
            signal = "bullish"
        elif score < -15:
            signal = "bearish"
        else:
            signal = "neutral"

        strength = min(1.0, abs(score) / 60)

        return signal, strength, warnings

    def _estimate_price_impact(
        self,
        bids: list[OrderBookLevel],
        asks: list[OrderBookLevel],
        order_value: float,
    ) -> float:
        """
        Estime l'impact sur le prix d'un ordre de taille donnée.

        Args:
            bids: Niveaux bid
            asks: Niveaux ask
            order_value: Valeur de l'ordre en USD

        Returns:
            Impact estimé en % du mid price
        """
        if not bids or not asks:
            return 0.0

        mid = (bids[0].price + asks[0].price) / 2

        # Estimer l'impact côté ask (achat)
        remaining = order_value
        avg_price = 0.0
        filled = 0.0

        for a in asks:
            level_value = a.value_usd
            if remaining <= level_value:
                avg_price = (avg_price * filled + a.price * remaining) / (filled + remaining) if filled + remaining > 0 else a.price
                filled += remaining
                remaining = 0
                break
            else:
                avg_price = (avg_price * filled + a.price * level_value) / (filled + level_value) if filled + level_value > 0 else a.price
                filled += level_value
                remaining -= level_value

        if filled > 0:
            impact = abs(avg_price - mid) / mid * 100
            return impact

        return 0.0

    def get_last_metrics(self, symbol: str) -> OrderBookMetrics | None:
        """Dernières métriques calculées."""
        return self._last_metrics.get(symbol)

    def get_market_maker_score(self, symbol: str) -> float | None:
        """
        Score de qualité du market making (0-100).

        Basé sur spread, profondeur, et concentration.
        """
        metrics = self._last_metrics.get(symbol)
        if not metrics:
            return None

        score = 100.0

        # Spread (idéal < 5bps)
        score -= min(30, metrics.spread_bps * 0.5)

        # Profondeur
        if metrics.total_bid_volume + metrics.total_ask_volume < 100_000:
            score -= 20

        # Concentration excessive
        if metrics.bid_concentration > 0.8:
            score -= 15
        if metrics.ask_concentration > 0.8:
            score -= 15

        return max(0, min(100, score))
