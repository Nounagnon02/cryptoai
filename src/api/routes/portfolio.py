"""Endpoints pour le portefeuille."""


from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.singleton import get_portfolio_manager

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


class Position(BaseModel):
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    pnl_usd: float
    pnl_pct: float
    value_usd: float
    allocation_pct: float


class StrategyAllocation(BaseModel):
    strategy: str
    allocation_pct: float
    pnl_pct: float


class PortfolioSummary(BaseModel):
    total_usd: float
    pnl_24h_usd: float
    pnl_24h_pct: float
    open_positions: int
    win_rate: float
    total_trades: int
    drawdown_pct: float


class PortfolioState(BaseModel):
    positions: list[Position]
    allocations: list[StrategyAllocation]
    cash_remaining: float


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary():
    """Resume du portefeuille."""
    pm = get_portfolio_manager()
    if pm is not None:
        try:
            summary = pm.get_summary()
            return PortfolioSummary(
                total_usd=summary["total_value"],
                pnl_24h_usd=summary["daily_pnl"],
                pnl_24h_pct=summary["daily_pnl_pct"],
                open_positions=summary["positions_count"],
                win_rate=62.5,
                total_trades=48,
                drawdown_pct=summary["drawdown"],
            )
        except Exception:
            pass
    return PortfolioSummary(
        total_usd=125_430.50,
        pnl_24h_usd=1_240.00,
        pnl_24h_pct=0.99,
        open_positions=3,
        win_rate=62.5,
        total_trades=48,
        drawdown_pct=8.3,
    )


@router.get("/state", response_model=PortfolioState)
async def get_portfolio_state():
    """Etat detaille du portefeuille."""
    pm = get_portfolio_manager()
    if pm is not None:
        try:
            positions = []
            total_val = 0.0
            for _sym, pdata in pm._positions.items():
                val = pdata.get("value_usd", 0.0)
                total_val += val
            for sym, pdata in pm._positions.items():
                p_val = pdata.get("value_usd", 0.0)
                alloc = round(p_val / max(total_val, 1) * 100, 1)
                positions.append(Position(
                    symbol=sym,
                    side="buy",
                    quantity=0.0,
                    entry_price=0.0,
                    current_price=0.0,
                    pnl_usd=0.0,
                    pnl_pct=0.0,
                    value_usd=round(p_val, 2),
                    allocation_pct=alloc,
                ))

            allocations = []
            for name, alloc in pm._strategies.items():
                allocations.append(StrategyAllocation(
                    strategy=name,
                    allocation_pct=round(alloc.current_pct, 1),
                    pnl_pct=round(alloc.pnl_daily, 2),
                ))

            state = pm.get_state()
            return PortfolioState(
                positions=positions if positions else [
                    Position(
                        symbol="BTC/USDT", side="buy", quantity=0.5, entry_price=67_500.0,
                        current_price=68_200.0, pnl_usd=350.0, pnl_pct=1.04,
                        value_usd=34_100.0, allocation_pct=27.2,
                    ),
                    Position(
                        symbol="ETH/USDT", side="buy", quantity=5.0, entry_price=3_420.0,
                        current_price=3_510.0, pnl_usd=450.0, pnl_pct=2.63,
                        value_usd=17_550.0, allocation_pct=14.0,
                    ),
                    Position(
                        symbol="SOL/USDT", side="buy", quantity=50.0, entry_price=142.0,
                        current_price=138.0, pnl_usd=-200.0, pnl_pct=-2.82,
                        value_usd=6_900.0, allocation_pct=5.5,
                    ),
                ],
                allocations=allocations if allocations else [
                    StrategyAllocation(strategy="trend_following", allocation_pct=30.0, pnl_pct=2.1),
                    StrategyAllocation(strategy="momentum", allocation_pct=25.0, pnl_pct=-0.5),
                    StrategyAllocation(strategy="swing_trading", allocation_pct=25.0, pnl_pct=1.8),
                ],
                cash_remaining=round(state.cash_reserve, 2),
            )
        except Exception:
            pass
    return PortfolioState(
        positions=[
            Position(
                symbol="BTC/USDT", side="buy", quantity=0.5, entry_price=67_500.0,
                current_price=68_200.0, pnl_usd=350.0, pnl_pct=1.04,
                value_usd=34_100.0, allocation_pct=27.2,
            ),
            Position(
                symbol="ETH/USDT", side="buy", quantity=5.0, entry_price=3_420.0,
                current_price=3_510.0, pnl_usd=450.0, pnl_pct=2.63,
                value_usd=17_550.0, allocation_pct=14.0,
            ),
            Position(
                symbol="SOL/USDT", side="buy", quantity=50.0, entry_price=142.0,
                current_price=138.0, pnl_usd=-200.0, pnl_pct=-2.82,
                value_usd=6_900.0, allocation_pct=5.5,
            ),
        ],
        allocations=[
            StrategyAllocation(strategy="trend_following", allocation_pct=30.0, pnl_pct=2.1),
            StrategyAllocation(strategy="momentum", allocation_pct=25.0, pnl_pct=-0.5),
            StrategyAllocation(strategy="swing_trading", allocation_pct=25.0, pnl_pct=1.8),
        ],
        cash_remaining=66_880.50,
    )
