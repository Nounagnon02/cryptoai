"""
Implémentation complète des indicateurs techniques.

Chaque indicateur est une fonction pure (DataFrame in → Series out).
Utilise ta (Technical Analysis Library) avec fallback NumPy.
Timeframes supportés : 1m, 5m, 15m, 1h, 4h, 1d, 1w
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ta

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# TREND INDICATORS
# ═══════════════════════════════════════════════════════════════

def ema(close: pd.Series, period: int = 21) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=period, adjust=False).mean()


def sma(close: pd.Series, period: int = 50) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=period).mean()


def wma(close: pd.Series, period: int = 21) -> pd.Series:
    """Weighted Moving Average."""
    weights = np.arange(1, period + 1)
    return close.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD (Moving Average Convergence Divergence).

    Returns:
        DataFrame avec colonnes : macd, signal, histogram
    """
    macd_line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    })


def ichimoku(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
    displacement: int = 26,
) -> pd.DataFrame:
    """
    Ichimoku Cloud complet.

    Returns:
        DataFrame avec : tenkan, kijun, senkou_a, senkou_b, chikou, cloud_color
    """
    tenkan = (high.rolling(tenkan_period).max() + low.rolling(tenkan_period).min()) / 2
    kijun = (high.rolling(kijun_period).max() + low.rolling(kijun_period).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(displacement)
    senkou_b = ((high.rolling(senkou_b_period).max() + low.rolling(senkou_b_period).min()) / 2).shift(displacement)
    chikou = close.shift(-displacement)

    cloud_color = pd.Series(index=close.index, data="neutral")
    cloud_color[senkou_a > senkou_b] = "green"  # Bullish
    cloud_color[senkou_a <= senkou_b] = "red"    # Bearish

    return pd.DataFrame({
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "chikou": chikou,
        "cloud_color": cloud_color,
    })


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    """
    ADX (Average Directional Index) avec DI+ et DI-.

    ADX > 25 : tendance forte
    ADX < 20 : range / consolidation
    """
    # True Range
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    # Directional Movement
    up_move = high - high.shift()
    down_move = low.shift() - low

    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    # ADX
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx_line = dx.rolling(period).mean()

    return pd.DataFrame({
        "adx": adx_line,
        "plus_di": plus_di,
        "minus_di": minus_di,
    })


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """
    SuperTrend indicator.

    Returns:
        DataFrame avec : supertrend (valeur ligne), trend (1=bullish, -1=bearish)
    """
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl_avg = (high + low) / 2
    upper_band = hl_avg + multiplier * atr
    lower_band = hl_avg - multiplier * atr

    supertrend_val = pd.Series(0.0, index=close.index)
    trend = pd.Series(1, index=close.index)

    for i in range(1, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            trend.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1]
            if trend.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if trend.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        supertrend_val.iloc[i] = lower_band.iloc[i] if trend.iloc[i] == 1 else upper_band.iloc[i]

    return pd.DataFrame({
        "supertrend": supertrend_val,
        "trend": trend,
    })


# ═══════════════════════════════════════════════════════════════
# MOMENTUM INDICATORS
# ═══════════════════════════════════════════════════════════════

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    return ta.momentum.RSIIndicator(close, window=period).rsi()


def stoch_rsi(
    close: pd.Series,
    period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
) -> pd.DataFrame:
    """Stochastic RSI."""
    stoch = ta.momentum.StochRSIIndicator(close, window=period, smooth1=k_period, smooth2=d_period)
    return pd.DataFrame({
        "stoch_rsi": stoch.stochrsi(),
        "stoch_rsi_k": stoch.stochrsi_k(),
        "stoch_rsi_d": stoch.stochrsi_d(),
    })


def roc(close: pd.Series, period: int = 10) -> pd.Series:
    """Rate of Change (%ROC)."""
    return ((close - close.shift(period)) / close.shift(period)) * 100


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Williams %R."""
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    return -100 * (highest_high - close) / (highest_high - lowest_low + 1e-10)


def money_flow_index(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Money Flow Index (MFI)."""
    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * volume

    mf_ratio = pd.Series(0.0, index=close.index)
    for i in range(1, len(typical_price)):
        if typical_price.iloc[i] > typical_price.iloc[i - 1]:
            mf_ratio.iloc[i] = raw_money_flow.iloc[i]
        else:
            mf_ratio.iloc[i] = -raw_money_flow.iloc[i]

    return 100 - (100 / (1 + mf_ratio.rolling(period).apply(
        lambda x: max(0, x.sum()) / max(1e-10, abs(x[x < 0].sum()))
    )))


# ═══════════════════════════════════════════════════════════════
# VOLATILITY INDICATORS
# ═══════════════════════════════════════════════════════════════

def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands."""
    bb = ta.volatility.BollingerBands(close, window=period, window_dev=std_dev)
    return pd.DataFrame({
        "bb_upper": bb.bollinger_hband(),
        "bb_middle": bb.bollinger_mavg(),
        "bb_lower": bb.bollinger_lband(),
        "bb_width": (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg(),
        "bb_pct": bb.bollinger_pband(),
    })


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    return ta.volatility.AverageTrueRange(high, low, close, window=period).average_true_range()


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    multiplier: float = 2.0,
) -> pd.DataFrame:
    """Keltner Channels."""
    middle = close.ewm(span=period, adjust=False).mean()
    atr_val = atr(high, low, close, period)

    return pd.DataFrame({
        "kc_upper": middle + multiplier * atr_val,
        "kc_middle": middle,
        "kc_lower": middle - multiplier * atr_val,
        "kc_width": (2 * multiplier * atr_val) / middle,
    })


# ═══════════════════════════════════════════════════════════════
# VOLUME INDICATORS
# ═══════════════════════════════════════════════════════════════

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    return ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()


def vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    """Volume-Weighted Average Price."""
    typical_price = (high + low + close) / 3
    cumulative_vp = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()
    return cumulative_vp / cumulative_volume.replace(0, np.nan)


def volume_profile(volume: pd.Series, close: pd.Series, num_bins: int = 10) -> dict:
    """
    Volume Profile — distribution du volume par niveau de prix.
    Identifie les zones de valeur haute/négociation.

    Returns:
        Dict avec prix max_volume, vwap, et distribution par paliers
    """
    price_min, price_max = close.min(), close.max()
    bin_size = (price_max - price_min) / num_bins if price_max > price_min else 1

    bins = pd.cut(close, bins=num_bins, labels=False)
    profile = volume.groupby(bins).sum()

    poc_bin = profile.idxmax()
    poc_price = price_min + (poc_bin + 0.5) * bin_size

    return {
        "point_of_control": poc_price,
        "value_area_high": price_min + (profile[profile > profile.sum() * 0.05].index.max() + 1) * bin_size,
        "value_area_low": price_min + profile[profile > profile.sum() * 0.05].index.min() * bin_size,
        "profile": profile.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════
# PATTERN / SUPPORT & RESISTANCE
# ═══════════════════════════════════════════════════════════════

def donchian_channels(
    high: pd.Series, low: pd.Series, period: int = 20
) -> pd.DataFrame:
    """Donchian Channels."""
    return pd.DataFrame({
        "dc_upper": high.rolling(period).max(),
        "dc_middle": (high.rolling(period).max() + low.rolling(period).min()) / 2,
        "dc_lower": low.rolling(period).min(),
        "dc_width": ((high.rolling(period).max() - low.rolling(period).min())
                     / ((high.rolling(period).max() + low.rolling(period).min()) / 2)),
    })


def pivot_points(
    high: pd.Series, low: pd.Series, close: pd.Series
) -> pd.DataFrame:
    """
    Pivot Points classiques (Floor Trading).

    Returns:
        DataFrame avec : R3, R2, R1, PP, S1, S2, S3
    """
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)

    return pd.DataFrame({
        "pivot": pp,
        "r1": r1, "r2": r2, "r3": r3,
        "s1": s1, "s2": s2, "s3": s3,
    })


def fibonacci_levels(high: pd.Series, low: pd.Series) -> dict[str, float]:
    """
    Retracement Fibonacci (dernier swing complet).

    Returns:
        Dict avec les niveaux 0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0
    """
    swing_high = high.max()
    swing_low = low.min()
    diff = swing_high - swing_low

    return {
        "level_0": swing_high,
        "level_0236": swing_high - diff * 0.236,
        "level_0382": swing_high - diff * 0.382,
        "level_05": swing_high - diff * 0.5,
        "level_0618": swing_high - diff * 0.618,
        "level_0786": swing_high - diff * 0.786,
        "level_1": swing_low,
    }


# ═══════════════════════════════════════════════════════════════
# INDICATOR REGISTRY
# ═══════════════════════════════════════════════════════════════

INDICATOR_FUNCTIONS = {
    # Trend
    "ema_9": lambda df: ema(df["close"], 9),
    "ema_21": lambda df: ema(df["close"], 21),
    "ema_50": lambda df: ema(df["close"], 50),
    "ema_200": lambda df: ema(df["close"], 200),
    "sma_20": lambda df: sma(df["close"], 20),
    "sma_50": lambda df: sma(df["close"], 50),
    "sma_200": lambda df: sma(df["close"], 200),
    "macd": lambda df: macd(df["close"]),
    "ichimoku": lambda df: ichimoku(df["high"], df["low"], df["close"]),
    "adx": lambda df: adx(df["high"], df["low"], df["close"]),
    "supertrend": lambda df: supertrend(df["high"], df["low"], df["close"]),
    # Momentum
    "rsi_14": lambda df: rsi(df["close"], 14),
    "stoch_rsi": lambda df: stoch_rsi(df["close"]),
    "roc": lambda df: roc(df["close"]),
    "williams_r": lambda df: williams_r(df["high"], df["low"], df["close"]),
    "mfi": lambda df: money_flow_index(df["high"], df["low"], df["close"], df["volume"]),
    # Volatility
    "bbands": lambda df: bollinger_bands(df["close"]),
    "atr_14": lambda df: atr(df["high"], df["low"], df["close"]),
    "keltner": lambda df: keltner_channels(df["high"], df["low"], df["close"]),
    # Volume
    "obv": lambda df: obv(df["close"], df["volume"]),
    "vwap": lambda df: vwap(df["high"], df["low"], df["close"], df["volume"]),
}


def compute_all_indicators(df: pd.DataFrame) -> dict[str, pd.Series | pd.DataFrame]:
    """
    Calcule tous les indicateurs techniques sur un DataFrame OHLCV.

    Args:
        df: DataFrame avec colonnes open, high, low, close, volume

    Returns:
        Dictionnaire {nom_indicateur: valeur calculée}
    """
    results = {}
    for name, func in INDICATOR_FUNCTIONS.items():
        try:
            results[name] = func(df)
        except Exception as e:
            logger.debug("Erreur calcul %s: %s", name, str(e))
    return results
