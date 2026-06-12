"""
Agrégateur d'actualités crypto.

Collecte et normalise les articles depuis multiples sources :
- Flux RSS (CoinDesk, CoinTelegraph, Decrypt)
- APIs (NewsAPI, CryptoCompare)
- Twitter/X (via API ou scraping)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class NewsArticle:
    """Article d'actualité normalisé."""

    id: str
    source: str  # coindesk, cointelegraph, cryptocompare, twitter, etc.
    title: str
    content: str
    url: str
    published_at: float  # Timestamp UNIX
    symbols: list[str] = field(default_factory=list)  # Actifs mentionnés (BTC, ETH...)
    author: str | None = None
    category: str = "general"  # general, regulation, technology, market, adoption
    language: str = "en"
    engagement: int = 0  # Likes/retweets/shares


class NewsAggregator:
    """
    Agrège les actualités crypto depuis multiples sources.

    Note : Version avec collecte simulée pour le développement.
    En production, connecter aux APIs réelles.
    """

    # Sources supportées
    SOURCES = {
        "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "cointelegraph": "https://cointelegraph.com/rss",
        "decrypt": "https://decrypt.co/feed",
        "cryptocompare": "https://min-api.cryptocompare.com/news/v1/list",
    }

    def __init__(self) -> None:
        self._articles: dict[str, list[NewsArticle]] = {}
        self._latest_fetch: dict[str, float] = {}

    async def fetch_latest(
        self,
        symbols: list[str] | None = None,
        sources: list[str] | None = None,
        max_age_hours: int = 24,
    ) -> list[NewsArticle]:
        """
        Récupère les dernières actualités.

        Args:
            symbols: Filtrer par actifs mentionnés (ex: ["BTC", "ETH"])
            sources: Sources à interroger (toutes si None)
            max_age_hours: Âge maximum des articles

        Returns:
            Liste des articles récents
        """
        try:
            articles = await self._fetch_from_sources(sources)
        except Exception:
            # Fallback : retourner le cache
            articles = self._get_cached_articles(symbols, max_age_hours)

        # Filtrer par symboles
        if symbols:
            articles = [
                a for a in articles
                if any(s.upper() in [sym.upper() for sym in a.symbols] for s in symbols)
            ]

        # Stocker dans le cache
        for article in articles:
            if article.symbols:
                primary_sym = article.symbols[0]
                if primary_sym not in self._articles:
                    self._articles[primary_sym] = []
                self._articles[primary_sym].append(article)

                # Limiter le cache
                if len(self._articles[primary_sym]) > 500:
                    self._articles[primary_sym] = self._articles[primary_sym][-500:]

        return articles[:50]

    async def _fetch_from_sources(
        self,
        _sources: list[str] | None = None,
    ) -> list[NewsArticle]:
        """
        Collecte depuis les sources configurées.

        Actuellement simulé. En production :
        - aiohttp pour les requêtes HTTP
        - Parsing RSS avec feedparser
        - APIs dédiées (NewsAPI, CryptoCompare)
        """
        # Simuler des articles pour le développement
        return [
            NewsArticle(
                id="sim-1",
                source="cryptocompare",
                title="Bitcoin shows strong momentum above $60,000",
                content="Bitcoin continues to show strong momentum...",
                url="https://example.com/news/1",
                published_at=datetime.now(UTC).timestamp() - 3600,
                symbols=["BTC", "ETH"],
                category="market",
            ),
            NewsArticle(
                id="sim-2",
                source="coindesk",
                title="Ethereum layer-2 activity reaches all-time high",
                content="Ethereum scaling solutions are seeing...",
                url="https://example.com/news/2",
                published_at=datetime.now(UTC).timestamp() - 7200,
                symbols=["ETH"],
                category="technology",
            ),
        ]

    def _get_cached_articles(
        self,
        symbols: list[str] | None,
        max_age_hours: int,
    ) -> list[NewsArticle]:
        """Récupère les articles en cache."""
        cutoff = datetime.now(UTC).timestamp() - max_age_hours * 3600
        articles: list[NewsArticle] = []

        if symbols:
            for sym in symbols:
                cached = self._articles.get(sym, [])
                articles.extend(a for a in cached if a.published_at > cutoff)
        else:
            for sym_articles in self._articles.values():
                articles.extend(a for a in sym_articles if a.published_at > cutoff)

        return sorted(articles, key=lambda a: a.published_at, reverse=True)

    def get_articles_for_symbol(
        self,
        symbol: str,
        limit: int = 20,
        max_age_hours: int = 48,
    ) -> list[NewsArticle]:
        """Récupère les articles en cache pour un actif."""
        cutoff = datetime.now(UTC).timestamp() - max_age_hours * 3600
        articles = [
            a for a in self._articles.get(symbol, [])
            if a.published_at > cutoff
        ]
        return sorted(articles, key=lambda a: a.published_at, reverse=True)[:limit]
