"""Intraday scanner for volume spikes, breakouts, and reversal setups."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from kiteconnect import KiteConnect
from loguru import logger

from src.auth.session import get_kite_session
from src.data.fetcher import fetch_historical

ALERTS_FILE = Path("/app/logs/alerts.json")
WATCHLIST_FILE = Path("/app/logs/eod/watchlist.json")


def get_active_symbols() -> List[str]:
    """Get watchlist symbols or fall back to Nifty 50."""
    if WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.keys())[:30]
        return [d.get("symbol", "") for d in data[:30] if d.get("symbol")]
    from src.data.fetcher import NIFTY50_SYMBOLS
    return [s.replace(".NS", "") for s in NIFTY50_SYMBOLS[:30]]


def detect_volume_spike(df: pd.DataFrame) -> tuple[bool, float]:
    """Volume > 3x 20-period average."""
    if len(df) < 25:
        return False, 0
    latest_vol = df["volume"].iloc[-1]
    avg_vol = df["volume"].iloc[-21:-1].mean()
    if avg_vol <= 0:
        return False, 0
    ratio = latest_vol / avg_vol
    return ratio >= 3.0, round(ratio, 1)


def detect_breakout(df: pd.DataFrame) -> tuple[bool, float]:
    """Price breaking above 20-period high with volume confirmation."""
    if len(df) < 25:
        return False, 0
    latest_close = df["close"].iloc[-1]
    resistance = df["high"].iloc[-21:-1].max()
    if latest_close <= resistance * 1.005:
        return False, 0
    vol_ratio = df["volume"].iloc[-1] / df["volume"].iloc[-21:-1].mean()
    return vol_ratio >= 1.5, round((latest_close / resistance - 1) * 100, 2)


def detect_rsi_reversal(df: pd.DataFrame) -> tuple[bool, str]:
    """RSI crossing below 30 (oversold bounce) or above 70 (overbought)."""
    if len(df) < 30:
        return False, ""
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta).clip(lower=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = rsi.iloc[-1]
    prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else 50
    if pd.isna(latest_rsi):
        return False, ""
    if prev_rsi > 30 and latest_rsi <= 30:
        return True, "OVERSOLD_BOUNCE"
    if prev_rsi < 70 and latest_rsi >= 70:
        return True, "OVERBOUGHT"
    return False, ""


def scan_all() -> List[Dict]:
    """Run all detection scans on active symbols."""
    kite = get_kite_session()
    if not kite:
        logger.error("No Kite session for scanner")
        return []

    symbols = get_active_symbols()
    alerts = []

    for sym in symbols:
        try:
            df = fetch_historical(sym, "5minute", 5)
            if df is None or len(df) < 50:
                continue

            ltp = float(df["close"].iloc[-1])
            atr_val = ltp * 0.02

            # Volume spike
            vol_spike, vol_ratio = detect_volume_spike(df)
            if vol_spike:
                score = min(95, 60 + vol_ratio * 5)
                alerts.append({
                    "tier": 1 if vol_ratio >= 5 else 2,
                    "symbol": sym,
                    "message": f"Volume spike {vol_ratio}x normal — potential institutional interest",
                    "score": round(score, 1),
                    "tags": ["volume_spike", "momentum"],
                    "time": datetime.now().isoformat(),
                    "entry_zone": f"₹{ltp:.2f}",
                    "stop_loss": f"₹{ltp - 2*atr_val:.2f}",
                    "target": f"₹{ltp + 3*atr_val:.2f}",
                    "rr_ratio": round(3/2, 1),
                })

            # Breakout
            breakout, break_pct = detect_breakout(df)
            if breakout:
                score = min(95, 65 + break_pct * 2)
                alerts.append({
                    "tier": 1 if break_pct >= 2 else 2,
                    "symbol": sym,
                    "message": f"Breakout above resistance (+{break_pct}%) with volume confirmation",
                    "score": round(score, 1),
                    "tags": ["breakout", "resistance"],
                    "time": datetime.now().isoformat(),
                    "entry_zone": f"₹{ltp:.2f}",
                    "stop_loss": f"₹{ltp - 2*atr_val:.2f}",
                    "target": f"₹{ltp + 4*atr_val:.2f}",
                    "rr_ratio": 2.0,
                })

            # RSI reversal
            rsi_signal, rsi_type = detect_rsi_reversal(df)
            if rsi_signal:
                alerts.append({
                    "tier": 2 if rsi_type == "OVERSOLD_BOUNCE" else 3,
                    "symbol": sym,
                    "message": f"RSI {rsi_type.replace('_', ' ').title()} — potential reversal setup",
                    "score": 60.0 if rsi_type == "OVERSOLD_BOUNCE" else 45.0,
                    "tags": ["rsi", "reversal", rsi_type.lower()],
                    "time": datetime.now().isoformat(),
                    "entry_zone": f"₹{ltp:.2f}",
                    "stop_loss": f"₹{ltp - 2*atr_val:.2f}",
                    "target": f"₹{ltp + 3*atr_val:.2f}",
                    "rr_ratio": 1.5,
                })

            time.sleep(0.15)  # rate limit

        except Exception as e:
            logger.warning(f"Scanner error for {sym}: {e}")
            continue

    # Sort by score descending
    alerts.sort(key=lambda x: x["score"], reverse=True)

    # Save to file
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_FILE, "w") as f:
        json.dump({"alerts": alerts, "updated_at": datetime.now().isoformat()}, f, indent=2)

    logger.info(f"Scanner complete: {len(alerts)} alerts ({sum(1 for a in alerts if a['tier']==1)} T1, {sum(1 for a in alerts if a['tier']==2)} T2, {sum(1 for a in alerts if a['tier']==3)} T3)")
    return alerts


if __name__ == "__main__":
    scan_all()