"""
Integration test: Decision → Portfolio → Risk interactions.

Validates how trading decisions flow through the portfolio manager,
risk assessment checks, and circuit breaker protection.
"""

from __future__ import annotations

import pytest

from src.core.decision_engine import ActionType, DecisionMatrix
from src.portfolio.manager import PortfolioManager
from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from src.risk.manager import RiskManager

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def portfolio() -> PortfolioManager:
    """A PortfolioManager initialised with 100k capital."""
    pm = PortfolioManager()
    pm.initialize(100_000.0)
    return pm


@pytest.fixture
def risk_manager() -> RiskManager:
    """A default RiskManager."""
    return RiskManager()


@pytest.fixture
def decision_matrix() -> DecisionMatrix:
    """A fresh DecisionMatrix."""
    return DecisionMatrix()


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """A default CircuitBreaker with standard config."""
    return CircuitBreaker(CircuitBreakerConfig())


# ── Helper: system-level decide with CB guard ─────────────────────


def _decide_with_circuit_breaker(
    cb: CircuitBreaker,
    dm: DecisionMatrix,
    symbol: str,
    score: float,
    direction: str,
    confidence: float,
    strength: float,
    current_price: float = 50000.0,
) -> tuple[bool, object]:
    """
    Simulate the real trading loop's decision gate.

    1. Check the circuit breaker for the symbol.
    2. If blocked (CB open or blacklisted), reject → return HOLD.
    3. Otherwise, delegate to DecisionMatrix.

    Returns (allowed, decision_record).
    """
    if cb.check_symbol(symbol, current_price) is False:
        return False, None

    decision = dm.decide(
        symbol=symbol,
        score=score,
        direction=direction,
        confidence=confidence,
        strength=strength,
    )
    return True, decision


# ── Tests ──────────────────────────────────────────────────────────


class TestDecisionToPortfolio:
    """Decision → PortfolioManager interactions."""

    def test_decision_affects_portfolio(
        self, decision_matrix: DecisionMatrix, portfolio: PortfolioManager
    ) -> None:
        """A buy decision leads to a portfolio position assignment."""
        # Generate a strong buy decision
        decision = decision_matrix.decide(
            symbol="BTC/USDT",
            score=82.0,
            direction="bullish",
            confidence=75.0,
            strength=0.6,
        )

        assert decision.action in (ActionType.STRONG_BUY, ActionType.BUY)
        assert decision.order is not None

        # Simulate the system assigning the position to the portfolio
        portfolio.assign_position(
            symbol=decision.symbol,
            value_usd=decision.order.quantity_usd,
            strategy=decision.order.strategy,
        )

        state = portfolio.get_state()
        assert state.positions_count == 1
        # The assigned value should equal the decision's order size
        assert state.positions_value == decision.order.quantity_usd, (
            f"Portfolio value {state.positions_value} != order size "
            f"{decision.order.quantity_usd}"
        )

    def test_portfolio_state_after_multiple_positions(
        self, portfolio: PortfolioManager
    ) -> None:
        """Adding several positions updates the state correctly."""
        portfolio.assign_position("BTC/USDT", 30_000.0, strategy="momentum")
        portfolio.assign_position("ETH/USDT", 20_000.0, strategy="momentum")
        portfolio.assign_position("SOL/USDT", 10_000.0, strategy="trend_following")

        # Simulate the cash deduction that would happen in production
        positions_value = 30_000.0 + 20_000.0 + 10_000.0
        cash_left = 100_000.0 - positions_value
        portfolio.update_value(100_000.0, cash_left)

        state = portfolio.get_state()
        assert state.positions_count == 3
        assert state.positions_value == 60_000.0
        assert state.cash_reserve == 40_000.0
        assert state.total_value == 100_000.0

        # The portfolio should not require rebalancing after fresh positions
        # (cash reserve is 40% > min_cash_reserve_pct=15%)
        assert state.cash_reserve_pct == 40.0  # 40000 / 100000
        assert state.is_halted is False


