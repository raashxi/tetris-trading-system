"""1‑5 day momentum strategy — trend continuation on liquid stocks."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.data.daily_fetcher import fetch_daily


class MomentumStrategy:
    """
    Classic momentum strategy:
    - Filter: 5-day return > 3%, volume > 1.5× 20-day avg, RSI 55‑75
    - Entry: BUY next morning (simulated at 9:20 AM)
    - Exit:  Target +2.0% or 3:15 PM, whichever comes first
    - Stop:  -1.0% from entry
    - Max 3 positions, 5% capital each
    """

    def __init__(self):
        self.min_return_5d = 0.03       # 3%
        self.min_volume_ratio = 1.5     # >1.5x average
        self.rsi_lower = 55
        self.rsi_upper = 75
        self.target_pct = 0.02
        self.stop_pct = 0.01
        self.max_positions = 3

    def _compute_rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta).clip(lower=0).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def scan(self, symbol: str) -> Optional[Dict]:
        """Return a momentum signal dict or None."""
        df = fetch_daily(symbol, days=60)
        if df is None or len(df) < 30:
            return None

        close = df["close"]
        volume = df["volume"]
        ltp = float(close.iloc[-1])

        # 5‑day return
        ret_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] if len(close) >= 6 else 0
        if ret_5d < self.min_return_5d:
            return None

        # Volume ratio
        avg_vol_20 = volume.iloc[-21:-1].mean()
        vol_ratio = volume.iloc[-1] / avg_vol_20 if avg_vol_20 > 0 else 0
        if vol_ratio < self.min_volume_ratio:
            return None

        # RSI
        rsi = self._compute_rsi(close)
        if rsi < self.rsi_lower or rsi > self.rsi_upper:
            return None

        atr = float(df["high"].iloc[-1] - df["low"].iloc[-1])
        entry = ltp
        target = round(entry * (1 + self.target_pct), 2)
        stop_loss = round(entry * (1 - self.stop_pct), 2)

        return {
            "symbol": symbol,
            "side": "BUY",
            "strategy": "momentum",
            "entry_price": entry,
            "target": target,
            "stop_loss": stop_loss,
            "confidence": min(0.9, 0.5 + ret_5d * 5),
            "reason": f"5d ret={ret_5d:.1%}, RSI={rsi:.0f}, Vol={vol_ratio:.1f}x",
            "atr": atr,
            "ret_5d": ret_5d,
            "rsi": rsi,
        }

    def scan_all(self, symbols: List[str]) -> List[Dict]:
        """Scan multiple symbols and return top signals."""
        signals = []
        for sym in symbols:
            try:
                s = self.scan(sym)
                if s:
                    signals.append(s)
            except Exception as e:
                logger.warning(f"Momentum scan error {sym}: {e}")
        signals.sort(key=lambda x: x["confidence"], reverse=True)
        return signals[: self.max_positions]