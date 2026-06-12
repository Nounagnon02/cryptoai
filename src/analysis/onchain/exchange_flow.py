"""
Analyse des flux d'entrée/sortie des exchanges.

Surveille les mouvements de tokens entre les wallets et les exchanges
pour détecter les tendances d'accumulation ou de distribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExchangeFlowMetrics:
    """Métriques de flux exchange."""

    symbol: str

    # Flux
    inflow_24h: float  # Entrées (USD)
    outflow_24h: float  # Sorties (USD)
    net_flow_24h: float  # Flux net
    inflow_7d: float = 0.0
    outflow_7d: float = 0.0
    net_flow_7d: float = 0.0

    # Ratios
    inflow_outflow_ratio: float = 1.0  # >1 = plus d'entrées
    exchange_balance_change: float = 0.0  # Variation du solde exchange

    # Réserves
    exchange_reserve: float = 0.0  # Solde total sur exchanges
    reserve_ratio_7d: float = 0.0  # Variation des réserves sur 7j

    # Signal
    signal: str = "neutral"
    signal_strength: float = 0.0
    warnings: list[str] = field(default_factory=list)


class ExchangeFlowAnalyzer:
    """
    Analyse les flux d'entrée/sortie des exchanges.

    Interprétation :
    - Net outflow (sorties > entrées) → accumulation, haussier
    - Net inflow (entrées > sorties) → vente potentielle, baissier
    - Exchange balance qui baisse → moins de pression vente
    - Exchange balance qui monte → plus de pression vente
    """

    def __init__(self) -> None:
        self._metrics: dict[str, ExchangeFlowMetrics] = {}

    def analyze(
        self,
        symbol: str,
        inflow_24h: float,
        outflow_24h: float,
        inflow_7d: float | None = None,
        outflow_7d: float | None = None,
        exchange_reserve: float | None = None,
    ) -> ExchangeFlowMetrics:
        """
        Analyse les flux exchange pour un actif.

        Args:
            symbol: Symbole de l'actif
            inflow_24h: Entrées sur les exchanges (24h)
            outflow_24h: Sorties des exchanges (24h)
            inflow_7d: Entrées sur 7 jours
            outflow_7d: Sorties sur 7 jours
            exchange_reserve: Solde total sur exchanges

        Returns:
            ExchangeFlowMetrics avec signal
        """
        net_flow_24h = inflow_24h - outflow_24h
        inflow_outflow_ratio = inflow_24h / max(outflow_24h, 1)

        # Données 7j
        net_flow_7d = 0.0
        reserve_ratio_7d = 0.0
        if inflow_7d is not None and outflow_7d is not None:
            net_flow_7d = inflow_7d - outflow_7d

        if exchange_reserve is not None and exchange_reserve > 0:
            reserve_ratio_7d = net_flow_7d / exchange_reserve

        # Signal
        signal, strength, warnings = self._compute_signal(
            net_flow_24h, inflow_outflow_ratio, reserve_ratio_7d
        )

        metrics = ExchangeFlowMetrics(
            symbol=symbol,
            inflow_24h=inflow_24h,
            outflow_24h=outflow_24h,
            net_flow_24h=net_flow_24h,
            inflow_7d=inflow_7d or 0,
            outflow_7d=outflow_7d or 0,
            net_flow_7d=net_flow_7d,
            inflow_outflow_ratio=round(inflow_outflow_ratio, 2),
            exchange_balance_change=round(net_flow_24h / max(inflow_24h + outflow_24h, 1), 3),
            exchange_reserve=exchange_reserve or 0,
            reserve_ratio_7d=round(reserve_ratio_7d, 4),
            signal=signal,
            signal_strength=strength,
            warnings=warnings,
        )

        self._metrics[symbol] = metrics
        return metrics

    def _compute_signal(
        self,
        net_flow_24h: float,
        inflow_outflow_ratio: float,
        reserve_ratio_7d: float,
    ) -> tuple[str, float, list[str]]:
        """
        Calcule le signal basé sur les flux exchange.

        Returns:
            (direction, force, avertissements)
        """
        warnings: list[str] = []
        score = 0.0

        # Flux net 24h (négatif = sorties = bullish)
        if net_flow_24h < -1_000_000:
            score += 15
        elif net_flow_24h < -100_000:
            score += 8
        elif net_flow_24h > 1_000_000:
            score -= 15
        elif net_flow_24h > 100_000:
            score -= 8

        # Ratio inflow/outflow
        if inflow_outflow_ratio < 0.5:
            score += 10  # Beaucoup plus de sorties
        elif inflow_outflow_ratio < 0.8:
            score += 5
        elif inflow_outflow_ratio > 2.0:
            score -= 10  # Beaucoup plus d'entrées
        elif inflow_outflow_ratio > 1.5:
            score -= 5

        # Variation des réserves sur 7j
        if reserve_ratio_7d < -0.1:
            score += 15  # Baisse significative des réserves
        elif reserve_ratio_7d < -0.05:
            score += 8
        elif reserve_ratio_7d > 0.1:
            score -= 15  # Hausse des réserves
        elif reserve_ratio_7d > 0.05:
            score -= 8

        # Alertes
        if abs(net_flow_24h) > 10_000_000:
            warnings.append(f"Flux exchange anormal: ${abs(net_flow_24h):,.0f}")

        # Direction
        if score > 15:
            signal = "bullish"
        elif score < -15:
            signal = "bearish"
        else:
            signal = "neutral"

        strength = min(1.0, abs(score) / 50)

        return signal, strength, warnings

    def get_metrics(self, symbol: str) -> ExchangeFlowMetrics | None:
        return self._metrics.get(symbol)
