"""Vectorized backtesting engine for TETRIS strategies."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from src.data.fetcher import fetch_historical
from src.features.technical import add_all_features
from src.models.predictor import Predictor
from src.trading.cost_model import compute_round_trip_cost

RESULTS_DIR = Path("/app/logs/backtests")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run_backtest(
    symbol: str,
    start_date: str = "2026-01-01",
    end_date: str = "2026-05-24",
    capital: float = 100000,
    max_positions: int = 1,
) -> Dict:
    """
    Simple vectorized backtest for a single symbol.
    
    Strategy: Buy when predicted return > 0, Sell when < 0.
    Hold for 60 minutes (12 candles), then exit.
    """
    logger.info(f"Backtesting {symbol} from {start_date} to {end_date}")

    # Fetch data
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    df = fetch_historical(symbol, "5minute", max(days, 5))
    if df is None or len(df) < 500:
        logger.error(f"Not enough data for {symbol}")
        return {"error": "Insufficient data"}

    # Compute features
    feat = add_all_features(df)
    if feat.empty:
        return {"error": "Feature computation failed"}

    # Get predictions
    predictor = Predictor(symbol)
    predictions = []
    for i in range(0, len(feat) - 12, 6):  # Every 30 minutes
        window = feat.iloc[i:i+20]
        if len(window) < 20:
            continue
        try:
            pred = predictor.predict(window)
            if pred:
                predictions.append({
                    "time": feat.index[i],
                    "predicted_return": pred["predicted_return"],
                    "confidence": pred["confidence"],
                    "price": float(feat["close"].iloc[i]),
                })
        except Exception:
            continue

    if not predictions:
        return {"error": "No predictions generated"}

    # Simulate trades
    trades = []
    position = None
    cash = capital

    for i, pred in enumerate(predictions):
        # Exit logic
        if position is not None:
            bars_held = i - position["entry_index"]
            if bars_held >= 12:  # 60 minutes
                exit_price = predictions[i]["price"]
                pnl = (exit_price - position["entry_price"]) * position["qty"]
                if position["side"] == "SELL":
                    pnl = -pnl

                # Apply costs
                costs = compute_round_trip_cost(
                    symbol, position["qty"], position["entry_price"], exit_price
                )
                net_pnl = pnl - costs["total_cost"]

                trades.append({
                    "entry_time": str(position["time"]),
                    "exit_time": str(pred["time"]),
                    "side": position["side"],
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "qty": position["qty"],
                    "gross_pnl": round(pnl, 2),
                    "costs": round(costs["total_cost"], 2),
                    "net_pnl": round(net_pnl, 2),
                })
                cash += net_pnl
                position = None

        # Entry logic
        if position is None and pred["confidence"] > 0.5:
            qty = int(cash * 0.1 / pred["price"])  # 10% allocation
            if qty > 0:
                side = "BUY" if pred["predicted_return"] > 0 else "SELL"
                position = {
                    "time": pred["time"],
                    "entry_index": i,
                    "entry_price": pred["price"],
                    "side": side,
                    "qty": qty,
                }

    # Calculate metrics
    if not trades:
        return {"error": "No trades executed", "total_trades": 0}

    df_trades = pd.DataFrame(trades)
    total_trades = len(df_trades)
    winning_trades = len(df_trades[df_trades["net_pnl"] > 0])
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    total_pnl = df_trades["net_pnl"].sum()
    avg_win = df_trades[df_trades["net_pnl"] > 0]["net_pnl"].mean() if winning_trades > 0 else 0
    avg_loss = abs(df_trades[df_trades["net_pnl"] < 0]["net_pnl"].mean()) if winning_trades < total_trades else 0
    profit_factor = (winning_trades * avg_win) / ((total_trades - winning_trades) * avg_loss) if avg_loss > 0 else float("inf")

    # Compute equity curve
    df_trades["equity"] = capital + df_trades["net_pnl"].cumsum()
    peak = df_trades["equity"].cummax()
    drawdown = (df_trades["equity"] - peak) / peak * 100
    max_drawdown = abs(drawdown.min())

    result = {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "final_capital": round(capital + total_pnl, 2),
        "return_pct": round((total_pnl / capital) * 100, 2),
        "trades": trades[:10],  # First 10 trades for display
    }

    # Save result
    result_path = RESULTS_DIR / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Backtest complete: {total_trades} trades, {win_rate:.1%} WR, ₹{total_pnl:+.0f} P&L")
    return result


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    result = run_backtest(symbol)
    print(json.dumps(result, indent=2))