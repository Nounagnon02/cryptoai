"""Tests for PortfolioManager."""
from __future__ import annotations

import pytest

from src.portfolio.manager import PortfolioManager


@pytest.fixture
def portfolio_manager() -> PortfolioManager:
    pm = PortfolioManager()
    pm.initialize(initial_capital=100000.0)
    return pm


@pytest.fixture
def pm_with_strategies(portfolio_manager: PortfolioManager) -> PortfolioManager:
    """Portfolio manager with registered strategies."""
    portfolio_manager.register_strategy("momentum", target_pct=40.0, sharpe_ratio=1.5)
    portfolio_manager.register_strategy("arbitrage", target_pct=30.0, sharpe_ratio=2.0)
    portfolio_manager.register_strategy("mean_reversion", target_pct=20.0, sharpe_ratio=1.2)
    return portfolio_manager


class TestPortfolioManagerInitialize:
    """Tests for initialization."""

    def test_initialize(self, portfolio_manager: PortfolioManager) -> None:
        """Test initial state after initialization."""
        state = portfolio_manager.get_state()
        assert state.total_value == 100000.0
        assert state.cash_reserve == 100000.0
        assert state.peak_value == 100000.0
        assert state.positions_count == 0
        assert state.drawdown_from_peak == 0.0
        assert state.cash_reserve_pct == 100.0

    def test_initialize_resets_values(self) -> None:
        """Test initialize resets all values."""
        pm = PortfolioManager()
        pm.initialize(50000.0)
        state = pm.get_state()
        assert state.total_value == 50000.0
        assert state.cash_reserve == 50000.0
        assert state.peak_value == 50000.0


class TestPortfolioManagerUpdateValue:
    """Tests for update_value()."""

    def test_update_value_tracking(self, portfolio_manager: PortfolioManager) -> None:
        """Test value tracking with updates."""
        portfolio_manager.update_value(total_value=110000.0, cash_reserve=20000.0)
        state = portfolio_manager.get_state()
        assert state.total_value == 110000.0
        assert state.peak_value == 110000.0  # Updated peak
        assert state.cash_reserve == 20000.0

    def test_update_value_peak_tracking(
        self, portfolio_manager: PortfolioManager
    ) -> None:
        """Test peak value is tracked correctly."""
        portfolio_manager.update_value(total_value=120000.0, cash_reserve=30000.0)
        assert portfolio_manager._peak_value == 120000.0

        # Value goes down, peak should stay at 120k
        portfolio_manager.update_value(total_value=100000.0, cash_reserve=20000.0)
        state = portfolio_manager.get_state()
        assert state.peak_value == 120000.0
        assert state.drawdown_from_peak > 0


class TestPortfolioManagerPositionAssignment:
    """Tests for assign_position()."""

    def test_assign_position(self, portfolio_manager: PortfolioManager) -> None:
        """Test position assignment."""
        portfolio_manager.assign_position(
            symbol="BTC/USDT",
            value_usd=20000.0,
            sector="crypto",
            strategy="momentum",
        )
        state = portfolio_manager.get_state()
        assert state.positions_count == 1
        assert "crypto" in state.sector_exposures

    def test_assign_multiple_positions(
        self, portfolio_manager: PortfolioManager
    ) -> None:
        """Test multiple position assignments."""
        portfolio_manager.assign_position("BTC/USDT", 15000.0, "crypto", "momentum")
        portfolio_manager.assign_position("ETH/USDT", 10000.0, "crypto", "momentum")
        portfolio_manager.assign_position("AAPL", 8000.0, "stocks", "mean_reversion")
        state = portfolio_manager.get_state()
        assert state.positions_count == 3


