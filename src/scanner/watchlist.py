"""Dynamic watchlist builder – scans NSE for high-potential stocks."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from kiteconnect import KiteConnect
from loguru import logger

from src.auth.session import get_kite_session
from src.data.fetcher import NIFTY50_SYMBOLS

# Additional large-cap / liquid stocks (Nifty Next 50 composition)
NIFTY_NEXT_50 = [
    "ABB", "ADANIENSOL", "ADANIGREEN", "AMBUJACEM", "AUROPHARMA",
    "BANKBARODA", "BERGEPAINT", "BHARATFORG", "BIOCON", "BOSCHLTD",
    "CADILAHC", "CANBK", "COFORGE", "COLPAL", "CONCOR",
    "CUMMINSIND", "DABUR", "DLF", "GAIL", "GODREJCP",
    "GODREJPROP", "HAL", "HAVELLS", "HINDZINC", "ICICIGI",
    "ICICIPRULI", "INDIGO", "IOC", "JINDALSTEL", "JUBLFOOD",
    "LUPIN", "MARICO", "MPHASIS", "MRF", "MUTHOOTFIN",
    "NAUKRI", "NTPC", "PAGEIND", "PATANJALI", "PIDILITIND",
    "POLYCAB", "SAIL", "SBICARD", "SBIINSURANCE", "SHREECEM",
    "SRF", "TORNTPHARM", "TRENT", "UPL", "VEDL"
]

# Minimum filters
MIN_PRICE = 50.0
MIN_AVG_VOLUME = 500_000


def get_instruments(kite: KiteConnect) -> List[Dict]:
    """Fetch and cache NSE instruments."""
    try:
        instruments = kite.instruments("NSE")
        logger.info(f"Fetched {len(instruments)} NSE instruments")
        return instruments
    except Exception as e:
        logger.error(f"Instruments fetch failed: {e}")
        return []


def filter_by_liquidity(instruments: List[Dict]) -> List[str]:
    """Filter stocks by price and volume."""
    candidates = []
    for ins in instruments:
        try:
            last_price = ins.get("last_price", 0)
            volume = ins.get("volume", 0)
            symbol = ins.get("tradingsymbol", "")

            if last_price >= MIN_PRICE and volume >= MIN_AVG_VOLUME:
                candidates.append({
                    "symbol": symbol,
                    "last_price": last_price,
                    "volume": volume,
                    "turnover": last_price * volume,
                })
        except Exception:
            continue

    # Sort by turnover (liquidity)
    candidates.sort(key=lambda x: x["turnover"], reverse=True)
    logger.info(f"Found {len(candidates)} liquid stocks")
    return [c["symbol"] for c in candidates]

def fetch_momentum_scores(kite: KiteConnect, symbols: List[str]) -> Dict[str, float]:
    """
    Compute a simple momentum score from the last 5, 10, and 21 daily returns.
    Returns a dict mapping symbol -> score (0-100).
    """
    scores = {}
    today = datetime.now()
    from_date = today - timedelta(days=60)   # enough for 21d window

    for sym in symbols:
        try:
            # Get instrument token
            instruments = kite.instruments("NSE")
            token = None
            for ins in instruments:
                if ins["tradingsymbol"] == sym:
                    token = ins["instrument_token"]
                    break
            if token is None:
                continue

            data = kite.historical_data(
                instrument_token=token,
                from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
                to_date=today.strftime("%Y-%m-%d %H:%M:%S"),
                interval="day",
                continuous=False,
                oi=False,
            )

            if not data or len(data) < 25:
                continue

            closes = [d["close"] for d in data]
            ret_5d = (closes[-1] / closes[-6] - 1) if len(closes) >= 6 else 0
            ret_10d = (closes[-1] / closes[-11] - 1) if len(closes) >= 11 else 0
            ret_21d = (closes[-1] / closes[-22] - 1) if len(closes) >= 22 else 0

            # Weighted score (more weight to recent)
            score = (0.5 * ret_5d + 0.3 * ret_10d + 0.2 * ret_21d)
            scores[sym] = min(max(score * 1000, 0), 100)  # scale to 0-100
            time.sleep(0.2)  # rate limit
        except Exception as e:
            logger.warning(f"Momentum failed for {sym}: {e}")
            time.sleep(0.5)
    return scores


def build_watchlist(
    kite: Optional[KiteConnect] = None,
    extra_symbols: Optional[List[str]] = None,
    max_stocks: int = 100,
) -> Dict[str, Dict]:
    """
    Main entry point: build ranked watchlist.

    Steps:
    1. Base symbols: Nifty 50 + Nifty Next 50
    2. Filter by liquidity (price > 50, avg vol > 5L)
    3. Score by momentum (5/10/21 day returns)
    4. Merge and rank
    5. Return top 'max_stocks' with scores
    """
    if kite is None:
        kite = get_kite_session()
    if kite is None:
        logger.error("No Kite session for watchlist")
        return {}

    # Combine base symbols
    base_symbols = [s.replace(".NS", "") for s in NIFTY50_SYMBOLS]
    all_symbols = list(dict.fromkeys(base_symbols + NIFTY_NEXT_50))

    if extra_symbols:
        all_symbols.extend(extra_symbols)

    # Fetch instruments and filter liquid
    instruments = get_instruments(kite)
    liquid_symbols = filter_by_liquidity(instruments)
    liquid_set = set(liquid_symbols)
    candidates = [s for s in all_symbols if s in liquid_set]

    logger.info(f"Candidates after liquidity filter: {len(candidates)}")

    # Momentum scoring
    scores = fetch_momentum_scores(kite, candidates)

    # Build ranked list
    ranked = []
    for sym in candidates:
        score = scores.get(sym, 0)
        ranked.append({
            "symbol": sym,
            "score": score,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    result = {}
    for item in ranked[:max_stocks]:
        result[item["symbol"]] = {
            "score": item["score"],
            "source": "momentum_scan",
        }

    # Always include Nifty 50 even if score is low
    for sym in base_symbols:
        if sym not in result:
            result[sym] = {"score": 50.0, "source": "nifty50"}

    logger.info(f"Watchlist built: {len(result)} stocks")
    return result