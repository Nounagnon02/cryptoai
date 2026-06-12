"""
Modèles de données pour les données de marché.

Utilise Pydantic V2 pour validation et sérialisation automatiques.
Tous les timestamps en UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class OHLCV(BaseModel):
    """Bougie OHLCV — Open, High, Low, Close, Volume."""

    symbol: str = Field(..., description="Paire de trading, ex: BTC/USDT")
    timeframe: str = Field(..., description="Intervalle: 1m, 5m, 1h, 1d...")
    timestamp: datetime = Field(..., description="Timestamp d'ouverture UTC")
    open: float = Field(..., ge=0, description="Prix d'ouverture")
    high: float = Field(..., ge=0, description="Plus haut")
    low: float = Field(..., ge=0, description="Plus bas")
    close: float = Field(..., ge=0, description="Prix de clôture")
    volume: float = Field(..., ge=0, description="Volume échangé")
    trades: int | None = Field(None, ge=0, description="Nombre de trades")
    vwap: float | None = Field(None, description="VWAP de la bougie")

    model_config = {"frozen": True, "extra": "forbid"}

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=UTC) if v.tzinfo is None else v

    @property
    def spread(self) -> float:
        """Spread haut-bas en %."""
        return ((self.high - self.low) / self.low) * 100 if self.low > 0 else 0.0

    @property
    def body(self) -> float:
        """Taille du corps de la bougie."""
        return abs(self.close - self.open)


class Ticker(BaseModel):
    """Données ticker temps réel d'un actif."""

    symbol: str
    bid: float = Field(..., ge=0)
    ask: float = Field(..., ge=0)
    last: float = Field(..., ge=0)
    volume_24h: float = Field(..., ge=0)
    high_24h: float = Field(..., ge=0)
    low_24h: float = Field(..., ge=0)
    change_24h: float = Field(..., description="Changement en %")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def spread_pct(self) -> float:
        """Spread bid-ask en %."""
        if self.ask > 0:
            return ((self.ask - self.bid) / self.ask) * 100
        return 0.0


class Trade(BaseModel):
    """Trade exécuté sur un exchange."""

    id: str
    symbol: str
    price: float
    amount: float
    cost: float = Field(..., description="Valeur totale (price * amount)")
    side: str = Field(..., pattern="^(buy|sell)$")
    timestamp: datetime
    exchange: str = "unknown"
    is_maker: bool | None = None


class OrderBookLevel(BaseModel):
    """Niveau du carnet d'ordres."""

    price: float
    amount: float
    total: float = Field(0, description="Cumulatif")

    @property
    def value_usd(self) -> float:
        return self.price * self.amount


class OrderBook(BaseModel):
    """Snapshot du carnet d'ordres L2."""

    symbol: str
    timestamp: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    exchange: str = "unknown"

    @property
    def spread(self) -> float:
        """Spread bid-ask."""
        if not self.bids or not self.asks:
            return 0.0
        return self.asks[0].price - self.bids[0].price

    @property
    def spread_pct(self) -> float:
        """Spread en %."""
        mid = self.mid_price
        if mid > 0:
            return (self.spread / mid) * 100
        return 0.0

    @property
    def mid_price(self) -> float:
        if self.bids and self.asks:
            return (self.bids[0].price + self.asks[0].price) / 2
        return 0.0

    @property
    def imbalance(self) -> float:
        """
        Déséquilibre du carnet.
        > 0 : pression acheteuse
        < 0 : pression vendeuse
        """
        total_bids = sum(b.amount for b in self.bids)
        total_asks = sum(a.amount for a in self.asks)
        total = total_bids + total_asks
        if total == 0:
            return 0.0
        return (total_bids - total_asks) / total

    @property
    def total_bid_volume(self) -> float:
        return sum(b.value_usd for b in self.bids)

    @property
    def total_ask_volume(self) -> float:
        return sum(a.value_usd for a in self.asks)
