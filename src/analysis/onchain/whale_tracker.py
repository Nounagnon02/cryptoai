"""
Suivi des transactions whales (gros mouvements).

Analyse les transactions on-chain de grande valeur pour détecter :
- Accumulation / distribution par les whales
- Mouvements vers/sortant des exchanges
- Patterns de whale trading
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class WhaleTransaction:
    """Transaction significative détectée."""

    tx_hash: str
    symbol: str  # Asset concerné (BTC, ETH, etc.)
    value_usd: float  # Valeur en USD
    from_address: str
    to_address: str
    transaction_type: str  # exchange_in | exchange_out | whale_to_whale | unknown
    timestamp: float
    exchange: str | None = None  # Exchange identifié, si applicable
    confidence: float = 0.8


@dataclass
class WhaleMetrics:
    """Métriques whales agrégées."""

    symbol: str
    large_transactions_24h: int  # Nombre de grosses transactions
    total_volume_24h: float  # Volume total whales (USD)
    net_exchange_flow_24h: float  # Flux net vers exchanges (+ = entrée, - = sortie)
    whale_confidence: float  # Sentiment whale (-1 bearish à +1 bullish)
    accumulation_score: float  # 0-100
    distribution_score: float  # 0-100
    top_movements: list[WhaleTransaction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class WhaleTracker:
    """
    Traque les mouvements de whales sur la blockchain.

    NOTE: Version simplifiée — en production, se connecter à
    des APIs comme Whale Alert, Santiment, ou un nœud full.
    """

    # Seuils de valeur pour considérer une transaction "whale"
    WHALE_THRESHOLDS = {
        "BTC": 1_000_000,  # $1M+
        "ETH": 500_000,    # $500k+
        "SOL": 250_000,    # $250k+
        "USDT": 2_000_000, # $2M+
        "USDC": 2_000_000, # $2M+
        "DEFAULT": 500_000,
    }

    # Exchanges identifiés (adresses notoires)
    KNOWN_EXCHANGES = {
        "binance": {"0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be"},
        "coinbase": {"0xa090e606e30bd747d4e6245a1517ebe430f0057e"},
        "kraken": {"0xa83b11093c858c86321fbc4c20fe82cdbd58e09e"},
        "bybit": {},  # À compléter
    }

    def __init__(self) -> None:
        self._transactions: dict[str, list[WhaleTransaction]] = {}
        self._metrics: dict[str, WhaleMetrics] = {}

    def record_transaction(self, tx: WhaleTransaction) -> None:
        """Enregistre une transaction whale."""
        if tx.symbol not in self._transactions:
            self._transactions[tx.symbol] = []
        self._transactions[tx.symbol].append(tx)

        # Garder seulement les 1000 dernières
        if len(self._transactions[tx.symbol]) > 1000:
            self._transactions[tx.symbol] = self._transactions[tx.symbol][-1000:]

    def record_batch(self, transactions: list[WhaleTransaction]) -> None:
        """Enregistre un lot de transactions."""
        for tx in transactions:
            self.record_transaction(tx)

    def compute_metrics(self, symbol: str) -> WhaleMetrics:
        """Calcule les métriques whales pour un actif."""
        txs = self._transactions.get(symbol, [])
        if not txs:
            return WhaleMetrics(
                symbol=symbol,
                large_transactions_24h=0,
                total_volume_24h=0,
                net_exchange_flow_24h=0,
                whale_confidence=0,
                accumulation_score=50,
                distribution_score=50,
            )

        # Transactions des dernières 24h
        now = datetime.now(UTC).timestamp()
        recent = [t for t in txs if t.timestamp > now - 86400]

        if not recent:
            return WhaleMetrics(
                symbol=symbol,
                large_transactions_24h=len(txs[-100:]),
                total_volume_24h=sum(t.value_usd for t in txs[-100:]),
                net_exchange_flow_24h=0,
                whale_confidence=0,
                accumulation_score=50,
                distribution_score=50,
            )

        # Flux exchange
        exchange_in = sum(
            t.value_usd for t in recent
            if t.transaction_type == "exchange_in"
        )
        exchange_out = sum(
            t.value_usd for t in recent
            if t.transaction_type == "exchange_out"
        )
        net_flow = exchange_in - exchange_out

        # Sentiment whale
        # Sortie d'exchange = bullish (retrait pour hold)
        # Entrée sur exchange = bearish (potentiel dump)
        total_tx_volume = sum(t.value_usd for t in recent)
        if total_tx_volume > 0:
            whale_confidence = (exchange_out - exchange_in) / total_tx_volume
        else:
            whale_confidence = 0

        # Accumulation / Distribution
        accumulation = exchange_out / max(total_tx_volume, 1) * 100
        distribution = exchange_in / max(total_tx_volume, 1) * 100

        # Top 5 mouvements
        top = sorted(recent, key=lambda t: t.value_usd, reverse=True)[:5]

        warnings = []
        if net_flow > 10_000_000:
            warnings.append(f"Fort afflux vers exchanges (${net_flow:,.0f})")
        elif net_flow < -10_000_000:
            warnings.append(f"Fort retrait des exchanges (${abs(net_flow):,.0f})")

        metrics = WhaleMetrics(
            symbol=symbol,
            large_transactions_24h=len(recent),
            total_volume_24h=total_tx_volume,
            net_exchange_flow_24h=net_flow,
            whale_confidence=round(whale_confidence, 3),
            accumulation_score=min(100, max(0, accumulation)),
            distribution_score=min(100, max(0, distribution)),
            top_movements=top,
            warnings=warnings,
        )

        self._metrics[symbol] = metrics
        return metrics

    def get_metrics(self, symbol: str) -> WhaleMetrics | None:
        """Dernières métriques whales calculées."""
        return self._metrics.get(symbol)

    def get_whale_signal(self, symbol: str) -> str:
        """
        Signal directionnel basé sur l'activité whale.

        Returns:
            bullish | bearish | neutral
        """
        metrics = self.get_metrics(symbol)
        if not metrics:
            return "neutral"

        if metrics.whale_confidence > 0.3 and metrics.accumulation_score > 60:
            return "bullish"
        elif metrics.whale_confidence < -0.3 and metrics.distribution_score > 60:
            return "bearish"

        return "neutral"
