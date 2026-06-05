"""Signal generation – regime‑aware, confidence‑weighted, and directionally confirmed."""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass
class Signal:
    symbol: str
    side: str                     # BUY / SELL / HOLD
    entry_price: float
    qty: int
    stop_loss: float
    target1: float
    target2: float
    predicted_move: float
    confidence: float
    reason: str = ""


class Strategy:
    """
    Generates trading signals with:
    - Minimum signal strength (absolute predicted move > threshold).
    - Confidence‑weighted stop and target scaling.
    - Directional confirmation from prediction interval.
    - Regime‑adaptive risk parameters.
    - No internal position sizing (left to OrderManager).
    """

    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        # Minimum thresholds
        self.min_predicted_move_pct = 0.0015       # 15 bps absolute return
        self.min_confidence = 0.55
        self.max_spread_pct = 0.10                # percent units

        # Base risk‑reward parameters (adjusted by regime & confidence)
        self.atr_mult_stop_base = 2.0
        self.atr_mult_target1_base = 1.5
        self.atr_mult_target2_base = 3.0

    def generate_signal(
        self,
        symbol: str,
        current_price: float,
        atr: float,
        predicted_move: float,      # in rupees
        confidence: float,          # 0‑1
        sector: str = "",
        bid_ask_spread_pct: float = 0.02,
        correlation: float = 0.0,
        regime: str = "SIDEWAYS",   # BULL / BEAR / SIDEWAYS
        lower_bound: float = None,  # prediction lower bound (rupees)
        upper_bound: float = None,  # prediction upper bound (rupees)
    ) -> Signal:
        """
        Return a BUY, SELL, or HOLD signal.
        Profitability and exact sizing are validated by OrderManager.
        """
        if current_price <= 0 or atr <= 0:
            return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                          predicted_move, confidence, "Invalid price or ATR")

        # 1. Confidence and liquidity gates
        if confidence < self.min_confidence:
            return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                          predicted_move, confidence, f"Confidence {confidence:.2f}")
        if bid_ask_spread_pct > self.max_spread_pct:
            return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                          predicted_move, confidence, f"Spread {bid_ask_spread_pct:.3f}%")

        # 2. Minimum signal strength. ATR filter blocks tiny model moves that
        # are indistinguishable from normal 5-minute noise.
        move_abs = abs(predicted_move)
        min_move = max(current_price * self.min_predicted_move_pct, 0.25 * atr)
        if move_abs < min_move:
            return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                          predicted_move, confidence, f"Move ₹{move_abs:.4f} < ₹{min_move:.4f}")

        # 3. Direction and interval confirmation
        if predicted_move > 0:
            side = "BUY"
            if lower_bound is not None and lower_bound <= 0 and confidence < 0.75:
                return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                              predicted_move, confidence, "Interval crosses zero")
        elif predicted_move < 0:
            side = "SELL"
            if upper_bound is not None and upper_bound >= 0 and confidence < 0.75:
                return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                              predicted_move, confidence, "Interval crosses zero")
        else:
            return Signal(symbol, "HOLD", current_price, 0, 0, 0, 0,
                          predicted_move, confidence, "No predicted move")

        # 4. Regime-adaptive multipliers
        regime_stop_mult = self.atr_mult_stop_base
        regime_target1_mult = self.atr_mult_target1_base
        regime_target2_mult = self.atr_mult_target2_base

        if regime == "BULL" and side == "BUY":
            regime_target2_mult *= 1.2   # let winners run
        elif regime == "BEAR" and side == "SELL":
            regime_target2_mult *= 1.2
        elif regime == "SIDEWAYS":
            regime_target2_mult *= 0.8   # take profits quicker
            regime_target1_mult *= 0.9

        # 5. Confidence-weighted stop and target scaling
        conf_factor_stop = 1.0 - 0.3 * (confidence - self.min_confidence)
        conf_factor_target = 1.0 + 0.3 * (confidence - self.min_confidence)

        stop_mult = regime_stop_mult * conf_factor_stop
        target1_mult = regime_target1_mult * conf_factor_target
        target2_mult = regime_target2_mult * conf_factor_target

        # 6. Compute stops and targets. Targets stay on the correct side of
        # entry and are capped by both ATR and predicted magnitude.
        if side == "BUY":
            stop_loss = round(current_price - stop_mult * atr, 2)
            target1_move = min(target1_mult * atr, max(0.75 * move_abs, 0.5 * atr))
            target2_move = min(target2_mult * atr, max(1.25 * move_abs, target1_move * 1.5))
            target1 = round(current_price + target1_move, 2)
            target2 = round(max(target1 + 0.01, current_price + target2_move), 2)
        else:  # SELL
            stop_loss = round(current_price + stop_mult * atr, 2)
            target1_move = min(target1_mult * atr, max(0.75 * move_abs, 0.5 * atr))
            target2_move = min(target2_mult * atr, max(1.25 * move_abs, target1_move * 1.5))
            target1 = round(current_price - target1_move, 2)
            target2 = round(min(target1 - 0.01, current_price - target2_move), 2)

        # ── 7. Assemble signal (no quantity – OrderManager handles it) ──
        sig = Signal(
            symbol=symbol,
            side=side,
            entry_price=current_price,
            qty=0,   # will be set by OrderManager
            stop_loss=stop_loss,
            target1=target1,
            target2=target2,
            predicted_move=predicted_move,
            confidence=confidence,
            reason=(f"Move ₹{predicted_move:.2f}, conf {confidence:.2%}, "
                    f"regime {regime}")
        )
        logger.info(f"SIGNAL: {sig.side} {sig.symbol} | SL={sig.stop_loss} "
                    f"T1={sig.target1} T2={sig.target2} | {sig.reason}")
        return sig
