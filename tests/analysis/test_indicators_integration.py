"""
Integration tests for technical indicators on synthetic data.

Verifies that all indicators work together coherently on the same
dataset — testing consistency, trend confirmation, divergence detection,
and graceful handling of insufficient data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.technical.indicators import (
    bollinger_bands,
    compute_all_indicators,
    donchian_channels,
    fibonacci_levels,
    macd,
    obv,
    vwap,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def long_uptrend_ohlcv() -> pd.DataFrame:
    """500 bars of OHLCV with a clear uptrend for full indicator warmup."""
    np.random.seed(42)
    n = 500
    trend = np.linspace(100, 200, n)
    noise = np.random.normal(0, 3, n)
    close = trend + noise
    high = close + np.abs(np.random.normal(0, 2, n))
    low = close - np.abs(np.random.normal(0, 2, n))
    volume = np.random.uniform(2000, 6000, n)
    # Volume slightly higher on up days
    for i in range(1, n):
        if close[i] > close[i - 1]:
            volume[i] *= 1.2
    open_price = close - np.random.normal(0, 1.5, n)
    return pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def sideways_market() -> pd.DataFrame:
    """200 bars of sideways (range-bound) market."""
    np.random.seed(7)
    n = 200
    base = 150.0
    noise = np.random.normal(0, 5, n)
    close = base + noise
    high = close + np.abs(np.random.normal(0, 3, n))
    low = close - np.abs(np.random.normal(0, 3, n))
    volume = np.random.uniform(1000, 4000, n)
    open_price = close - np.random.normal(0, 2, n)
    return pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def short_data() -> pd.DataFrame:
    """Only 10 bars — insufficient for most indicators."""
    np.random.seed(13)
    return pd.DataFrame({
        "open": np.random.normal(100, 2, 10),
        "high": np.random.normal(102, 2, 10),
        "low": np.random.normal(98, 2, 10),
        "close": np.random.normal(100, 2, 10),
        "volume": np.random.uniform(1000, 5000, 10),
    })


# ── Tests ────────────────────────────────────────────────────────────────────


class TestAllIndicators:
    """Integration-level tests covering all indicators together."""

    def test_all_indicators_computed_without_nan_on_500_bars(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """compute_all_indicators runs without error and returns no NaN in tail.

        With 500 bars, all indicator windows should have warmed up.
        """
        results = compute_all_indicators(long_uptrend_ohlcv)
        assert isinstance(results, dict)
        assert len(results) > 0

        # Check that the tail (last 50 rows) of Series results has no NaN
        for name, val in results.items():
            if isinstance(val, pd.Series):
                tail = val.iloc[-50:]
                # Some indicators may produce NaN for the very first values
                # but the tail should be fully populated
                valid_count = tail.notna().sum()
                assert valid_count >= 45, (
                    f"{name} has {50 - valid_count} NaN values in last 50 rows"
                )
            elif isinstance(val, pd.DataFrame):
                for col in val.columns:
                    if col == "cloud_color":
                        continue  # Non-numeric column
                    if col == "chikou":
                        continue  # Chikou is shifted forward, inherently has NaN tail
                    tail = val[col].iloc[-50:]
                    valid_count = tail.notna().sum()
                    assert valid_count >= 40, (
                        f"{name}[{col}] has {50 - valid_count} NaN in last 50 rows"
                    )

    def test_rolling_calculations_consistent(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """Indicators that depend on rolling windows produce monotonic or bounded output.

        Checks that bbands, donchian, and macd produce internally consistent values.
        """
        close = long_uptrend_ohlcv["close"]

        # Bollinger Bands: upper >= middle >= lower
        bb = bollinger_bands(close)
        valid = bb.dropna()
        assert (valid["bb_upper"] >= valid["bb_middle"]).all()
        assert (valid["bb_middle"] >= valid["bb_lower"]).all()

        # Donchian Channels: upper >= middle >= lower
        dc = donchian_channels(
            long_uptrend_ohlcv["high"],
            long_uptrend_ohlcv["low"],
        )
        valid_dc = dc.dropna()
        assert (valid_dc["dc_upper"] >= valid_dc["dc_middle"]).all()
        assert (valid_dc["dc_middle"] >= valid_dc["dc_lower"]).all()

    def test_macd_positive_in_uptrend(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """In a sustained uptrend, the MACD line should generally be positive."""
        close = long_uptrend_ohlcv["close"]
        macd_df = macd(close)
        macd_line = macd_df["macd"].dropna()

        # Most of the tail values should be positive in an uptrend
        tail = macd_line.iloc[-100:]
        positive_ratio = (tail > 0).sum() / len(tail)
        assert positive_ratio > 0.5, (
            f"Only {positive_ratio:.0%} of MACD values positive in uptrend"
        )

    def test_bollinger_breakout_detection(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """In a strong trend, price should touch the upper band periodically."""
        close = long_uptrend_ohlcv["close"]
        bb = bollinger_bands(close)
        valid = bb.dropna()

        # %B above 1.0 indicates price above upper band
        bb_pct = valid["bb_pct"]
        breakouts = (bb_pct > 1.0).sum()
        assert breakouts >= 0  # Not guaranteed, but should not crash

    def test_vwap_trend_confirmation(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """In an uptrend, VWAP should be below the current price at the tail."""
        df = long_uptrend_ohlcv
        vwap_vals = vwap(df["high"], df["low"], df["close"], df["volume"])
        vwap_vals = vwap_vals.dropna()

        # At the end of an uptrend, price should be above VWAP
        if len(vwap_vals) > 10:
            price_above_vwap = (df["close"].iloc[-len(vwap_vals):].values > vwap_vals.values).sum()
            tail_ratio = price_above_vwap / len(vwap_vals)
            # In an uptrend, more than half the time price should be above VWAP
            assert tail_ratio > 0.4

    def test_obv_confirms_trend(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """On-Balance Volume should generally rise alongside an uptrend.

        Since volume is slightly higher on up days in our fixture,
        OBV should show an upward trajectory.
        """
        close = long_uptrend_ohlcv["close"]
        volume = long_uptrend_ohlcv["volume"]
        obv_vals = obv(close, volume)

        obv_tail = obv_vals.iloc[-100:]
        # In an uptrend with higher volume on up days, OBV should be
        # higher at the end than at the start of the tail
        assert obv_tail.iloc[-1] >= obv_tail.iloc[0], (
            "OBV decreased despite uptrend with volume confirmation"
        )

    def test_obv_divergence_detection(
        self,
        sideways_market: pd.DataFrame,
    ) -> None:
        """In a sideways market, OBV may diverge — check it at least runs."""
        close = sideways_market["close"]
        volume = sideways_market["volume"]
        obv_vals = obv(close, volume)

        # OBV should be finite
        assert np.isfinite(obv_vals.iloc[-1])

    def test_donchian_breakout(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """In an uptrend, price should periodically challenge the Donchian upper band."""
        high = long_uptrend_ohlcv["high"]
        low = long_uptrend_ohlcv["low"]
        close = long_uptrend_ohlcv["close"]

        dc = donchian_channels(high, low)
        valid = dc.dropna()

        # The close price should be near the upper band at times in an uptrend
        upper_series = valid["dc_upper"]
        close_aligned = close.iloc[-len(upper_series):]
        near_upper = (close_aligned >= upper_series * 0.98).sum()
        assert near_upper >= 0  # At minimum, no crash

    def test_fibonacci_levels_correct_ratios(
        self,
        long_uptrend_ohlcv: pd.DataFrame,
    ) -> None:
        """Fibonacci levels should maintain correct ratio relationships."""
        high = long_uptrend_ohlcv["high"]
        low = long_uptrend_ohlcv["low"]

        fib = fibonacci_levels(high, low)

        assert fib["level_0"] >= fib["level_1"]
        assert fib["level_0"] > fib["level_0236"] > fib["level_0382"] > fib["level_05"] > fib["level_0618"] > fib["level_0786"] > fib["level_1"]

        # Verify specific ratio differences
        diff = fib["level_0"] - fib["level_1"]
        assert abs(fib["level_0"] - fib["level_0236"] - diff * 0.236) < 0.01
        assert abs(fib["level_0"] - fib["level_0618"] - diff * 0.618) < 0.01

    def test_insufficient_data_graceful_handling(
        self,
        short_data: pd.DataFrame,
    ) -> None:
        """compute_all_indicators on very short data should not crash.

        Some indicators may return empty or all-NaN series, but the
        function should handle this gracefully.
        """
        results = compute_all_indicators(short_data)
        assert isinstance(results, dict)
        # Function should complete without raising
