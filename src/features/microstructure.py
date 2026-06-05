"""Order book microstructure features for signal confirmation."""
from __future__ import annotations

from typing import Dict, Optional


def compute_order_book_imbalance(quote: Dict) -> Optional[Dict]:
    """
    Compute order book imbalance metrics from a Kite quote.

    Returns:
        dict with imbalance, spread, depth_ratio, and pass/fail flags,
        or None if quote data is missing.
    """
    bid = quote.get("bid", 0)
    ask = quote.get("ask", 0)
    bid_qty = quote.get("bid_qty", 0)
    ask_qty = quote.get("ask_qty", 0)
    total_buy = quote.get("total_buy_qty", 0)
    total_sell = quote.get("total_sell_qty", 0)
    ltp = quote.get("ltp", 0)

    if ltp <= 0 or (bid_qty + ask_qty) == 0:
        return None

    # Order book imbalance: -1 (all sellers) to +1 (all buyers)
    imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)

    # Spread as percentage
    spread_pct = ((ask - bid) / ltp * 100) if bid > 0 and ask > 0 else 0.05

    # Depth imbalance
    depth_ratio = (total_buy / total_sell) if total_sell > 0 else 1.0

    # Confirmation logic
    buy_confirmed = imbalance > 0.2 and spread_pct < 0.1 and depth_ratio > 1.2
    sell_confirmed = imbalance < -0.2 and spread_pct < 0.1 and depth_ratio < 0.8

    return {
        "imbalance": round(imbalance, 4),
        "spread_pct": round(spread_pct, 4),
        "depth_ratio": round(depth_ratio, 2),
        "buy_confirmed": buy_confirmed,
        "sell_confirmed": sell_confirmed,
        "pass": buy_confirmed or sell_confirmed,
    }


def confirm_signal(side: str, quote: Dict) -> tuple[bool, str]:
    """
    Check if a signal should be accepted based on order book microstructure.

    Returns:
        (confirmed: bool, reason: str)
    """
    metrics = compute_order_book_imbalance(quote)
    if metrics is None:
        return False, "No order book data available"

    if side == "BUY" and not metrics["buy_confirmed"]:
        return False, f"OB rejected BUY (imb={metrics['imbalance']}, spread={metrics['spread_pct']}%)"
    if side == "SELL" and not metrics["sell_confirmed"]:
        return False, f"OB rejected SELL (imb={metrics['imbalance']}, spread={metrics['spread_pct']}%)"

    return True, f"OB confirmed (imb={metrics['imbalance']}, spread={metrics['spread_pct']}%)"