class TestRiskValidatesTrades:
    """RiskManager trade validation."""

    def test_risk_validates_trade(self, risk_manager: RiskManager) -> None:
        """
        An oversized position should be rejected by the risk manager.

        With max_position_pct = 25% of 100k = 25k USD, a 50k USD
        suggestion should fail the risk check.
        """
        assessment = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50_000.0,
            portfolio_value=100_000.0,
            position_size_usd=50_000.0,  # exceeds 25% limit → 25k max
        )

        assert assessment.checks_passed is False, (
            f"Oversized trade should be rejected, failed_checks: "
            f"{assessment.failed_checks}"
        )
        assert any("taille" in c.lower() or "size" in c.lower()
                    for c in assessment.failed_checks), (
            f"Expected a position-sizing failure, got: {assessment.failed_checks}"
        )
        assert assessment.score < 100

    def test_risk_approves_safe_trade(self, risk_manager: RiskManager) -> None:
        """
        A small, sensible position should pass the risk check.

        5k USD on a 100k portfolio (5%) is well within limits.
        """
        assessment = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50_000.0,
            portfolio_value=100_000.0,
            position_size_usd=5_000.0,  # well under 25k max
        )

        assert assessment.checks_passed is True, (
            f"Safe trade should be approved, got: {assessment.failed_checks}"
        )
        assert assessment.recommended_size > 0
        assert assessment.stop_loss_price is not None
        assert assessment.stop_loss_price < 50_000.0  # SL below entry for buy
        assert assessment.risk_reward_ratio >= 1.0

    def test_risk_stop_loss_and_take_profit(
        self, risk_manager: RiskManager
    ) -> None:
        """Risk assessment should compute sensible SL/TP levels."""
        assessment = risk_manager.assess_trade(
            symbol="ETH/USDT",
            side="buy",
            entry_price=3_000.0,
            portfolio_value=100_000.0,
            atr=60.0,  # 2% ATR → ATR-based stop loss
            position_size_usd=5_000.0,
        )

        assert assessment.checks_passed is True
        # ATR-based SL: entry - 2 * ATR = 3000 - 120 = 2880, 4% distance
        assert assessment.stop_loss_price is not None
        assert assessment.stop_loss_price < 3_000.0

        # Take profit should be above entry (RR >= 1.5)
        assert assessment.take_profit_price is not None
        assert assessment.take_profit_price > 3_000.0
        assert assessment.risk_reward_ratio >= 1.5

        # Recommended size should be positive
        assert assessment.recommended_size > 0


