"""Technical features – pure Python, no external indicator library needed."""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
from loguru import logger


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def _bollinger(series: pd.Series, period: int = 20, std: int = 2):
    sma = _sma(series, period)
    std_val = series.rolling(window=period).std()
    upper = sma + std * std_val
    lower = sma - std * std_val
    band_width = (upper - lower) / sma
    pct = (series - lower) / (upper - lower)
    return upper, lower, band_width, pct


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _stochastic(df: pd.DataFrame, k=14, d=3):
    low_min = df["low"].rolling(window=k).min()
    high_max = df["high"].rolling(window=k).max()
    stoch_k = 100.0 * (df["close"] - low_min) / (high_max - low_min)
    stoch_d = stoch_k.rolling(window=d).mean()
    return stoch_k, stoch_d


def add_all_features(df: pd.DataFrame,
                     timeframes: List[int] = [1, 5, 15]) -> pd.DataFrame:
    """Compute rich feature set on 5‑minute base DataFrame. No lookahead."""
    base = df.copy()
    ohlc = base.resample("5min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"
    }).dropna()

    close = ohlc["close"]
    volume = ohlc["volume"]

    ohlc["returns_1"] = close.pct_change().shift(1)
    ohlc["returns_5"] = close.pct_change(5).shift(1)
    ohlc["returns_15"] = close.pct_change(15).shift(1)
    ohlc["log_returns"] = np.log1p(ohlc["returns_1"])

    ohlc["sma_10"] = _sma(close, 10).shift(1)
    ohlc["sma_20"] = _sma(close, 20).shift(1)
    ohlc["sma_50"] = _sma(close, 50).shift(1)
    ohlc["ema_9"] = _ema(close, 9).shift(1)
    ohlc["ema_21"] = _ema(close, 21).shift(1)
    ohlc["ema_50"] = _ema(close, 50).shift(1)

    ohlc["rsi_14"] = _rsi(close, 14).shift(1)
    ohlc["rsi_7"] = _rsi(close, 7).shift(1)

    ohlc["atr_14"] = _atr(ohlc, 14).shift(1)
    ohlc["atr_pct"] = (ohlc["atr_14"] / close.shift(1)).shift(1)

    bb_upper, bb_lower, bb_width, bb_pct = _bollinger(close.shift(1))
    ohlc["bb_upper"], ohlc["bb_lower"], ohlc["bb_width"], ohlc["bb_pct"] = bb_upper, bb_lower, bb_width, bb_pct

    macd_line, macd_signal, macd_hist = _macd(close.shift(1))
    ohlc["macd_line"], ohlc["macd_signal"], ohlc["macd_hist"] = macd_line, macd_signal, macd_hist

    stoch_k, stoch_d = _stochastic(ohlc)
    ohlc["stoch_k"], ohlc["stoch_d"] = stoch_k.shift(1), stoch_d.shift(1)

    ohlc["volume_ratio"] = (volume / volume.rolling(10).mean()).shift(1)
    ohlc["returns_std_10"] = ohlc["returns_1"].rolling(10).std().shift(1)
    ohlc["returns_std_20"] = ohlc["returns_1"].rolling(20).std().shift(1)
    ohlc["skew_20"] = ohlc["returns_1"].rolling(20).skew().shift(1)
    ohlc["kurt_20"] = ohlc["returns_1"].rolling(20).kurt().shift(1)

    ohlc["price_vs_open"] = (close.shift(1) / ohlc["open"].shift(1)) - 1
    ohlc["intraday_range"] = ((ohlc["high"] - ohlc["low"]) / ohlc["open"]).shift(1)
    ohlc["upper_shadow"] = ((ohlc["high"] - ohlc[["open", "close"]].max(axis=1)) / ohlc["open"]).shift(1)
    ohlc["lower_shadow"] = ((ohlc[["open", "close"]].min(axis=1) - ohlc["low"]) / ohlc["open"]).shift(1)

    mins = pd.Index((ohlc.index.hour - 9) * 60 + ohlc.index.minute - 15)
    mins = pd.Index([max(0, m) for m in mins])
    ohlc["time_sin"] = np.sin(2 * np.pi * mins / 375)
    ohlc["time_cos"] = np.cos(2 * np.pi * mins / 375)
    ohlc["day_sin"] = np.sin(2 * np.pi * ohlc.index.dayofweek / 5)
    ohlc["day_cos"] = np.cos(2 * np.pi * ohlc.index.dayofweek / 5)
    ohlc["is_first_30min"] = (mins <= 30).astype(int)
    ohlc["is_last_30min"] = (mins >= 345).astype(int)

    ohlc = ohlc.iloc[200:]
    ohlc = ohlc.dropna()
    return ohlc