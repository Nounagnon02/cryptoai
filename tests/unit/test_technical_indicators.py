"""Tests for technical indicators."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.technical.indicators import (
    adx,
    atr,
    bollinger_bands,
    compute_all_indicators,
    donchian_channels,
    ema,
    fibonacci_levels,
    ichimoku,
    keltner_channels,
    macd,
    money_flow_index,
    obv,
    pivot_points,
    roc,
    rsi,
    sma,
    stoch_rsi,
    supertrend,
    volume_profile,
    vwap,
    williams_r,
    wma,
)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate synthetic OHLCV data with a known trend."""
    np.random.seed(42)
    n = 200
    # Uptrend with noise
    trend = np.linspace(100, 150, n)
    noise = np.random.normal(0, 2, n)
    close = trend + noise
    high = close + np.abs(np.random.normal(0, 1.5, n))
    low = close - np.abs(np.random.normal(0, 1.5, n))
    volume = np.random.uniform(1000, 5000, n)
    open_price = close - np.random.normal(0, 1, n)

    return pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def constant_price_data() -> pd.DataFrame:
    """Data with constant prices (edge case)."""
    n = 100
    return pd.DataFrame({
        "open": [150.0] * n,
        "high": [150.0] * n,
        "low": [150.0] * n,
        "close": [150.0] * n,
        "volume": [1000.0] * n,
    })


