"""Kelly-based position sizing for EOD trades."""
from __future__ import annotations

from typing import Dict, Optional
import numpy as np
from loguru import logger


class PositionSizer:
    """
    Sizes EOD positions using:
    - Half-Kelly criterion
    - Capped at 10% of capital
    - Regime-adjusted multipliers
    """

    def __init__(self, capital: float):
        self.capital = capital
        self.kelly_fraction = 0.5  # Half-Kelly for safety
        self.max_allocation_pct = 0.10
        self.regime_multipliers = {
            "TRENDING_UP": 1.0,
            "TRENDING_DOWN": 0.5,
            "HIGH_VOL_CHOP": 0.3,
            "LOW_VOL_RANGE": 0.7,
            "SIDEWAYS": 0.5,
        }

    def calculate_kelly(
        self, win_prob: float, avg_win: float, avg_loss: float
    ) -> float:
        """
        Kelly formula: f = (p * b - q) / b
        where:
            p = win probability
            q = 1 - p (loss probability)
            b = avg_win / avg_loss (win/loss ratio)
        """
        if avg_loss <= 0 or win_prob <= 0:
            return 0.0

        b = avg_win / abs(avg_loss)
        q = 1.0 - win_prob
        kelly = (win_prob * b - q) / b
        return max(0.0, kelly)

    def size_position(
        self,
        entry_price: float,
        win_prob: float,
        avg_win: float = 0.01,
        avg_loss: float = 0.005,
        stop_loss: Optional[float] = None,
        regime: str = "SIDEWAYS",
    ) -> int:
        """
        Compute number of shares using Kelly criterion.

        Args:
            entry_price: Current stock price
            win_prob: Probability of winning (from model confidence)
            avg_win: Expected win size (as decimal, e.g., 0.01 = 1%)
            avg_loss: Expected loss size (as decimal, e.g., 0.005 = 0.5%)
            stop_loss: Pre-calculated stop loss price
            regime: Market regime for multiplier

        Returns:
            Number of shares to buy
        """
        # Kelly fraction of capital
        kelly_pct = self.calculate_kelly(win_prob, avg_win, avg_loss)
        kelly_pct *= self.kelly_fraction  # Half-Kelly

        # Apply regime multiplier
        multiplier = self.regime_multipliers.get(regime, 0.5)
        kelly_pct *= multiplier

        # Cap at max allocation
        allocation_pct = min(kelly_pct, self.max_allocation_pct)

        # Convert to rupees and shares
        capital_to_use = self.capital * allocation_pct
        quantity = int(capital_to_use / entry_price)

        # Risk-based cap if stop_loss provided
        if stop_loss and stop_loss > 0:
            risk_per_share = abs(entry_price - stop_loss)
            max_risk_capital = self.capital * 0.01  # 1% max risk per trade
            max_qty_by_risk = int(max_risk_capital / risk_per_share)
            quantity = min(quantity, max_qty_by_risk)

        logger.info(
            f"Sizing: {quantity} shares, allocation: ₹{capital_to_use:,.0f} "
            f"({allocation_pct:.1%}), regime: {regime}"
        )
        return max(1, quantity)

    def allocate_portfolio(
        self,
        predictions: Dict[str, Dict],
        sector_map: Dict[str, str],
        regime: str = "SIDEWAYS",
    ) -> Dict[str, Dict]:
        """
        Allocate capital across multiple EOD signals.
        Returns dict with symbol -> allocation details.
        """
        allocations = {}
        remaining_capital = self.capital * 0.80  # Max 80% total deployment

        # Sort by confidence (highest first)
        sorted_preds = sorted(
            predictions.items(),
            key=lambda x: x[1].get("confidence", 0),
            reverse=True,
        )

        for sym, pred in sorted_preds:
            if remaining_capital <= 0:
                break

            entry_price = pred.get("last_close", 0)
            if entry_price <= 0:
                continue

            win_prob = pred.get("confidence", 0.5)
            qty = self.size_position(
                entry_price=entry_price,
                win_prob=win_prob,
                regime=regime,
            )

            capital_used = entry_price * qty
            if capital_used > remaining_capital:
                qty = int(remaining_capital / entry_price)
                capital_used = entry_price * qty

            if qty > 0:
                allocations[sym] = {
                    "quantity": qty,
                    "entry_price": entry_price,
                    "capital_used": capital_used,
                    "allocation_pct": capital_used / self.capital,
                    "sector": sector_map.get(sym, "Unknown"),
                }
                remaining_capital -= capital_used

        logger.info(f"Portfolio allocated: {len(allocations)} positions")
        return allocations