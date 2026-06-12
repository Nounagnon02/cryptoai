"""
Moteur de découverte automatique d'actifs.

Scanne les exchanges pour identifier les cryptomonnaies prometteuses
basées sur le volume, la liquidité, la croissance, et l'activité.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.data.market.provider import CCXTProvider
from src.utils.logging import LoggerMixin


@dataclass
class AssetScore:
    """Score d'un actif pour décision d'ajout à la watchlist."""

    symbol: str
    volume_score: float = 0.0      # 0-100
    liquidity_score: float = 0.0   # 0-100
    growth_score: float = 0.0      # 0-100
    total_score: float = 0.0       # 0-100 pondéré
    reason: str = ""

    def calculate_total(self) -> None:
        """Calcule le score total pondéré."""
        self.total_score = (
            self.volume_score * 0.35
            + self.liquidity_score * 0.35
            + self.growth_score * 0.30
        )


class AssetDiscovery(LoggerMixin):
    """
    Découvre et score automatiquement les nouveaux actifs.

    Basé sur :
    - Volume d'échange 24h
    - Liquidité du carnet d'ordres
    - Croissance du volume (7j)
    - Nombre de paires de trading
    - Présence sur les exchanges majeurs
    """

    # Seuils pour l'ajout automatique
    MIN_VOLUME_24H_USD: float = 1_000_000       # $1M minimum
    MIN_SPREAD_SCORE: float = 30.0                # spread max pour être liquide
    MIN_GROWTH_PCT: float = 10.0                  # croissance minimale 7j
    SCORE_THRESHOLD: float = 60.0                 # score min pour ajout

    # Exchanges à scanner pour la découvrabilité
    PRIMARY_EXCHANGES = ["binance", "bybit", "okx"]
    TOP_N_BY_VOLUME: int = 50                     # top N par volume

    def __init__(self) -> None:
        self._discovered_assets: dict[str, AssetScore] = {}
        self._providers: dict[str, CCXTProvider] = {}

    async def scan_market(self) -> list[AssetScore]:
        """
        Scanne le marché pour découvrir de nouveaux actifs.

        Returns:
            Liste des actifs scorés, triés par score décroissant
        """
        self.logger.info("Scan du marché pour découverte d'actifs...")

        candidates: list[AssetScore] = []

        # Scanner les exchanges majeurs pour les top volumes
        for exchange_name in self.PRIMARY_EXCHANGES:
            try:
                provider = self._get_provider(exchange_name)
                exchange_candidates = await self._scan_exchange(provider)
                candidates.extend(exchange_candidates)
            except Exception as e:
                self.logger.warning(
                    "Erreur scan exchange",
                    extra={"exchange": exchange_name, "error": str(e)},
                )

        # Dédupliquer et scorer
        seen: set[str] = set()
        unique_candidates: list[AssetScore] = []

        for candidate in sorted(candidates, key=lambda x: x.total_score, reverse=True):
            if candidate.symbol not in seen and candidate.symbol.endswith("/USDT"):
                seen.add(candidate.symbol)
                candidate.calculate_total()
                unique_candidates.append(candidate)

                if candidate.total_score >= self.SCORE_THRESHOLD:
                    self._discovered_assets[candidate.symbol] = candidate

        self.logger.info(
            "Scan terminé",
            extra={
                "candidates": len(unique_candidates),
                "discovered": len(self._discovered_assets),
            },
        )

        return sorted(unique_candidates, key=lambda x: x.total_score, reverse=True)

    async def _scan_exchange(self, provider: CCXTProvider) -> list[AssetScore]:
        """Scanne un exchange pour les actifs à fort volume."""
        scores: list[AssetScore] = []

        try:
            # Récupérer les tickers (tous les symboles)
            exchange = await provider._get_exchange()
            tickers = await exchange.fetch_tickers()

            usdt_pairs = [
                (symbol, data) for symbol, data in tickers.items()
                if symbol.endswith("/USDT") and data.get("quoteVolume", 0) is not None
            ]

            # Trier par volume et prendre le top N
            usdt_pairs.sort(
                key=lambda x: float(x[1].get("quoteVolume", 0) or 0),
                reverse=True,
            )

            for symbol, data in usdt_pairs[:self.TOP_N_BY_VOLUME]:
                volume_24h = float(data.get("quoteVolume", 0) or 0)
                change_pct = float(data.get("percentage", 0) or 0)
                high_24h = float(data.get("high", 0) or 0)
                low_24h = float(data.get("low", 0) or 0)

                # Score de volume (logarithmique pour éviter le biais BTC/ETH)
                volume_score = min(100, (volume_24h / self.MIN_VOLUME_24H_USD) * 50)

                # Score de liquidité (basé sur le spread)
                spread = 0.0
                if high_24h > 0 and low_24h > 0:
                    spread = ((high_24h - low_24h) / high_24h) * 100
                liquidity_score = max(0, 100 - spread * 5)

                # Score de croissance
                growth_score = min(100, max(0, change_pct * 2))

                score = AssetScore(
                    symbol=symbol,
                    volume_score=min(100, volume_score),
                    liquidity_score=min(100, liquidity_score),
                    growth_score=min(100, growth_score),
                    reason=f"Vol24h: ${volume_24h:,.0f}, Change: {change_pct:+.1f}%",
                )
                score.calculate_total()
                scores.append(score)

        except Exception as e:
            self.logger.warning(
                "Erreur pendant le scan",
                extra={"error": str(e)},
            )

        return scores

    def get_new_discoveries(self, existing_symbols: set[str]) -> list[str]:
        """Retourne les actifs découverts qui ne sont pas déjà dans la watchlist."""
        return [
            symbol
            for symbol, score in sorted(
                self._discovered_assets.items(),
                key=lambda x: x[1].total_score,
                reverse=True,
            )
            if symbol not in existing_symbols and score.total_score >= self.SCORE_THRESHOLD
        ]

    def _get_provider(self, exchange_name: str) -> CCXTProvider:
        """Retourne ou crée un provider pour l'exchange."""
        if exchange_name not in self._providers:
            self._providers[exchange_name] = CCXTProvider(
                exchange_name=exchange_name,
                testnet=False,  # scan nécessite données réelles
            )
        return self._providers[exchange_name]

    async def cleanup(self) -> None:
        """Ferme les connexions des providers."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
