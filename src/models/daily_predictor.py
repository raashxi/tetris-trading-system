"""Morning EOD predictor – run at 9:00 AM to predict today's closing direction."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

import pandas as pd
from loguru import logger

from src.data.daily_fetcher import fetch_daily
from src.data.fetcher import NIFTY50_SYMBOLS
from src.features.daily_features import add_daily_features
from src.features.daily_target import add_target
from src.models.daily_trainer import DailyTrainer, EOD_MODEL_DIR


class DailyPredictor:
    """Loads trained EOD model for a symbol and predicts today's close direction."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.trainer = DailyTrainer(symbol)
        self._loaded = self.trainer._load()

    @property
    def is_ready(self) -> bool:
        return self._loaded

    def predict(self) -> Optional[Dict[str, Any]]:
        """Fetch today's data, compute features, and return prediction."""
        if not self._loaded:
            logger.warning(f"No EOD model for {self.symbol}")
            return None

        # Fetch recent daily data (need enough for feature rolling windows)
        df = fetch_daily(self.symbol, days=300)
        if df is None or len(df) < 100:
            logger.warning(f"Not enough daily data for {self.symbol} prediction")
            return None

        # Fetch Nifty for market-relative features
        nifty_df = fetch_daily("NIFTY 50", days=300)

        # Compute features (no target needed for prediction, but function won't break)
        df = add_daily_features(df, nifty_df)

        if df.empty:
            return None

        # Predict using the latest row
        try:
            result = self.trainer.predict(df)
            if result is None:
                return None

            last_close = float(df["close"].iloc[-1])
            predicted_return = last_close * 0.01  # placeholder estimate from direction

            return {
                "symbol": self.symbol,
                "last_close": last_close,
                "direction": "BUY" if result["direction"] == 1 else "SELL",
                "probability": result["probability"],
                "confidence": result["confidence"],
                "win_rate": self.trainer.win_rate,
                "predicted_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Prediction failed for {self.symbol}: {e}")
            return None


def run_daily_predictions(max_symbols: int = 50) -> Dict[str, Dict]:
    """
    Run EOD predictions for all trained symbols.
    Call this at 9:00 AM from main.py or scheduler.
    
    Returns:
        Dict mapping symbol to prediction dict
    """
    symbols = [s.replace(".NS", "") for s in NIFTY50_SYMBOLS[:max_symbols]]
    # Only predict for symbols that have trained models
    trained = set(
        p.stem.split("_")[0]
        for p in Path(EOD_MODEL_DIR).glob("*.pkl")
        if p.suffix == ".pkl"
    )
    symbols = [s for s in symbols if s in trained]

    logger.info(f"Running EOD predictions for {len(symbols)} stocks…")

    results = {}
    for sym in symbols:
        try:
            predictor = DailyPredictor(sym)
            if predictor.is_ready:
                pred = predictor.predict()
                if pred:
                    results[sym] = pred
        except Exception as e:
            logger.error(f"EOD predict error for {sym}: {e}")

    # Summary
    buy_count = sum(1 for p in results.values() if p["direction"] == "BUY")
    sell_count = sum(1 for p in results.values() if p["direction"] == "SELL")
    logger.info(f"EOD predictions complete: {buy_count} BUY, {sell_count} SELL, {len(results)} total")
    return results


def get_morning_brief() -> str:
    """Generate a Telegram-ready morning summary."""
    predictions = run_daily_predictions()

    high_conf = {s: p for s, p in predictions.items() if p["confidence"] > 0.70}
    moderate = {s: p for s, p in predictions.items() if 0.40 < p["confidence"] <= 0.70}

    brief = f"📊 MORNING EOD BRIEF — {datetime.now().strftime('%d %b %Y')}\n"
    brief += f"━━━━━━━━━━━━━━━━━━━━━\n"
    brief += f"Total signals: {len(predictions)}\n"
    brief += f"High confidence (>70%): {len(high_conf)}\n"
    brief += f"Moderate confidence (40-70%): {len(moderate)}\n\n"

    if high_conf:
        brief += "🟢 HIGH CONFIDENCE:\n"
        for sym, p in list(high_conf.items())[:5]:
            brief += f"  {p['direction']} {sym} (conf: {p['confidence']:.0%}, wr: {p['win_rate']:.0%})\n"

    if moderate:
        brief += "\n🟡 MODERATE:\n"
        for sym, p in list(moderate.items())[:5]:
            brief += f"  {p['direction']} {sym} (conf: {p['confidence']:.0%})\n"

    return brief