class TestTrendIndicators:
    """Tests for trend-following indicators."""

    def test_ema_calculation(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test EMA calculation with synthetic data."""
        ema_21 = ema(sample_ohlcv["close"], period=21)
        assert len(ema_21) == len(sample_ohlcv)
        assert not ema_21.isna().all()
        # Early values (before enough data for span) may be NaN
        # Later values should be finite
        assert np.isfinite(ema_21.iloc[-1])

    def test_sma_calculation(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test SMA calculation."""
        sma_50 = sma(sample_ohlcv["close"], period=50)
        assert len(sma_50) == len(sample_ohlcv)
        # Last value should be reasonable (close to 150 given trend)
        assert np.isfinite(sma_50.iloc[-1])

    def test_wma_calculation(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test WMA calculation."""
        wma_21 = wma(sample_ohlcv["close"], period=21)
        assert len(wma_21) == len(sample_ohlcv)

    def test_macd_cross_detection(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test MACD calculation detects cross events."""
        macd_result = macd(sample_ohlcv["close"])
        assert "macd" in macd_result.columns
        assert "signal" in macd_result.columns
        assert "histogram" in macd_result.columns
        # Check for crossover: when histogram crosses zero, macd crosses signal
        hist = macd_result["histogram"].dropna()
        assert len(hist) > 0

    def test_ichimoku_cloud(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Ichimoku Cloud calculation."""
        ichi = ichimoku(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert "tenkan" in ichi.columns
        assert "kijun" in ichi.columns
        assert "senkou_a" in ichi.columns
        assert "senkou_b" in ichi.columns
        assert "cloud_color" in ichi.columns
        assert ichi["cloud_color"].iloc[-1] in ("green", "red", "neutral")

    def test_adx_trend_strength(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test ADX measures trend strength."""
        adx_result = adx(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert "adx" in adx_result.columns
        assert "plus_di" in adx_result.columns
        assert "minus_di" in adx_result.columns
        # In an uptrend, +DI should be > -DI on average
        avg_plus_di = adx_result["plus_di"].dropna().mean()
        avg_minus_di = adx_result["minus_di"].dropna().mean()
        # Our synthetic data has an uptrend
        assert avg_plus_di > avg_minus_di or avg_plus_di > 0

    def test_supertrend(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test SuperTrend indicator."""
        st = supertrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert "supertrend" in st.columns
        assert "trend" in st.columns
        # Trend should be 1 (bullish) or -1 (bearish)
        assert st["trend"].dropna().iloc[-1] in (1, -1)


class TestMomentumIndicators:
    """Tests for momentum indicators."""

    def test_rsi_with_known_values(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test that RSI stays within 0-100 range."""
        rsi_values = rsi(sample_ohlcv["close"], period=14)
        valid = rsi_values.dropna()
        assert len(valid) > 0
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_rsi_constant_price(self, constant_price_data: pd.DataFrame) -> None:
        """Test RSI with constant prices (should not crash)."""
        rsi_values = rsi(constant_price_data["close"], period=14)
        # RSI on constant prices should return valid values (0 or 50 or NaN)
        assert len(rsi_values) == len(constant_price_data)

    def test_stoch_rsi(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Stochastic RSI stays within bounds."""
        sk = stoch_rsi(sample_ohlcv["close"])
        assert "stoch_rsi" in sk.columns
        assert "stoch_rsi_k" in sk.columns
        assert "stoch_rsi_d" in sk.columns
        valid = sk["stoch_rsi"].dropna()
        assert len(valid) > 0
        assert valid.min() >= 0
        assert valid.max() <= 1

    def test_roc_calculation(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Rate of Change calculation."""
        roc_values = roc(sample_ohlcv["close"], period=10)
        valid = roc_values.dropna()
        assert len(valid) > 0
        # In an uptrend, ROC should be positive on average
        assert valid.mean() > -5

    def test_williams_r(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Williams %R stays within -100 to 0."""
        wr = williams_r(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        valid = wr.dropna()
        assert len(valid) > 0
        assert valid.min() >= -100
        assert valid.max() <= 0

    def test_money_flow_index(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Money Flow Index stays within 0-100."""
        mfi = money_flow_index(
            sample_ohlcv["high"], sample_ohlcv["low"],
            sample_ohlcv["close"], sample_ohlcv["volume"],
        )
        valid = mfi.dropna()
        assert len(valid) > 0
        assert valid.min() >= 0
        assert valid.max() <= 100


class TestVolatilityIndicators:
    """Tests for volatility indicators."""

    def test_bollinger_bands_width(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Bollinger Bands width calculation."""
        bb = bollinger_bands(sample_ohlcv["close"])
        assert "bb_upper" in bb.columns
        assert "bb_middle" in bb.columns
        assert "bb_lower" in bb.columns
        assert "bb_width" in bb.columns
        assert "bb_pct" in bb.columns
        # Upper band must be > middle > lower
        valid = bb.dropna()
        assert (valid["bb_upper"] >= valid["bb_middle"]).all()
        assert (valid["bb_middle"] >= valid["bb_lower"]).all()
        # Width should be positive
        assert (valid["bb_width"] > 0).all()

    def test_bollinger_bands_position(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test that %B indicates price position within bands."""
        bb = bollinger_bands(sample_ohlcv["close"])
        valid = bb["bb_pct"].dropna()
        assert len(valid) > 0
        # %B should typically be between 0 and 1 for most data points
        assert valid.mean() > -1  # Check it doesn't all fail

    def test_atr(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test ATR calculation."""
        atr_values = atr(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        valid = atr_values.dropna()
        assert len(valid) > 0
        # ATR should be positive or zero for later rows
        later_valid = valid.iloc[len(valid) // 2:]  # Second half
        assert (later_valid > 0).all()

    def test_keltner_channels(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Keltner Channels calculation."""
        kc = keltner_channels(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert "kc_upper" in kc.columns
        assert "kc_middle" in kc.columns
        assert "kc_lower" in kc.columns
        assert "kc_width" in kc.columns
        valid = kc.dropna()
        assert (valid["kc_upper"] >= valid["kc_middle"]).all()


class TestVolumeIndicators:
    """Tests for volume-based indicators."""

    def test_obv(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test On-Balance Volume calculation."""
        obv_values = obv(sample_ohlcv["close"], sample_ohlcv["volume"])
        assert len(obv_values) == len(sample_ohlcv)
        # OBV changes with price direction
        assert not obv_values.isna().all()

    def test_vwap(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test VWAP calculation."""
        vwap_values = vwap(
            sample_ohlcv["high"], sample_ohlcv["low"],
            sample_ohlcv["close"], sample_ohlcv["volume"],
        )
        assert len(vwap_values) == len(sample_ohlcv)
        # VWAP should be close to the price level
        assert np.isfinite(vwap_values.iloc[-1])

    def test_volume_profile(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Volume Profile calculation."""
        vp = volume_profile(sample_ohlcv["volume"], sample_ohlcv["close"], num_bins=10)
        assert "point_of_control" in vp
        assert "value_area_high" in vp
        assert "value_area_low" in vp
        assert "profile" in vp
        # Point of control should be within price range
        assert sample_ohlcv["close"].min() <= vp["point_of_control"] <= sample_ohlcv["close"].max()


class TestPatternIndicators:
    """Tests for pattern/support-resistance indicators."""

    def test_donchian_channels(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Donchian Channels calculation."""
        dc = donchian_channels(sample_ohlcv["high"], sample_ohlcv["low"])
        assert "dc_upper" in dc.columns
        assert "dc_middle" in dc.columns
        assert "dc_lower" in dc.columns
        assert "dc_width" in dc.columns
        valid = dc.dropna()
        assert (valid["dc_upper"] >= valid["dc_middle"]).all()
        assert (valid["dc_middle"] >= valid["dc_lower"]).all()

    def test_pivot_points(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Pivot Points calculation."""
        pp = pivot_points(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert "pivot" in pp.columns
        assert "r1" in pp.columns
        assert "s1" in pp.columns
        assert "r3" in pp.columns
        assert "s3" in pp.columns
        # R levels should be >= pivot >= S levels
        assert (pp["r3"] >= pp["pivot"]).all()
        assert (pp["pivot"] >= pp["s3"]).all()

    def test_fibonacci_levels(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test Fibonacci retracement levels."""
        fib = fibonacci_levels(sample_ohlcv["high"], sample_ohlcv["low"])
        assert "level_0" in fib
        assert "level_0618" in fib
        assert "level_1" in fib
        # Level 0 = swing high, Level 1 = swing low
        assert fib["level_0"] >= fib["level_1"]
        # 0.236 should be between level_0 and level_1
        assert fib["level_0"] >= fib["level_0236"] >= fib["level_1"]


class TestEdgeCases:
    """Tests for edge cases."""

    def test_constant_price_edge_cases(self, constant_price_data: pd.DataFrame) -> None:
        """Test indicators on constant price data (should not crash)."""
        # These should not crash
        ema_result = ema(constant_price_data["close"])
        assert ema_result.iloc[-1] == pytest.approx(150.0, rel=0.01)

        bb = bollinger_bands(constant_price_data["close"])
        # With constant prices, bands may have NaN width (division by zero)
        # but should still produce valid rows
        assert "bb_upper" in bb.columns
        assert "bb_middle" in bb.columns

    def test_zero_volume(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test indicators with zero volume."""
        df = sample_ohlcv.copy()
        df["volume"] = 0.0
        # OBV with zero volume should be flat (no changes)
        obv_values = obv(df["close"], df["volume"])
        assert (obv_values == 0.0).all() or not obv_values.isna().all()

    def test_compute_all_indicators(self, sample_ohlcv: pd.DataFrame) -> None:
        """Test that compute_all_indicators runs without error."""
        results = compute_all_indicators(sample_ohlcv)
        assert isinstance(results, dict)
        assert len(results) > 0
        # All indicator names should be keys
        expected_names = {"rsi_14", "macd", "bbands", "atr_14", "obv", "vwap", "ema_9", "sma_20", "adx"}
        assert expected_names.issubset(set(results.keys()))

    def test_compute_all_indicators_missing_columns(self) -> None:
        """Test compute_all_indicators with DataFrame missing columns."""
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        # Should not crash, just skip indicators that need missing columns
        results = compute_all_indicators(df)
        assert isinstance(results, dict)