class TestCircuitBreakerIntegration:
    """CircuitBreaker integration with the decision pipeline."""

    def test_circuit_breaker_blocks_decision(
        self,
        circuit_breaker: CircuitBreaker,
        decision_matrix: DecisionMatrix,
    ) -> None:
        """
        When the circuit breaker is open for a symbol, the system
        should block trading and default to HOLD.
        """
        circuit_breaker.force_open("BTC/USDT", "Simulated flash crash")

        # Verify the CB is actually open
        status = circuit_breaker.get_status()
        assert "BTC/USDT" in status["open_circuits"], (
            "Circuit should be open after force_open"
        )

        # Attempt decision through the gated pipeline
        allowed, decision = _decide_with_circuit_breaker(
            cb=circuit_breaker,
            dm=decision_matrix,
            symbol="BTC/USDT",
            score=85.0,
            direction="bullish",
            confidence=80.0,
            strength=0.7,
        )

        # The CB should block the trade
        assert allowed is False, (
            "Trade should be blocked when circuit is open"
        )
        assert decision is None

        # The CB status reflects the blocked symbol
        symbol_status = circuit_breaker.get_symbol_status("BTC/USDT")
        assert symbol_status["can_trade"] is False
        assert symbol_status["state"] == "open"
        assert symbol_status["is_blacklisted"] is True

    def test_circuit_breaker_allows_when_closed(
        self,
        circuit_breaker: CircuitBreaker,
        decision_matrix: DecisionMatrix,
    ) -> None:
        """
        When the circuit breaker is closed, trading decisions
        flow through normally.
        """
        # CB is closed by default — no force_open called
        status = circuit_breaker.get_status()
        assert status["system_state"] == "closed"

        # A strongly bullish signal should produce a buy
        allowed, decision = _decide_with_circuit_breaker(
            cb=circuit_breaker,
            dm=decision_matrix,
            symbol="BTC/USDT",
            score=82.0,
            direction="bullish",
            confidence=75.0,
            strength=0.6,
        )

        assert allowed is True
        assert decision is not None
        assert decision.action in (ActionType.STRONG_BUY, ActionType.BUY)

        # The symbol is not blacklisted
        symbol_status = circuit_breaker.get_symbol_status("BTC/USDT")
        assert symbol_status["can_trade"] is True
        assert symbol_status["is_blacklisted"] is False

    def test_circuit_breaker_force_open_and_recover(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """A manually opened circuit can be force-closed for recovery."""
        circuit_breaker.force_open("ETH/USDT", "Manual override for test")

        status_before = circuit_breaker.get_status()
        assert "ETH/USDT" in status_before["open_circuits"]

        # Force-close to simulate recovery
        circuit_breaker.force_close("ETH/USDT")

        status_after = circuit_breaker.get_status()
        assert "ETH/USDT" not in status_after["open_circuits"]

        symbol_status = circuit_breaker.get_symbol_status("ETH/USDT")
        assert symbol_status["state"] == "closed"
        assert symbol_status["can_trade"] is True

    def test_circuit_breaker_does_not_affect_other_symbols(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Opening the circuit for one symbol should not block others."""
        circuit_breaker.force_open("BTC/USDT", "BTC crash")

        # BTC should be blocked
        assert circuit_breaker.check_symbol("BTC/USDT", 100.0) is False

        # ETH should still be tradable
        assert circuit_breaker.check_symbol("ETH/USDT", 100.0) is True

        status = circuit_breaker.get_status()
        assert "BTC/USDT" in status["open_circuits"]
        assert "ETH/USDT" not in status["open_circuits"]


class TestPortfolioRiskIntegration:
    """Cross-cutting Portfolio + Risk interactions."""

    def test_risk_aware_portfolio_assignment(
        self,
        portfolio: PortfolioManager,
        risk_manager: RiskManager,
    ) -> None:
        """
        A position that passes risk checks can be assigned to the
        portfolio and is reflected in the state.
        """
        # First, risk-validate the trade
        assessment = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50_000.0,
            portfolio_value=100_000.0,
            position_size_usd=10_000.0,
        )
        assert assessment.checks_passed is True

        # Then assign to portfolio
        portfolio.assign_position(
            symbol="BTC/USDT",
            value_usd=assessment.recommended_size,
            strategy="momentum",
        )

        state = portfolio.get_state()
        assert state.positions_count == 1
        assert state.positions_value == assessment.recommended_size, (
            f"Portfolio value {state.positions_value} != "
            f"recommended size {assessment.recommended_size}"
        )

    def test_oversized_position_rejected_by_both(
        self,
        portfolio: PortfolioManager,
        risk_manager: RiskManager,
    ) -> None:
        """
        An oversized position should be rejected by the risk manager
        AND caught by the portfolio's allocation limits.
        """
        # Risk check should reject
        assessment = risk_manager.assess_trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50_000.0,
            portfolio_value=100_000.0,
            position_size_usd=60_000.0,  # exceeds 25% max_position_pct
        )
        assert assessment.checks_passed is False

        # Portfolio check should also reject
        allowed, violations = portfolio.check_allocation_limits(
            "BTC/USDT", 60_000.0
        )
        assert allowed is False
        assert len(violations) > 0
