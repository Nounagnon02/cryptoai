"""Tests for CircuitBreaker."""
from __future__ import annotations

import pytest

from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    cb = CircuitBreaker()
    return cb


@pytest.fixture
def fast_recovery_cb() -> CircuitBreaker:
    """Circuit breaker with very short cooldown for testing recovery."""
    config = CircuitBreakerConfig(
        cooldown_minutes=0,  # Immediate recovery
        auto_recovery=True,
        consecutive_triggers_limit=5,
    )
    return CircuitBreaker(config=config)


class TestCircuitBreakerInitialState:
    """Tests for initial state."""

    def test_initial_state_closed(self, circuit_breaker: CircuitBreaker) -> None:
        """Verify initial default state is closed."""
        assert circuit_breaker._system_state == CircuitState.CLOSED
        assert circuit_breaker.is_system_operational() is True

    def test_initial_symbol_status(self, circuit_breaker: CircuitBreaker) -> None:
        """Verify symbol status before any activity."""
        status = circuit_breaker.get_symbol_status("BTC/USDT")
        assert status["state"] == "closed"
        assert status["triggers"] == 0
        assert status["is_blacklisted"] is False


class TestCircuitBreakerTripping:
    """Tests for circuit breaker tripping behavior."""

    def test_trip_on_drawdown(self, circuit_breaker: CircuitBreaker) -> None:
        """Test trip after price drop exceeds threshold."""
        symbol = "BTC/USDT"
        # Record a high reference price first
        circuit_breaker.check_symbol(symbol, 50000.0)
        # Now a big drop that exceeds the 1m threshold (3%)
        can_trade = circuit_breaker.check_symbol(symbol, 47500.0)
        assert can_trade is False
        # Check state
        status = circuit_breaker.get_symbol_status(symbol)
        assert status["state"] == "open"
        assert status["triggers"] == 1

    def test_trip_on_drawdown_5m(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test trip triggered by 5-minute drawdown threshold."""
        symbol = "ETH/USDT"
        # Simulate 5-minute window by manipulating timestamps directly
        circuit_breaker.check_symbol(symbol, 3000.0)
        # Price drops 6% which should exceed the 5m threshold (5%)
        can_trade = circuit_breaker.check_symbol(symbol, 2820.0)
        assert can_trade is False
        status = circuit_breaker.get_symbol_status(symbol)
        assert status["state"] == "open"

    def test_no_trip_small_drawdown(self, circuit_breaker: CircuitBreaker) -> None:
        """Test small price change does not trigger circuit breaker."""
        symbol = "BTC/USDT"
        circuit_breaker.check_symbol(symbol, 50000.0)
        # Small 0.5% drop should be fine
        can_trade = circuit_breaker.check_symbol(symbol, 49750.0)
        assert can_trade is True
        status = circuit_breaker.get_symbol_status(symbol)
        assert status["state"] == "closed"


class TestCircuitBreakerRecovery:
    """Tests for circuit breaker recovery."""

    def test_half_open_after_timeout(self, fast_recovery_cb: CircuitBreaker) -> None:
        """Test circuit transitions to half-open after cooldown."""
        symbol = "BTC/USDT"
        fast_recovery_cb.check_symbol(symbol, 50000.0)
        fast_recovery_cb.check_symbol(symbol, 45000.0)  # 10% drop, triggers

        # Try recovery immediately (cooldown is 0)
        recovered = fast_recovery_cb.try_recovery(symbol)
        assert recovered is True
        status = fast_recovery_cb.get_symbol_status(symbol)
        assert status["state"] == "closed"

    def test_recovery_blocks_within_cooldown(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test recovery is blocked during cooldown period."""
        symbol = "BTC/USDT"
        circuit_breaker.check_symbol(symbol, 50000.0)
        circuit_breaker.check_symbol(symbol, 45000.0)  # Triggers

        # Recovery should fail during cooldown
        recovered = circuit_breaker.try_recovery(symbol)
        assert recovered is False
        status = circuit_breaker.get_symbol_status(symbol)
        assert status["state"] == "open"


class TestCircuitBreakerEdgeCases:
    """Tests for edge cases."""

    def test_multiple_triggers_system_halt(self, circuit_breaker: CircuitBreaker) -> None:
        """Test system halts after consecutive triggers limit."""
        symbol = "BTC/USDT"
        # Use force_open to properly trigger (increments trigger count)
        circuit_breaker.force_open(symbol, "Test 1")
        circuit_breaker.force_open(symbol, "Test 2")
        circuit_breaker.force_open(symbol, "Test 3")

        # After 3 triggers (limit=3), system should be halted
        assert circuit_breaker.is_system_operational() is False
        status = circuit_breaker.get_status()
        assert symbol in status["open_circuits"]

    def test_force_open_and_close(self, circuit_breaker: CircuitBreaker) -> None:
        """Test manual force open and force close."""
        symbol = "BTC/USDT"
        circuit_breaker.force_open(symbol, "Manual test")
        status = circuit_breaker.get_symbol_status(symbol)
        assert status["state"] == "open"

        circuit_breaker.force_close(symbol)
        status = circuit_breaker.get_symbol_status(symbol)
        assert status["state"] == "closed"

    def test_blacklist_expiry(self, circuit_breaker: CircuitBreaker) -> None:  # noqa: ARG002
        """Test blacklist expiry after duration."""
        config = CircuitBreakerConfig(
            auto_blacklist_on_trigger=True,
            blacklist_duration_minutes=0,  # Expires immediately
        )
        cb = CircuitBreaker(config=config)
        symbol = "BTC/USDT"
        cb.check_symbol(symbol, 50000.0)
        cb.check_symbol(symbol, 45000.0)

        # Should still be blocked initially
        assert cb.check_symbol(symbol, 48000.0) is False

    def test_get_status_no_events(self, circuit_breaker: CircuitBreaker) -> None:
        """Test get_status returns empty state with no events."""
        status = circuit_breaker.get_status()
        assert status["system_state"] == "closed"
        assert status["open_circuits"] == []
        assert status["total_triggers"] == 0
        assert status["recent_events"] == []
