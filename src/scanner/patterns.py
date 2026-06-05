"""Pattern recognition with quality scoring for EOD watchlist."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from kiteconnect import KiteConnect
from loguru import logger

from src.auth.session import get_kite_session


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def fetch_ohlc(kite: KiteConnect, symbol: str, days: int = 30) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV for pattern analysis."""
    try:
        instruments = kite.instruments("NSE")
        token = None
        for ins in instruments:
            if ins["tradingsymbol"] == symbol:
                token = ins["instrument_token"]
                break
        if token is None:
            return None

        today = datetime.now()
        data = kite.historical_data(
            instrument_token=token,
            from_date=(today - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
            to_date=today.strftime("%Y-%m-%d %H:%M:%S"),
            interval="day",
            continuous=False,
            oi=False,
        )
        if not data:
            return None
        df = pd.DataFrame(data)
        df["datetime"] = pd.to_datetime(df["date"])
        df.set_index("datetime", inplace=True)
        return df[["open", "high", "low", "close", "volume"]].astype(float)
    except Exception as e:
        logger.error(f"Pattern fetch error for {symbol}: {e}")
        return None


def detect_breakout(df: pd.DataFrame) -> Tuple[bool, float]:
    """
    Detect breakout above 20-day resistance.
    Returns (is_breakout, quality_score 0-1).
    """
    if len(df) < 25:
        return False, 0.0

    close = df["close"]
    high = df["high"]
    volume = df["volume"]

    # 20-day resistance (highest high in last 20 days)
    resistance = high.iloc[-21:-1].max()
    latest_close = close.iloc[-1]
    latest_volume = volume.iloc[-1]
    avg_volume_20 = volume.iloc[-21:-1].mean()

    if latest_close <= resistance * 1.005:  # within 0.5% above resistance
        return False, 0.0

    # Quality checks
    score = 0.0
    checks = 0

    # Volume confirmation (>2x avg)
    if avg_volume_20 > 0:
        vol_ratio = latest_volume / avg_volume_20
        if vol_ratio > 2.0:
            score += 1.0
        else:
            score += vol_ratio / 2.0
        checks += 1

    # Close near high (clean breakout, no upper wick)
    if high.iloc[-1] > close.iloc[-1]:
        wick_ratio = (high.iloc[-1] - close.iloc[-1]) / (close.iloc[-1] - df["low"].iloc[-1] + 0.001)
        score += 1.0 - min(wick_ratio, 1.0)
        checks += 1

    # Prior tests of resistance
    prior_tests = sum(1 for i in range(-21, -1) if high.iloc[i] >= resistance * 0.985)
    if prior_tests >= 2:
        score += 1.0
    checks += 1

    quality = score / max(checks, 1)
    return quality > 0.5, round(quality, 2)


def detect_bull_flag(df: pd.DataFrame) -> Tuple[bool, float]:
    """
    Detect bull flag: steep pole up, then shallow consolidation with declining volume.
    """
    if len(df) < 15:
        return False, 0.0

    close = df["close"]
    volume = df["volume"]

    # Check for prior uptrend (pole) - last 5 days strong up?
    pole_return = (close.iloc[-6] - close.iloc[-11]) / close.iloc[-11] if len(close) >= 11 else 0
    if pole_return < 0.05:  # at least 5% move
        return False, 0.0

    # Consolidation (flag) - last 3-5 days shallow retracement
    flag_retrace = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6]
    if flag_retrace > 0.02 or flag_retrace < -0.05:  # too deep retracement or no consolidation
        return False, 0.0

    # Volume declining during flag
    vol_start = volume.iloc[-6:-4].mean()
    vol_end = volume.iloc[-3:-1].mean()
    vol_declining = vol_end < vol_start * 0.8 if vol_start > 0 else False

    quality = 0.0
    if vol_declining:
        quality += 0.4
    if flag_retrace > -0.03 and flag_retrace < 0.01:  # shallow flag
        quality += 0.4
    if pole_return > 0.08:  # strong pole
        quality += 0.2

    return quality >= 0.5, round(min(quality, 1.0), 2)


def detect_inside_day(df: pd.DataFrame) -> Tuple[bool, float]:
    """
    Inside day: today's range entirely within yesterday's range.
    Indicates compression and potential explosive move.
    """
    if len(df) < 3:
        return False, 0.0

    today_high = df["high"].iloc[-1]
    today_low = df["low"].iloc[-1]
    yesterday_high = df["high"].iloc[-2]
    yesterday_low = df["low"].iloc[-2]

    inside = today_high <= yesterday_high and today_low >= yesterday_low
    if not inside:
        return False, 0.0

    # Quality: volume contraction
    vol_today = df["volume"].iloc[-1]
    vol_avg_10 = df["volume"].iloc[-11:-1].mean()
    vol_score = 1.0 - min(vol_today / vol_avg_10, 1.0) if vol_avg_10 > 0 else 0.5

    # Quality: prior trend (inside day after uptrend is more bullish)
    prior_return = (df["close"].iloc[-3] - df["close"].iloc[-8]) / df["close"].iloc[-8] if len(df) >= 8 else 0
    trend_score = 0.5 if prior_return > 0.02 else 0.2

    quality = (vol_score + trend_score) / 2
    return quality > 0.4, round(quality, 2)


def scan_patterns(kite: KiteConnect, symbols: List[str]) -> Dict[str, Dict]:
    """
    Scan all symbols for technical patterns.
    Returns dict mapping symbol -> pattern info.
    """
    results = {}
    for sym in symbols:
        try:
            df = fetch_ohlc(kite, sym, days=30)
            if df is None or len(df) < 15:
                continue

            patterns = []
            best_quality = 0.0

            # Check each pattern
            is_bull, q = detect_breakout(df)
            if is_bull:
                patterns.append("breakout")
                best_quality = max(best_quality, q)

            is_flag, q = detect_bull_flag(df)
            if is_flag:
                patterns.append("bull_flag")
                best_quality = max(best_quality, q)

            is_inside, q = detect_inside_day(df)
            if is_inside:
                patterns.append("inside_day")
                best_quality = max(best_quality, q)

            if patterns:
                # Tier classification
                if best_quality >= 0.75:
                    tier = "HIGH_CONVICTION"
                elif best_quality >= 0.50:
                    tier = "MODERATE"
                else:
                    tier = "SPECULATIVE"

                results[sym] = {
                    "patterns": patterns,
                    "best_quality": best_quality,
                    "tier": tier,
                }

        except Exception as e:
            logger.warning(f"Pattern scan error for {sym}: {e}")

    logger.info(f"Patterns found: {len(results)} stocks")
    return results