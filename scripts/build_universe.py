"""Build tradeable universe from Nifty 200 based on price, volume, and data availability."""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

# Ensure src is in python path
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from src.auth.session import get_kite_session
from src.data.daily_fetcher import fetch_daily
from src.data.nifty200_symbols import NIFTY200_SYMBOLS

MAX_PRICE = 500.0
MIN_VOLUME = 500_000

OUTPUT_FILE = APP_ROOT / "config" / "tradeable_universe.yaml"


def main():
    kite = get_kite_session()
    if not kite:
        logger.error("No valid Kite session. Cannot build universe.")
        return

    logger.info(f"Scanning {len(NIFTY200_SYMBOLS)} Nifty 200 symbols (Filters: Price < ₹{MAX_PRICE}, Volume > {MIN_VOLUME:,})...")

    filtered_symbols = []

    for i, sym in enumerate(NIFTY200_SYMBOLS):
        time.sleep(0.3)  # Rate limiting
        try:
            df = fetch_daily(sym, days=30)
            if df is None or len(df) < 20:
                logger.warning(f"[{i+1}/{len(NIFTY200_SYMBOLS)}] {sym}: Insufficient daily data")
                continue

            last_close = float(df["close"].iloc[-1])
            avg_volume = float(df["volume"].iloc[-21:-1].mean())

            if last_close < MAX_PRICE and avg_volume > MIN_VOLUME:
                filtered_symbols.append(sym)
                logger.info(f"[{i+1}/{len(NIFTY200_SYMBOLS)}] ✅ {sym}: Price=₹{last_close:.2f}, AvgVol={avg_volume:,.0f}")
            else:
                logger.debug(f"[{i+1}/{len(NIFTY200_SYMBOLS)}] ❌ {sym}: Price=₹{last_close:.2f}, AvgVol={avg_volume:,.0f}")
        except Exception as e:
            logger.error(f"Error processing {sym}: {e}")

    logger.info(f"Universe filtering complete: {len(filtered_symbols)}/{len(NIFTY200_SYMBOLS)} symbols passed.")

    output_data = {
        "filter": {
            "max_price": MAX_PRICE,
            "min_volume": MIN_VOLUME,
            "generated_at": datetime.now().isoformat(),
        },
        "symbols": filtered_symbols,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Tradeable universe saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
