"""Realistic cost model for Indian equity intraday trading.
Includes dynamic slippage, spread impact, market impact, and order-type adjustments.
"""
from __future__ import annotations

from typing import Dict, Literal, Optional
import math

# Zerodha intraday cost structure (2024-25) – static components
COSTS = {
    "brokerage_pct": 0.0003,           # 0.03 % or ₹20 whichever lower
    "brokerage_flat": 20.0,            # ₹20 max per trade
    "stt_intraday_sell_pct": 0.00025,  # 0.025 % on sell side
    "nse_transaction_pct": 0.0000297,  # NSE turnover charge
    "sebi_charges_per_crore": 10.0,    # ₹10 per crore turnover
    "gst_pct": 0.18,                   # 18 % on (brokerage + exchange charges)
    "stamp_duty_buy_pct": 0.00015,     # 0.015 % on buy side
    "clearing_charges_pct": 0.000002,  # 0.0002 %
    "base_slippage_pct": 0.0005,       # 5 bps baseline execution slippage
    "slippage_pct": 0.0005,            # backward-compatible alias
    "max_slippage_pct": 0.005,         # 50 bps cap for normal conditions
}


def estimate_slippage_pct(
    price: float,
    *,
    atr: Optional[float] = None,
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT",
) -> float:
    """Return decimal slippage estimate, e.g. 0.0005 means 5 bps."""
    if price <= 0:
        return COSTS["max_slippage_pct"]
    atr_pct = (atr / price) if atr and atr > 0 else 0.0
    slip = COSTS["base_slippage_pct"] + 0.3 * atr_pct
    if order_type == "MARKET":
        slip *= 1.5
    return min(max(slip, COSTS["base_slippage_pct"]), COSTS["max_slippage_pct"])


def compute_all_in_cost(
    symbol: str,
    qty: int,
    price: float,
    side: Literal["BUY", "SELL"],
    exchange: str = "NSE",
    *,
    atr: Optional[float] = None,
    spread_pct: float = 0.0,
    volume: Optional[float] = None,        # traded volume (shares)
    avg_daily_volume: Optional[float] = None,
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT",
) -> Dict:
    """
    Compute all costs for a single trade (buy or sell).

    Dynamic adjustments:
    - Slippage: base 5 bps + 0.3 * ATR_pct. Capped at 0.5 %.
    - Spread: pass in half‑spread (e.g. (ask‑bid)/2) as spread_pct.
    - Market impact: uses sqrt(qty / ADV) * volatility factor.
    - Market orders pay full spread + higher slippage.
    """
    turnover = qty * price

    # --- Brokerage (Zerodha cap) ---
    brokerage_pct_cost = turnover * COSTS["brokerage_pct"]
    brokerage = min(brokerage_pct_cost, COSTS["brokerage_flat"])

    # --- Exchange transaction charge ---
    if exchange.upper() == "BSE":
        exchange_txn = turnover * 0.0000375
    else:
        exchange_txn = turnover * COSTS["nse_transaction_pct"]

    # --- SEBI charges ---
    sebi = (turnover / 10_000_000) * COSTS["sebi_charges_per_crore"]

    # --- Clearing charges ---
    clearing = turnover * COSTS["clearing_charges_pct"]

    # --- GST ---
    gst = (brokerage + exchange_txn) * COSTS["gst_pct"]

    # --- Stamp duty (buy only) ---
    stamp_duty = 0.0
    if side.upper() == "BUY":
        stamp_duty = turnover * COSTS["stamp_duty_buy_pct"]

    # --- STT (sell only, intraday) ---
    stt = 0.0
    if side.upper() == "SELL":
        stt = turnover * COSTS["stt_intraday_sell_pct"]

    # ========== DYNAMIC COSTS ==========
    # 1. Spread impact (half‑spread for limit orders, full spread for market)
    if order_type == "MARKET":
        effective_spread_pct = spread_pct
    else:
        effective_spread_pct = spread_pct / 2.0   # limit orders may trade inside spread
    spread_cost = turnover * effective_spread_pct

    # 2. Dynamic slippage
    dynamic_slip = estimate_slippage_pct(price, atr=atr, order_type=order_type)

    slippage = turnover * dynamic_slip

    # 3. Market impact (non‑linear)
    impact = 0.0
    participation_rate = 0.0
    impact_pct = 0.0
    if avg_daily_volume and avg_daily_volume > 0:
        participation_rate = qty / avg_daily_volume
        # Simple Kyle model: impact = spread * sqrt(participation) * volatility factor
        if atr and price > 0:
            vol_factor = atr / price
        else:
            vol_factor = 0.02
        intraday_volume_penalty = 1.0
        if volume and volume > 0:
            intraday_volume_penalty = min(3.0, max(1.0, qty / volume))
        impact_pct = vol_factor * math.sqrt(participation_rate) * intraday_volume_penalty
        impact = turnover * impact_pct

    # --- Total cost ---
    total_cost = (brokerage + exchange_txn + sebi + clearing + gst +
                  stamp_duty + stt + spread_cost + slippage + impact)
    cost_pct = total_cost / turnover if turnover > 0 else 0.0

    return {
        "turnover": round(turnover, 2),
        "brokerage": round(brokerage, 2),
        "exchange_charges": round(exchange_txn, 2),
        "sebi_charges": round(sebi, 2),
        "clearing_charges": round(clearing, 2),
        "gst": round(gst, 2),
        "stamp_duty": round(stamp_duty, 2),
        "stt": round(stt, 2),
        "spread_cost": round(spread_cost, 2),
        "slippage": round(slippage, 2),
        "impact": round(impact, 2),
        "impact_pct": round(impact_pct * 100, 6),
        "participation_rate": round(participation_rate * 100, 6),
        "total_cost": round(total_cost, 2),
        "cost_pct": round(cost_pct * 100, 6),
    }