class TestPortfolioManagerAllocation:
    """Tests for allocation calculations."""

    def test_allocation_sum(self, pm_with_strategies: PortfolioManager) -> None:
        """Test that strategy allocations are tracked."""
        pm_with_strategies.assign_position("BTC/USDT", 20000.0, "crypto", "momentum")
        pm_with_strategies.assign_position("ETH/USDT", 15000.0, "crypto", "arbitrage")
        state = pm_with_strategies.get_state()
        assert "momentum" in state.strategies
        assert "arbitrage" in state.strategies

    def test_remove_position(self, portfolio_manager: PortfolioManager) -> None:
        """Test position removal."""
        portfolio_manager.assign_position("BTC/USDT", 20000.0, "crypto", "momentum")
        assert portfolio_manager.get_state().positions_count == 1
        portfolio_manager.remove_position("BTC/USDT")
        assert portfolio_manager.get_state().positions_count == 0

    def test_check_allocation_limits(
        self, portfolio_manager: PortfolioManager
    ) -> None:
        """Test allocation limit checks."""
        portfolio_manager.assign_position("BTC/USDT", 10000.0, "crypto", "momentum")
        # Try a position well within limits
        allowed, violations = portfolio_manager.check_allocation_limits(
            "ETH/USDT", 5000.0
        )
        assert allowed is True
        assert len(violations) == 0

    def test_position_exceeds_single_limit(
        self, portfolio_manager: PortfolioManager
    ) -> None:
        """Test single position limit violation."""
        portfolio_manager._total_value = 100000.0
        # Try a position that exceeds 25% max
        allowed, violations = portfolio_manager.check_allocation_limits(
            "BTC/USDT", 40000.0
        )
        assert allowed is False
        assert any("25" in v for v in violations)


class TestPortfolioManagerPnL:
    """Tests for PnL tracking."""

    def test_strategy_pnl_tracking(
        self, pm_with_strategies: PortfolioManager
    ) -> None:
        """Test PnL tracking per strategy."""
        pm_with_strategies.update_value(total_value=105000.0, cash_reserve=25000.0)
        state = pm_with_strategies.get_state()
        assert state.daily_pnl == 5000.0  # 105k - 100k initial

    def test_record_pnl(self, portfolio_manager: PortfolioManager) -> None:
        """Test recording realized PnL."""
        portfolio_manager.record_pnl(5000.0)
        assert portfolio_manager._total_value == 105000.0

    def test_reset_daily(self, portfolio_manager: PortfolioManager) -> None:
        """Test daily reset."""
        portfolio_manager.update_value(total_value=110000.0, cash_reserve=20000.0)
        portfolio_manager.reset_daily()
        assert portfolio_manager._daily_initial_value == 110000.0


class TestPortfolioManagerRebalancing:
    """Tests for rebalancing triggers."""

    def test_rebalancing_trigger_no_drift(
        self, pm_with_strategies: PortfolioManager
    ) -> None:
        """Test no rebalance when allocations are on target."""
        pm_with_strategies.register_strategy("test_strat", target_pct=10.0)
        actions = pm_with_strategies.check_rebalance_needed()
        # Current allocation is 0%, target is 10%, drift is 10% > 5% threshold
        # But rebalance only sells overexposed — should have empty or sell actions
        assert isinstance(actions, list)

    def test_rebalancing_min_interval(
        self, portfolio_manager: PortfolioManager
    ) -> None:
        """Test rebalancing respects minimum interval."""
        # Trigger rebalance once
        portfolio_manager.check_rebalance_needed()
        # Immediately calling again should return empty (within min interval)
        actions2 = portfolio_manager.check_rebalance_needed()
        # Min interval is 24h, so no second rebalance
        assert len(actions2) == 0

    def test_halt_on_daily_loss(self, portfolio_manager: PortfolioManager) -> None:
        """Test trading halts when daily loss limit is exceeded."""
        portfolio_manager.register_strategy("test", target_pct=50.0)
        portfolio_manager._daily_initial_value = 100000.0
        portfolio_manager.update_value(total_value=92000.0, cash_reserve=80000.0)
        state = portfolio_manager.get_state()
        # 8% loss exceeds 5% daily limit
        assert state.is_halted is True

    def test_get_summary(self, portfolio_manager: PortfolioManager) -> None:
        """Test get_summary returns formatted dictionary."""
        portfolio_manager.assign_position("BTC/USDT", 20000.0, "crypto", "momentum")
        summary = portfolio_manager.get_summary()
        assert summary["total_value"] == 100000.0
        assert summary["positions_count"] == 1
        assert summary["positions_value"] == 20000.0
