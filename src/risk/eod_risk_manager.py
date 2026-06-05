"""Portfolio-level risk manager for EOD positions."""
from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import numpy as np
from loguru import logger


class EODRiskManager:
    """
    Controls EOD portfolio risk:
    - Max 2 positions
    - 1 per sector
    - Correlation < 0.80 with existing
    - Daily VaR (95%) ≤ 3% of capital
    - Max 10% capital per position
    """

    def __init__(self, capital: float):
        self.capital = capital
        self.max_positions = 2
        self.max_per_position_pct = 0.10
        self.max_sector_positions = 1
        self.correlation_limit = 0.80
        self.daily_var_limit_pct = 0.03

    def can_add_position(
        self,
        symbol: str,
        sector: str,
        existing_positions: List[Dict],
        correlation_score: float = 0.0,
    ) -> Tuple[bool, str]:
        """Check if a new EOD position can be added."""
        # Position count
        if len(existing_positions) >= self.max_positions:
            return False, f"Max {self.max_positions} EOD positions reached"

        # Sector concentration
        sector_count = sum(1 for p in existing_positions if p.get("sector") == sector)
        if sector_count >= self.max_sector_positions:
            return False, f"Sector '{sector}' limit reached"

        # Capital allocation
        allocated = sum(p.get("capital_used", 0) for p in existing_positions)
        new_allocation = self.capital * self.max_per_position_pct
        if allocated + new_allocation > self.capital * 0.80:
            return False, "Total EOD exposure would exceed 80%"

        # Correlation check
        if correlation_score > self.correlation_limit:
            return False, f"Correlation {correlation_score:.2f} too high"

        return True, "OK"

    def check_portfolio_var(
        self, positions: List[Dict], confidence: float = 0.95
    ) -> Tuple[bool, float]:
        """
        Compute portfolio-level Value at Risk.
        Simplified: uses sum of individual position risks.
        """
        if not positions:
            return True, 0.0

        total_var = 0.0
        for p in positions:
            # Individual VaR = position_value * predicted_volatility * z_score
            pos_value = p.get("capital_used", 0)
            volatility = p.get("predicted_volatility", 0.02)  # default 2% daily vol
            z_score = 1.65  # 95% confidence
            position_var = pos_value * volatility * z_score
            total_var += position_var

        portfolio_var_pct = total_var / self.capital if self.capital > 0 else 0.0
        is_safe = portfolio_var_pct <= self.daily_var_limit_pct

        if not is_safe:
            logger.warning(f"Portfolio VaR {portfolio_var_pct:.2%} exceeds limit")

        return is_safe, portfolio_var_pct

    def calculate_position_risk(
        self, entry_price: float, stop_loss: float, quantity: int
    ) -> float:
        """Calculate max loss for a position."""
        risk_per_share = abs(entry_price - stop_loss)
        total_risk = risk_per_share * quantity
        return total_risk / self.capital if self.capital > 0 else 0.0

    def daily_drawdown_check(self, current_pnl: float) -> Tuple[bool, str]:
        """Halt if daily loss exceeds 2%."""
        loss_pct = abs(current_pnl) / self.capital if current_pnl < 0 else 0.0
        if loss_pct >= 0.02:
            return False, f"Daily loss limit hit: {loss_pct:.2%}"
        return True, "OK"