def compute_round_trip_cost(
    symbol: str,
    qty: int,
    buy_price: float,
    sell_price: float,
    exchange: str = "NSE",
    *,
    atr: Optional[float] = None,
    spread_pct: float = 0.0,
    volume: Optional[float] = None,
    avg_daily_volume: Optional[float] = None,
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT",
) -> Dict:
    """
    Full round‑trip cost with dynamic parameters.
    Returns break‑even and net P&L.
    """
    buy = compute_all_in_cost(symbol, qty, buy_price, "BUY", exchange,
                              atr=atr, spread_pct=spread_pct,
                              volume=volume, avg_daily_volume=avg_daily_volume,
                              order_type=order_type)
    sell = compute_all_in_cost(symbol, qty, sell_price, "SELL", exchange,
                               atr=atr, spread_pct=spread_pct,
                               volume=volume, avg_daily_volume=avg_daily_volume,
                               order_type=order_type)

    total_cost = buy["total_cost"] + sell["total_cost"]
    gross_pnl = (sell_price - buy_price) * qty
    net_pnl = gross_pnl - total_cost
    turnover = buy["turnover"] + sell["turnover"]

    breakeven_move = total_cost / qty if qty > 0 else 0.0

    return {
        "buy_costs": buy,
        "sell_costs": sell,
        "total_cost": round(total_cost, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "breakeven_move": round(breakeven_move, 4),
        "cost_pct": round(total_cost / turnover * 100, 6) if turnover > 0 else 0.0,
    }


def minimum_move_for_profit(
    symbol: str,
    qty: int,
    entry_price: float,
    exchange: str = "NSE",
    *,
    atr: Optional[float] = None,
    spread_pct: float = 0.0,
    volume: Optional[float] = None,
    avg_daily_volume: Optional[float] = None,
    profit_buffer_pct: float = 0.2,   # 20 % above breakeven required
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT",
) -> float:
    """
    Minimum price move (in ₹) to achieve profit after ALL costs + buffer.
    The profit buffer ensures we don't take zero‑edge trades.
    """
    costs = compute_round_trip_cost(symbol, qty, entry_price, entry_price,
                                    exchange=exchange, atr=atr,
                                    spread_pct=spread_pct,
                                    volume=volume,
                                    avg_daily_volume=avg_daily_volume,
                                    order_type=order_type)
    base_move = costs["breakeven_move"]
    # Add buffer: minimum move = breakeven * (1 + buffer)
    return round(base_move * (1 + profit_buffer_pct), 4)
