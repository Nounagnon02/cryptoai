"""Tests for RiskManager."""
from __future__ import annotations

import pytest

from src.risk.manager import RiskLimits, RiskManager


@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager()


@pytest.fixture
def conservative_limits() -> RiskLimits:
    return RiskLimits(
        max_position_pct=10.0,
        max_daily_loss_pct=3.0,
        stop_loss_atr_multiplier=3.0,
        volatility_scaling=True,
        max_volatility_position=0.03,
    )


class TestRiskManagerAssessTrade:
    """Tests for assess_trade() method."""

    def test_assess_trade_valid_params(self, risk_manager: RiskManager) -> None:
        """Test trade assessment completes with valid parameters."""
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
            atr=1000.0,
            volatility=0.4,
        )
        assert result.symbol == "BTC/USDT"
        assert result.side == "buy"
        assert result.stop_loss_price is not None
        assert result.stop_loss_price < 50000.0  # Long SL below entry
        assert result.take_profit_price is not None
        assert result.take_profit_price > 50000.0  # Long TP above entry
        assert result.recommended_size > 0
        assert 0 <= result.score <= 100

    def test_assess_trade_atr_based_sizing(self, risk_manager: RiskManager) -> None:
        """Test ATR-based stop loss calculation."""
        entry = 50000.0
        atr_val = 2000.0  # Large ATR
        result = risk_manager.assess_trade(
            symbol="ETH/USDT",
            side="buy",
            entry_price=entry,
            portfolio_value=100000.0,
            atr=atr_val,
        )
        # ATR multiple = 2.0, so SL distance = 4000, SL price = 46000
        expected_sl = entry - atr_val * 2.0
        assert result.stop_loss_type == "atr"
        assert result.stop_loss_price == pytest.approx(expected_sl, rel=0.01)

    def test_assess_trade_volatility_based_sizing(
        self, risk_manager: RiskManager
    ) -> None:
        """Test volatility-based position sizing reduces size in high vol."""
        # First with low volatility
        low_vol = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
            atr=500.0,
            volatility=0.2,
        )
        # Then with high volatility
        high_vol = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
            atr=500.0,
            volatility=0.8,
        )
        # High volatility should reduce position size
        assert high_vol.recommended_size <= low_vol.recommended_size


class TestRiskManagerDailyLoss:
    """Tests for daily loss limits."""

    def test_check_daily_loss_no_losses(self, risk_manager: RiskManager) -> None:
        """Test daily loss check passes with no losses recorded."""
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
        )
        assert result.checks_passed is True
        # Score should be a reasonable value when everything is fine
        assert result.score >= 30

    def test_check_daily_loss_exceeded(self, risk_manager: RiskManager) -> None:
        """Test trade is blocked when daily loss limit is exceeded."""
        # Record a large loss that exceeds the daily limit (5%)
        risk_manager.record_trade_result(symbol="BTC/USDT", pnl=-8000.0)  # -8% of 100k
        risk_manager._current_portfolio_value = 92000.0

        result = risk_manager.assess_trade(
            symbol="ETH/USDT",
            side="buy",
            entry_price=3000.0,
            portfolio_value=92000.0,
        )
        assert result.checks_passed is False
        assert result.score == 0
        assert any("perte" in f.lower() for f in result.failed_checks)


class TestRiskManagerMarketCrash:
    """Tests for market crash detection."""

    def test_check_market_crash_detection(self, risk_manager: RiskManager) -> None:
        """Test market crash detection via drawdown threshold."""
        # Set portfolio to have dropped significantly from peak
        risk_manager._current_portfolio_value = 70000.0
        risk_manager._peak_portfolio_value = 100000.0  # Peak was 100k, now 70k = 30% DD
        # Max drawdown limit is 25%

        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=70000.0,
        )
        assert result.checks_passed is False
        assert result.score == 0

    def test_no_market_crash_within_limits(self, risk_manager: RiskManager) -> None:
        """Test trading is allowed when drawdown is within limits."""
        # 10% drawdown should be fine (limit is 25%)
        risk_manager._current_portfolio_value = 90000.0
        risk_manager._peak_portfolio_value = 100000.0

        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=90000.0,
        )
        assert result.checks_passed is True


class TestRiskManagerStopLoss:
    """Tests for stop loss calculations."""

    def test_atr_stop_loss_long(self, risk_manager: RiskManager) -> None:
        """Test ATR-based stop loss for long position."""
        entry = 50000.0
        atr_val = 800.0
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=entry,
            portfolio_value=100000.0,
            atr=atr_val,
        )
        expected_sl = entry - atr_val * risk_manager.limits.stop_loss_atr_multiplier
        assert result.stop_loss_price == pytest.approx(expected_sl, rel=0.01)
        assert result.stop_loss_type == "atr"

    def test_atr_stop_loss_short(self, risk_manager: RiskManager) -> None:
        """Test ATR-based stop loss for short position."""
        entry = 50000.0
        atr_val = 800.0
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="sell",
            entry_price=entry,
            portfolio_value=100000.0,
            atr=atr_val,
        )
        # Short SL is above entry
        expected_sl = entry + atr_val * risk_manager.limits.stop_loss_atr_multiplier
        assert result.stop_loss_price == pytest.approx(expected_sl, rel=0.01)
        assert result.stop_loss_type == "atr"


class TestRiskManagerKellyCriterion:
    """Tests for Kelly Criterion position sizing."""

    def test_kelly_criterion_sizing(self, risk_manager: RiskManager) -> None:
        """Test Kelly Criterion position sizing formula."""
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
            atr=1000.0,
        )
        # Kelly percentage should be reasonable (between 0 and 100)
        assert 0 <= result.kelly_percentage <= 100
        # Recommended size should not exceed max size
        assert result.recommended_size <= result.max_size
        # Kelly fraction defaults to 0.25 so kelly_pct <= 0.25 * 100 = 25
        assert result.kelly_percentage <= 25.0

    def test_kelly_with_zero_atr(self, risk_manager: RiskManager) -> None:
        """Test Kelly with zero ATR (falls back to fixed SL)."""
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
            atr=0.0,
        )
        assert result.stop_loss_type == "fixed"
        assert result.stop_loss_price is not None
        assert result.recommended_size > 0


class TestRiskManagerEdgeCases:
    """Tests for edge cases."""

    def test_negative_portfolio_value(self, risk_manager: RiskManager) -> None:
        """Test handling of negative portfolio value."""
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=-1000.0,
            atr=500.0,
        )
        # Should not crash, assessments should have valid values
        assert result.symbol == "BTC/USDT"

    def test_missing_parameters(self, risk_manager: RiskManager) -> None:
        """Test assessment with minimal parameters (no atr, no volatility)."""
        result = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=100000.0,
        )
        assert result.stop_loss_price is not None
        assert result.recommended_size > 0
        assert result.score >= 0

    def test_portfolio_value_update_and_get_state(
        self, risk_manager: RiskManager
    ) -> None:
        """Test that assess_trade updates portfolio value and get_state works."""
        risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            portfolio_value=200000.0,
        )
        state = risk_manager.get_state()
        assert state["portfolio"]["current_value"] == 200000.0
