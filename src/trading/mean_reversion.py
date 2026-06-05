"""Mean reversion strategy — RSI + VWAP based reversal signals."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from src.data.fetcher import fetch_historical


class MeanReversionStrategy:
    """
    Classic mean reversion using RSI and VWAP distance.
    
    Entry (BUY):
        - RSI(14) < 25
        - Price < 0.98 × VWAP (2% below VWAP)
        - Volume > 1.2× 20-period average (confirmation)
    
    Exit:
        - Target: +1.0% from entry
        - Stop loss: -0.5% from entry
        - Time stop: 45 minutes
    """

    def __init__(self):
        self.rsi_lower = 25
        self.rsi_upper = 75
        self.vwap_threshold = 0.98  # 2% below VWAP
        self.volume_ratio_min = 1.2
        self.target_pct = 0.01      # 1% profit target
        self.stop_pct = 0.005       # 0.5% stop loss
        self.max_hold_minutes = 45

    def compute_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Compute RSI for the latest candle."""
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta).clip(lower=0).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def compute_vwap(self, df: pd.DataFrame) -> float:
        """Compute rolling VWAP."""
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical_price * df["volume"]).sum() / df["volume"].sum()
        return float(vwap)

    def volume_ratio(self, volume: pd.Series, period: int = 20) -> float:
        """Latest volume vs. 20-period average."""
        avg_vol = volume.iloc[-period-1:-1].mean()
        latest_vol = volume.iloc[-1]
        return latest_vol / avg_vol if avg_vol > 0 else 1.0

    def scan(self, symbol: str, df: Optional[pd.DataFrame] = None) -> Optional[Dict]:
        """
        Check if a mean reversion signal exists for the given symbol.
        Returns a signal dict or None.
        """
        if df is None:
            df = fetch_historical(symbol, "5minute", 2)
        if df is None or len(df) < 30:
            return None

        close = df["close"]
        ltp = float(close.iloc[-1])
        rsi = self.compute_rsi(close)
        vwap = self.compute_vwap(df)
        vol_ratio = self.volume_ratio(df["volume"])

        # Check BUY conditions
        if rsi <= self.rsi_lower and ltp < vwap * self.vwap_threshold and vol_ratio >= self.volume_ratio_min:
            atr = float(df["high"].iloc[-1] - df["low"].iloc[-1])
            entry = ltp
            target = round(entry * (1 + self.target_pct), 2)
            stop_loss = round(entry * (1 - self.stop_pct), 2)

            return {
                "symbol": symbol,
                "side": "BUY",
                "strategy": "mean_reversion",
                "entry_price": entry,
                "target": target,
                "stop_loss": stop_loss,
                "confidence": round(1.0 - (rsi / self.rsi_lower) * 0.3, 2),
                "reason": f"RSI={rsi:.1f}, VWAP dist={((ltp/vwap)-1)*100:.1f}%, Vol={vol_ratio:.1f}x",
                "atr": atr,
                "rsi": rsi,
                "vwap": vwap,
                "vol_ratio": vol_ratio,
            }

        # Check SELL conditions (mean reversion on overbought)
        if rsi >= self.rsi_upper and ltp > vwap * (2 - self.vwap_threshold) and vol_ratio >= self.volume_ratio_min:
            atr = float(df["high"].iloc[-1] - df["low"].iloc[-1])
            entry = ltp
            target = round(entry * (1 - self.target_pct), 2)
            stop_loss = round(entry * (1 + self.stop_pct), 2)

            return {
                "symbol": symbol,
                "side": "SELL",
                "strategy": "mean_reversion",
                "entry_price": entry,
                "target": target,
                "stop_loss": stop_loss,
                "confidence": round(1.0 - ((100 - rsi) / (100 - self.rsi_upper)) * 0.3, 2),
                "reason": f"RSI={rsi:.1f}, VWAP dist={((ltp/vwap)-1)*100:.1f}%, Vol={vol_ratio:.1f}x",
                "atr": atr,
                "rsi": rsi,
                "vwap": vwap,
                "vol_ratio": vol_ratio,
            }

        return None

    def scan_all(self, symbols: list) -> list:
        """Scan multiple symbols for mean reversion signals."""
        signals = []
        for sym in symbols:
            try:
                signal = self.scan(sym)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.warning(f"MR scan error for {sym}: {e}")
        signals.sort(key=lambda x: x["confidence"], reverse=True)
        return signals