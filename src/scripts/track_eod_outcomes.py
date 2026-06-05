"""Track EOD prediction accuracy by comparing morning calls to actual closes."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
from loguru import logger

from src.data.daily_fetcher import fetch_daily
from src.models.daily_trainer import EOD_MODEL_DIR

LOG_FILE = Path("/app/logs/eod_accuracy.json")
PREDICTION_LOG = Path("/app/logs/eod_prediction_log.csv")


def fetch_today_close(symbol: str) -> float | None:
    """Fetch today's closing price for a symbol."""
    df = fetch_daily(symbol, days=5)
    if df is not None and not df.empty:
        return float(df["close"].iloc[-1])
    return None


def load_morning_predictions() -> dict:
    """Load the predictions that were saved this morning."""
    pred_file = Path("/app/logs/eod/predictions.json")
    if not pred_file.exists():
        logger.error("No morning predictions found")
        return {}
    with open(pred_file) as f:
        return json.load(f)


def track_outcomes():
    """
    Compare morning predictions with actual closes.
    Saves results to LOG_FILE and appends to PREDICTION_LOG.
    """
    preds = load_morning_predictions()
    if not preds:
        return

    results = {}
    outcomes = []
    today = datetime.now().strftime("%Y-%m-%d")

    for symbol, pred in preds.items():
        actual_close = fetch_today_close(symbol)
        if actual_close is None:
            continue

        last_close = pred.get("last_close", 0)
        predicted_dir = pred.get("direction", "HOLD")
        confidence = pred.get("confidence", 0)

        # Determine actual direction
        actual_return = (actual_close - last_close) / last_close if last_close > 0 else 0
        actual_dir = "BUY" if actual_return > 0.005 else "SELL" if actual_return < -0.005 else "HOLD"

        # Was the prediction correct?
        correct = (predicted_dir == actual_dir) or (predicted_dir == "HOLD" and actual_dir == "HOLD")

        outcomes.append({
            "date": today,
            "symbol": symbol,
            "predicted": predicted_dir,
            "actual": actual_dir,
            "confidence": confidence,
            "last_close": last_close,
            "actual_close": actual_close,
            "actual_return_pct": round(actual_return * 100, 2),
            "correct": correct,
        })

        results[symbol] = {
            "predicted": predicted_dir,
            "actual": actual_dir,
            "correct": correct,
            "confidence": confidence,
        }

    # Save detailed outcomes
    df = pd.DataFrame(outcomes)
    if PREDICTION_LOG.exists():
        df.to_csv(PREDICTION_LOG, mode="a", header=False, index=False)
    else:
        df.to_csv(PREDICTION_LOG, index=False)

    # Calculate summary metrics
    total = len(outcomes)
    correct_count = sum(1 for o in outcomes if o["correct"])
    win_rate = correct_count / total if total > 0 else 0

    buy_signals = [o for o in outcomes if o["predicted"] == "BUY"]
    sell_signals = [o for o in outcomes if o["predicted"] == "SELL"]
    buy_correct = sum(1 for o in buy_signals if o["correct"])
    sell_correct = sum(1 for o in sell_signals if o["correct"])

    summary = {
        "date": today,
        "total_predictions": total,
        "correct": correct_count,
        "win_rate": round(win_rate, 4),
        "buy_signals": len(buy_signals),
        "buy_correct": buy_correct,
        "sell_signals": len(sell_signals),
        "sell_correct": sell_correct,
        "per_symbol": results,
    }

    # Save summary
    # Keep rolling 90-day history
    history = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            history = json.load(f)
    history.append(summary)
    # Keep last 90 days
    history = history[-90:]
    with open(LOG_FILE, "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"EOD Tracking: {correct_count}/{total} correct ({win_rate:.1%})")
    logger.info(f"  BUY: {buy_correct}/{len(buy_signals)} | SELL: {sell_correct}/{len(sell_signals)}")

    return summary


if __name__ == "__main__":
    track_outcomes()