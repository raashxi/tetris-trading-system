"""Daily feature engineering for EOD prediction model."""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


def _sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def _bollinger_bands(series: pd.Series, period: int = 20):
    """Bollinger Bands."""
    sma = _sma(series, period)
    std = series.rolling(window=period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    width = (upper - lower) / sma
    pct_b = (series - lower) / (upper - lower)
    return upper, lower, width, pct_b


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (simplified)."""
    high, low, close = df["high"], df["low"], df["close"]
    atr = _atr(df, period)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_di = 100 * _ema(pd.Series(plus_dm, index=df.index), period) / atr
    minus_di = 100 * _ema(pd.Series(minus_dm, index=df.index), period) / atr

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = _ema(dx, period)
    return adx


def add_daily_features(df: pd.DataFrame, nifty_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Compute all daily features for a stock.

    Args:
        df: DataFrame with columns [open, high, low, close, volume] and datetime index
        nifty_df: Optional Nifty 50 daily data for market-relative features

    Returns:
        DataFrame with all feature columns added
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    ohlc = df.copy()

    # ── Price Returns ────────────────────────────
    ohlc["return_1d"] = close.pct_change()
    ohlc["return_5d"] = close.pct_change(5)
    ohlc["return_21d"] = close.pct_change(21)
    ohlc["return_63d"] = close.pct_change(63)

    # ── Moving Averages ──────────────────────────
    ohlc["sma_10"] = _sma(close, 10)
    ohlc["sma_20"] = _sma(close, 20)
    ohlc["sma_50"] = _sma(close, 50)
    ohlc["sma_200"] = _sma(close, 200)
    ohlc["ema_10"] = _ema(close, 10)
    ohlc["ema_20"] = _ema(close, 20)
    ohlc["ema_50"] = _ema(close, 50)

    # Distance from moving averages (as %)
    ohlc["dist_sma_20"] = (close - ohlc["sma_20"]) / ohlc["sma_20"]
    ohlc["dist_sma_50"] = (close - ohlc["sma_50"]) / ohlc["sma_50"]
    ohlc["dist_sma_200"] = (close - ohlc["sma_200"]) / ohlc["sma_200"]

    # ── Momentum Oscillators ─────────────────────
    ohlc["rsi_14"] = _rsi(close, 14)
    ohlc["rsi_5"] = _rsi(close, 5)

    # MACD
    ema_12 = _ema(close, 12)
    ema_26 = _ema(close, 26)
    ohlc["macd_line"] = ema_12 - ema_26
    ohlc["macd_signal"] = _ema(ohlc["macd_line"], 9)
    ohlc["macd_hist"] = ohlc["macd_line"] - ohlc["macd_signal"]

    # ── Volatility ───────────────────────────────
    ohlc["atr_14"] = _atr(df, 14)
    ohlc["atr_pct"] = ohlc["atr_14"] / close

    # Historical volatility (21-day)
    ohlc["hist_vol_21"] = ohlc["return_1d"].rolling(21).std() * np.sqrt(252)

    # Bollinger Bands
    bb_upper, bb_lower, bb_width, bb_pct = _bollinger_bands(close, 20)
    ohlc["bb_width"] = bb_width
    ohlc["bb_pct_b"] = bb_pct

    # ── Trend Strength ───────────────────────────
    ohlc["adx_14"] = _adx(df, 14)

    # EMA crossover signals
    ohlc["ema_10_50_cross"] = (ohlc["ema_10"] > ohlc["ema_50"]).astype(float)

    # ── Volume ───────────────────────────────────
    ohlc["volume_ratio_20"] = volume / volume.rolling(20).mean()
    ohlc["volume_ratio_50"] = volume / volume.rolling(50).mean()

    # On-Balance Volume change
    obv = (volume * np.sign(close.diff())).cumsum()
    ohlc["obv_change_5d"] = obv.pct_change(5)

    # ── Price Pattern ────────────────────────────
    ohlc["gap"] = (df["open"] - close.shift(1)) / close.shift(1)
    ohlc["intraday_range"] = (high - low) / close
    ohlc["close_location"] = (close - low) / (high - low)  # where did we close in today's range?
    ohlc["body_pct"] = (close - df["open"]) / df["open"]  # candlestick body

    # ── Calendar Features ────────────────────────
    ohlc["day_of_week"] = ohlc.index.dayofweek
    ohlc["month"] = ohlc.index.month
    ohlc["is_month_end"] = (ohlc.index.day >= 25).astype(int)

    # ── Market-Relative Features ─────────────────
    if nifty_df is not None and not nifty_df.empty:
        nifty_close = nifty_df["close"].reindex(ohlc.index, method="ffill")
        nifty_return_1d = nifty_close.pct_change()
        ohlc["nifty_return_1d"] = nifty_return_1d
        ohlc["nifty_return_5d"] = nifty_close.pct_change(5)

        # Stock vs Market relative strength
        ohlc["return_vs_nifty_1d"] = ohlc["return_1d"] - nifty_return_1d
        ohlc["return_vs_nifty_5d"] = ohlc["return_5d"] - ohlc["nifty_return_5d"]

        # Rolling beta (21-day)
        stock_ret = ohlc["return_1d"].dropna()
        nifty_ret = nifty_return_1d.dropna()
        common_idx = stock_ret.index.intersection(nifty_ret.index)
        if len(common_idx) > 21:
            rolling_beta = (
                stock_ret[common_idx]
                .rolling(21)
                .cov(nifty_ret[common_idx]) / nifty_ret[common_idx].rolling(21).var()
            )
            ohlc["rolling_beta_21"] = rolling_beta
        else:
            ohlc["rolling_beta_21"] = 1.0
    else:
        ohlc["nifty_return_1d"] = 0.0
        ohlc["nifty_return_5d"] = 0.0
        ohlc["return_vs_nifty_1d"] = 0.0
        ohlc["return_vs_nifty_5d"] = 0.0
        ohlc["rolling_beta_21"] = 1.0

    # ── Cleanup ──────────────────────────────────
    ohlc = ohlc.replace([np.inf, -np.inf], np.nan)
    ohlc = ohlc.dropna()

    return ohlc