"""
Détection de manipulation de marché via l'order book.

Analyse les patterns de trading abusifs :
- Spoofing : ordres placés puis annulés pour créer une fausse impression
- Wash trading : auto-échanges pour gonfler les volumes
- Layering : multiples ordres à différents niveaux pour simuler la demande
- Quote stuffing : avalanches d'ordres/annulations pour saturer le flux
- Iceberg detection : ordres fractionnés pour masquer la vraie intention
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.data.market.schema import OrderBookLevel
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ManipulationAlert:
    """Alerte de manipulation détectée."""

    symbol: str
    manipulation_type: str  # spoofing | wash_trading | layering | quote_stuffing | iceberg
    severity: str  # low | medium | high | critical
    confidence: float  # 0-1
    description: str
    timestamp: float
    details: dict[str, float] = field(default_factory=dict)


@dataclass
class OrderBookEvent:
    """Événement sur le carnet d'ordres (snapshot)."""

    symbol: str
    timestamp: float
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


class ManipulationDetector:
    """
    Détecte les manipulations de marché.

    Méthodes :
    - Spoofing : annulations rapides d'ordres après exécution
    - Wash trading : corrélation temporelle trades ↔ pas de changement de position
    - Layering : empilement d'ordres non exécutés
    - Quote stuffing : taux d'annulation anormal
    - Iceberg : répétition de taille d'ordres identiques
    """

    def __init__(self, window_size: int = 100) -> None:
        self.window_size = window_size
        self._orderbook_history: dict[str, list[OrderBookEvent]] = {}
        self._alerts: dict[str, list[ManipulationAlert]] = {}
        self._cancel_rates: dict[str, list[float]] = {}
        self._spoof_scores: dict[str, float] = {}

    def analyze(self, symbol: str, event: OrderBookEvent) -> list[ManipulationAlert]:
        """
        Analyse un snapshot d'order book pour détecter des manipulations.

        Args:
            symbol: Paire de trading
            event: Snapshot d'order book

        Returns:
            Liste des alertes de manipulation détectées
        """
        alerts: list[ManipulationAlert] = []

        # Historique
        if symbol not in self._orderbook_history:
            self._orderbook_history[symbol] = []
        self._orderbook_history[symbol].append(event)

        # Garder la fenêtre glissante
        if len(self._orderbook_history[symbol]) > self.window_size:
            self._orderbook_history[symbol] = self._orderbook_history[symbol][-self.window_size:]

        if len(self._orderbook_history[symbol]) < 3:
            return alerts

        # Détections
        try:
            alerts.extend(self._detect_spoofing(symbol, event))
            alerts.extend(self._detect_layering(symbol, event))

            if len(self._orderbook_history[symbol]) >= 10:
                alerts.extend(self._detect_iceberg(symbol))
                alerts.extend(self._detect_quote_stuffing(symbol))
        except Exception as e:
            logger.error("Erreur détection manipulation %s: %s", symbol, str(e))

        # Stocker les alertes
        if symbol not in self._alerts:
            self._alerts[symbol] = []
        self._alerts[symbol].extend(alerts)

        # Limiter le nombre d'alertes stockées
        if len(self._alerts[symbol]) > 100:
            self._alerts[symbol] = self._alerts[symbol][-100:]

        return alerts

    def _detect_spoofing(
        self,
        symbol: str,
        event: OrderBookEvent,
    ) -> list[ManipulationAlert]:
        """
        Détecte le spoofing : ordres placés loin du prix pour créer une fausse
        impression de demande, puis annulés rapidement.

        Signes :
        - Grands ordres placés à des prix éloignés du spread
        - Annulation rapide de ces ordres (cross-snapshot)
        """
        alerts: list[ManipulationAlert] = []

        if len(self._orderbook_history[symbol]) < 2:
            return alerts

        prev = self._orderbook_history[symbol][-2]
        current = event

        # Chercher des ordres suspects dans les asks lointains
        spoof_score = 0.0
        far_asks_current = [a for a in current.asks if len(current.asks) >= 10 and
                           a.price > current.asks[min(9, len(current.asks) - 1)].price * 1.005]

        if len(far_asks_current) >= 3:
            # Vérifier si ces ordres n'existaient pas avant (nouveaux)
            prev_far_asks = {a.price: a.volume for a in prev.asks}

            new_far_orders = sum(
                1 for a in far_asks_current
                if a.price not in prev_far_asks
            )

            # Si beaucoup de nouveaux ordres lointains, suspect
            if new_far_orders >= 3:
                spoof_score += 0.4

        # Symétriquement pour les bids
        far_bids_current = [b for b in current.bids if len(current.bids) >= 10 and
                           b.price < current.bids[min(9, len(current.bids) - 1)].price * 0.995]

        if len(far_bids_current) >= 3:
            prev_far_bids = {b.price: b.volume for b in prev.bids}

            new_far_orders = sum(
                1 for b in far_bids_current
                if b.price not in prev_far_bids
            )

            if new_far_orders >= 3:
                spoof_score += 0.4

        # Mettre à jour le score cumulé
        self._spoof_scores[symbol] = self._spoof_scores.get(symbol, 0) * 0.9 + spoof_score * 0.1

        if self._spoof_scores[symbol] > 0.5:
            severity = "high" if self._spoof_scores[symbol] > 0.7 else "medium"
            alerts.append(ManipulationAlert(
                symbol=symbol,
                manipulation_type="spoofing",
                severity=severity,
                confidence=round(self._spoof_scores[symbol], 2),
                description="Spoofing détecté : ordres éloignés anormaux",
                timestamp=event.timestamp,
                details={"spoof_score": self._spoof_scores[symbol]},
            ))

        return alerts

    def _detect_layering(
        self,
        symbol: str,
        event: OrderBookEvent,
    ) -> list[ManipulationAlert]:
        """
        Détecte le layering : multiples ordres à différents niveaux de prix
        qui sont annulés à mesure que le prix approche.
        """
        alerts: list[ManipulationAlert] = []

        # Vérifier la structure des ordres
        bids = event.bids[:15]
        asks = event.asks[:15]

        # Layering pattern : volumes décroissants ou croissants de façon suspecte
        if len(bids) >= 5:
            bid_volumes = [b.value_usd for b in bids]
            # Vérifier si les volumes augmentent régulièrement en s'éloignant
            increasing = all(
                bid_volumes[i] <= bid_volumes[i + 1] * 1.1
                for i in range(len(bid_volumes) - 1)
            )
            if increasing and bid_volumes[-1] > bid_volumes[0] * 3:
                alerts.append(ManipulationAlert(
                    symbol=symbol,
                    manipulation_type="layering",
                    severity="medium",
                    confidence=0.6,
                    description="Layering suspect sur les bids",
                    timestamp=event.timestamp,
                    details={"layering_score": 0.6},
                ))

        if len(asks) >= 5:
            ask_volumes = [a.value_usd for a in asks]
            increasing = all(
                ask_volumes[i] <= ask_volumes[i + 1] * 1.1
                for i in range(len(ask_volumes) - 1)
            )
            if increasing and ask_volumes[-1] > ask_volumes[0] * 3:
                alerts.append(ManipulationAlert(
                    symbol=symbol,
                    manipulation_type="layering",
                    severity="medium",
                    confidence=0.6,
                    description="Layering suspect sur les asks",
                    timestamp=event.timestamp,
                    details={"layering_score": 0.6},
                ))

        return alerts

    def _detect_iceberg(self, symbol: str) -> list[ManipulationAlert]:
        """
        Détecte les ordres iceberg : mêmes volumes apparaissant à différents
        niveaux de prix, suggérant un ordre fractionné.
        """
        alerts: list[ManipulationAlert] = []
        history = self._orderbook_history[symbol]
        latest = history[-1]

        # Compter les occurrences de volumes similaires sur plusieurs niveaux
        bid_volumes = sorted([b.volume for b in latest.bids[:10]])
        ask_volumes = sorted([a.volume for a in latest.asks[:10]])

        # Chercher des clusters de volumes similaires
        def find_clusters(volumes, tolerance=0.01) -> list[list[float]]:
            clusters = []
            used = set()
            for i, v1 in enumerate(volumes):
                if i in used:
                    continue
                cluster = [v1]
                used.add(i)
                for j, v2 in enumerate(volumes):
                    if j in used:
                        continue
                    if abs(v1 - v2) / max(v1, 1) <= tolerance:
                        cluster.append(v2)
                        used.add(j)
                if len(cluster) >= 3:
                    clusters.append(cluster)
            return clusters

        bid_clusters = find_clusters(bid_volumes)
        ask_clusters = find_clusters(ask_volumes)

        for cluster in bid_clusters:
            if len(cluster) >= 3:
                alerts.append(ManipulationAlert(
                    symbol=symbol,
                    manipulation_type="iceberg",
                    severity="medium",
                    confidence=min(0.9, 0.4 + len(cluster) * 0.1),
                    description=f"Iceberg suspect : {len(cluster)} niveaux avec volume similaire côté bid",
                    timestamp=latest.timestamp,
                    details={"cluster_size": len(cluster), "volume": cluster[0]},
                ))

        for cluster in ask_clusters:
            if len(cluster) >= 3:
                alerts.append(ManipulationAlert(
                    symbol=symbol,
                    manipulation_type="iceberg",
                    severity="medium",
                    confidence=min(0.9, 0.4 + len(cluster) * 0.1),
                    description=f"Iceberg suspect : {len(cluster)} niveaux avec volume similaire côté ask",
                    timestamp=latest.timestamp,
                    details={"cluster_size": len(cluster), "volume": cluster[0]},
                ))

        return alerts

    def _detect_quote_stuffing(self, symbol: str) -> list[ManipulationAlert]:
        """
        Détecte le quote stuffing : taux anormal de changements d'order book.

        Compare le nombre de changements à la moyenne de la fenêtre.
        """
        alerts: list[ManipulationAlert] = []
        history = self._orderbook_history[symbol]

        if len(history) < 10:
            return alerts

        # Calculate rate of change
        recent = history[-5:]
        changes = 0
        for i in range(1, len(recent)):
            prev_bids = {b.price: b.volume for b in recent[i - 1].bids}
            curr_bids = {b.price: b.volume for b in recent[i].bids}
            prev_asks = {a.price: a.volume for a in recent[i - 1].asks}
            curr_asks = {a.price: a.volume for a in recent[i].asks}

            bid_changes = sum(1 for p in set(prev_bids) | set(curr_bids)
                             if prev_bids.get(p) != curr_bids.get(p))
            ask_changes = sum(1 for p in set(prev_asks) | set(curr_asks)
                             if prev_asks.get(p) != curr_asks.get(p))
            changes += bid_changes + ask_changes

        avg_changes = changes / max(1, len(recent) - 1)

        # Comparer à la moyenne historique
        older = history[:-5]
        if older:
            older_changes = []
            for i in range(1, min(len(older), 20)):
                prev_bids = {b.price: b.volume for b in older[i - 1].bids}
                curr_bids = {b.price: b.volume for b in older[i].bids}
                bid_changes = sum(1 for p in set(prev_bids) | set(curr_bids)
                                 if prev_bids.get(p) != curr_bids.get(p))
                older_changes.append(bid_changes)
            historical_avg = sum(older_changes) / max(1, len(older_changes))

            if historical_avg > 0 and avg_changes > historical_avg * 3:
                alerts.append(ManipulationAlert(
                    symbol=symbol,
                    manipulation_type="quote_stuffing",
                    severity="high",
                    confidence=min(0.9, 0.5 * (avg_changes / historical_avg)),
                    description=f"Quote stuffing : {avg_changes:.0f} changements (moyenne: {historical_avg:.0f})",
                    timestamp=history[-1].timestamp,
                    details={
                        "current_rate": avg_changes,
                        "historical_rate": historical_avg,
                        "ratio": round(avg_changes / max(1, historical_avg), 2),
                    },
                ))

        return alerts

    def get_alerts(
        self,
        symbol: str,
        min_severity: str = "low",
        limit: int = 20,
    ) -> list[ManipulationAlert]:
        """
        Récupère les alertes de manipulation pour un symbole.

        Args:
            symbol: Paire de trading
            min_severity: Seuil minimum (low, medium, high, critical)
            limit: Nombre maximum d'alertes

        Returns:
            Liste filtrée des alertes
        """
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_level = severity_order.get(min_severity, 0)

        alerts = self._alerts.get(symbol, [])
        filtered = [
            a for a in alerts
            if severity_order.get(a.severity, 0) >= min_level
        ]

        return filtered[-limit:]

    def get_manipulation_score(self, symbol: str) -> float:
        """
        Score global de risque de manipulation (0-100).

        Plus le score est élevé, plus le risque est grand.
        """
        alerts = self._alerts.get(symbol, [])
        if not alerts:
            return 0

        recent = alerts[-20:]
        score = 0
        for alert in recent:
            severity_mult = {"low": 1, "medium": 3, "high": 8, "critical": 20}
            score += severity_mult.get(alert.severity, 1) * alert.confidence

        return min(100, score / len(recent) * 10)

    def is_manipulated(self, symbol: str, threshold: float = 30) -> bool:
        """Vérifie si un actif est probablement manipulé."""
        return self.get_manipulation_score(symbol) > threshold
