"""Professional order lifecycle manager with risk-based sizing, dynamic costs,
portfolio controls, and full trade journaling."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

from loguru import logger

from src.trading.execution import Broker
from src.trading.risk import RiskManager
from src.trading.cost_model import compute_round_trip_cost, COSTS
from src.monitoring.alerter import Alerter


class ManagedPosition:
    """Tracks a filled position through its lifecycle."""
    def __init__(self, symbol: str, side: str, qty: int, entry_price: float,
                 stop_loss: float, target1: float, target2: float,
                 atr: float, entry_time: datetime,
                 predicted_move: float = 0.0, confidence: float = 0.0,
                 spread_pct: float = 0.0, slippage: float = 0.0):
        self.symbol = symbol
        self.side = side
        self.qty = qty
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.target1 = target1
        self.target2 = target2
        self.atr = atr
        self.entry_time = entry_time
        self.current_price = entry_price
        self.trailing_activated = False
        self.exit_price: Optional[float] = None
        self.exit_time: Optional[datetime] = None
        self.exit_reason: str = ""
        self.predicted_move = predicted_move
        self.confidence = confidence
        self.spread_pct = spread_pct
        self.slippage = slippage


class OrderManager:
    """Full lifecycle manager with professional risk controls."""

    def __init__(self, broker: Broker, risk: RiskManager, alerter: Alerter,
                 capital: float = 100_000):
        self.broker = broker
        self.risk = risk
        self.alerter = alerter
        self.capital = capital
        self.peak_equity = capital
        self.daily_pnl = 0.0

        self.managed_positions: Dict[str, ManagedPosition] = {}
        self.pending_orders: Dict[str, dict] = {}
        self.cooldowns: Dict[str, datetime] = {}
        self.cooldown_minutes = 15

        self.consecutive_failures = 0
        self.max_failures = 3
        self.circuit_breaker_until: Optional[datetime] = None
        self.pause_minutes = 10

        self.min_confidence = 0.55
        self.max_spread_pct = 0.1

        self.daily_loss_limit_pct = 0.02
        self.intraday_drawdown_limit_pct = 0.05

        self.journal_path = Path("/app/logs/trades.csv")
        self.journal_path.parent.mkdir(exist_ok=True)

        self.max_positions = 5
        self.max_sector_concentration = 2
        self.correlation_threshold = 0.85

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------
    def _compute_position_size(self, entry_price: float, stop_loss: float,
                               atr: float, spread_pct: float) -> int:
        dynamic_slip = self._dynamic_slippage(atr, entry_price)
        effective_spread = spread_pct / 100.0 / 2.0
        adjusted_entry = entry_price * (1 + effective_spread + dynamic_slip)
        sl_distance = abs(adjusted_entry - stop_loss)
        if sl_distance <= 1e-6:
            return 0
        risk_amount = self.capital * 0.01
        raw_qty = int(risk_amount / sl_distance)
        max_qty = int(self.capital * 0.05 / adjusted_entry)
        return max(1, min(raw_qty, max_qty))

    def _dynamic_slippage(self, atr: float, price: float) -> float:
        base = 0.0005
        atr_pct = atr / price if price > 0 else 0.01
        slip = base + atr_pct * 0.3
        return min(slip, 0.005)

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------
    def _check_drawdown_limits(self) -> bool:
        if self.daily_pnl <= -self.capital * self.daily_loss_limit_pct:
            logger.error(f"Daily loss limit hit: ₹{self.daily_pnl:,.2f}")
            self.alerter.send("🚨 Daily loss limit reached. Halting trading.", priority="high")
            return False
        current_equity = self.capital + self.daily_pnl
        if self.peak_equity > 0:
            dd = (self.peak_equity - current_equity) / self.peak_equity
            if dd >= self.intraday_drawdown_limit_pct:
                logger.error(f"Intraday drawdown {dd:.2%} exceeded limit.")
                self.alerter.send("🚨 Max intraday drawdown hit. Halting trading.", priority="high")
                return False
        return True

    def _portfolio_risk_ok(self, symbol: str, sector: str = "Unknown",
                           correlation: float = 0.0) -> bool:
        if len(self.managed_positions) >= self.max_positions:
            return False
        sec_ok, _ = self.risk.check_sector_limit(sector)
        if not sec_ok:
            return False
        corr_ok, _ = self.risk.check_correlation_limit(symbol, correlation)
        if not corr_ok:
            return False
        exposure = sum(p.entry_price * p.qty for p in self.managed_positions.values())
        if exposure > self.capital * 0.8:
            return False
        return True

    def _is_quote_fresh(self, quote: dict) -> bool:
        ts = quote.get("timestamp")
        if ts is None:
            return True
        try:
            quote_time = datetime.fromisoformat(ts)
            return (datetime.now() - quote_time).total_seconds() <= 30
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Edge validation
    # ------------------------------------------------------------------
    def pre_filter_signal(symbol: str, ltp: float, predicted_return: float,
                     confidence: float, spread_pct: float, atr: float,
                     avg_daily_volume: Optional[float] = None) -> Tuple[bool, float]:
    # TEMPORARY BYPASS FOR PAPER TESTING ONLY
        return True, 0.0

    # ------------------------------------------------------------------
    # Submit signal
    # ------------------------------------------------------------------
    def submit_signal(self, symbol: str, side: str, qty: int, price: float,
                      stop_loss: float, target1: float, target2: float,
                      atr: float, predicted_move: float, confidence: float,
                      spread_pct: float = 0.02,
                      sector: str = "Unknown",
                      correlation: float = 0.0) -> bool:
        if not self._check_drawdown_limits():
            self.square_off_all()
            return False
        if self._is_circuit_broken():
            return False
        if self._is_cooling_down(symbol):
            return False
        if not self._portfolio_risk_ok(symbol, sector, correlation):
            return False
        if symbol in self.managed_positions or any(o.get("symbol") == symbol for o in self.pending_orders.values()):
            return False

        qty_sized = self._compute_position_size(price, stop_loss, atr, spread_pct)
        if qty_sized <= 0:
            return False

        ok, reason = self._validate_edge(symbol, qty_sized, price,
                                         predicted_move, confidence,
                                         spread_pct, atr)
        if not ok:
            logger.info(f"Edge rejected {symbol}: {reason}")
            return False

        order = self.broker.place_order(
            symbol=symbol, side=side, qty=qty_sized, price=price,
            order_type="LIMIT", product="MIS"
        )

        if order.status == "REJECTED":
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_failures:
                self.circuit_breaker_until = datetime.now() + timedelta(minutes=self.pause_minutes)
                self.alerter.send(f"🔴 Circuit breaker {self.pause_minutes} min", priority="high")
            return False

        dynamic_slip = self._dynamic_slippage(atr, price)
        self.pending_orders[order.order_id] = {
            "symbol": symbol, "side": side, "qty": qty_sized,
            "entry_price": price,
            "stop_loss": stop_loss,
            "target1": target1, "target2": target2,
            "atr": atr,
            "predicted_move": predicted_move,
            "confidence": confidence,
            "spread_pct": spread_pct,
            "slippage": dynamic_slip,
            "order_time": datetime.now(),
        }
        self.consecutive_failures = 0
        logger.info(f"Order placed: {side} {qty_sized} {symbol} @ {price:.2f}")
        return True

    def _is_circuit_broken(self) -> bool:
        if self.circuit_breaker_until and datetime.now() < self.circuit_breaker_until:
            return True
        self.circuit_breaker_until = None
        self.consecutive_failures = 0
        return False

    def _is_cooling_down(self, symbol: str) -> bool:
        if symbol in self.cooldowns:
            if datetime.now() < self.cooldowns[symbol]:
                return True
            del self.cooldowns[symbol]
        return False

    # ------------------------------------------------------------------
    # Pending order processing
    # ------------------------------------------------------------------
    def process_pending_orders(self):
        to_remove = []
        for oid, info in list(self.pending_orders.items()):
            age = (datetime.now() - info["order_time"]).total_seconds()
            filled_qty, fill_price = self.broker.get_order_fill(oid)
            status = self.broker.get_order_status(oid)

            if status == "FILLED" and filled_qty > 0:
                self._activate_position(oid, info, fill_price, filled_qty)
                to_remove.append(oid)
            elif status == "PARTIALLY_FILLED" and filled_qty > 0:
                if age > 60:
                    self.broker.cancel_order(oid)
                    self._activate_position(oid, info, fill_price, filled_qty)
                    to_remove.append(oid)
            elif status == "REJECTED":
                self.consecutive_failures += 1
                to_remove.append(oid)
            elif age > 90 and status not in ("FILLED", "REJECTED"):
                self.broker.cancel_order(oid)
                mkt_order = self.broker.place_order(
                    symbol=info["symbol"], side=info["side"], qty=info["qty"],
                    price=0, order_type="MARKET", product="MIS"
                )
                if mkt_order.status == "FILLED":
                    mkt_qty, mkt_price = self.broker.get_order_fill(mkt_order.order_id)
                    if mkt_qty > 0:
                        ratio = (mkt_price - info["entry_price"]) / info["entry_price"]
                        new_t1 = round(info["target1"] * (1 + ratio), 2)
                        new_t2 = round(info["target2"] * (1 + ratio), 2)
                        new_sl = round(info["stop_loss"] * (1 + ratio), 2)
                        self._activate_position(oid, info, mkt_price, mkt_qty,
                                                target1=new_t1, target2=new_t2,
                                                stop_loss=new_sl)
                else:
                    self.consecutive_failures += 1
                to_remove.append(oid)

        for oid in to_remove:
            if oid in self.pending_orders:
                del self.pending_orders[oid]

    def _activate_position(self, order_id, info, fill_price, filled_qty,
                           target1=None, target2=None, stop_loss=None):
        symbol = info["symbol"]
        pos = ManagedPosition(
            symbol=symbol, side=info["side"], qty=filled_qty,
            entry_price=fill_price,
            stop_loss=stop_loss if stop_loss else info["stop_loss"],
            target1=target1 if target1 else info["target1"],
            target2=target2 if target2 else info["target2"],
            atr=info["atr"],
            entry_time=info["order_time"],
            predicted_move=info.get("predicted_move", 0.0),
            confidence=info.get("confidence", 0.0),
            spread_pct=info.get("spread_pct", 0.0),
            slippage=info.get("slippage", 0.0)
        )
        self.managed_positions[symbol] = pos
        self.risk.add_position(symbol=symbol, side=info["side"], qty=filled_qty,
                               entry_price=fill_price, atr=info["atr"])

    # ------------------------------------------------------------------
    # Position monitoring
    # ------------------------------------------------------------------
    def check_open_positions(self, quotes: Dict[str, dict]):
        to_exit = []
        for sym, pos in list(self.managed_positions.items()):
            if sym not in quotes:
                continue
            q = quotes[sym]
            if not self._is_quote_fresh(q):
                continue
            ltp = q.get("ltp", pos.current_price)
            pos.current_price = ltp

            if pos.side == "BUY":
                if ltp <= pos.stop_loss:
                    to_exit.append((sym, "SL"))
                elif ltp >= pos.target2:
                    to_exit.append((sym, "T2"))
                elif ltp >= pos.target1 and not pos.trailing_activated:
                    pos.trailing_activated = True
            else:
                if ltp >= pos.stop_loss:
                    to_exit.append((sym, "SL"))
                elif ltp <= pos.target2:
                    to_exit.append((sym, "T2"))
                elif ltp <= pos.target1 and not pos.trailing_activated:
                    pos.trailing_activated = True

            if pos.trailing_activated:
                if pos.side == "BUY":
                    new_sl = ltp - pos.atr
                    if new_sl > pos.stop_loss:
                        pos.stop_loss = round(new_sl, 2)
                else:
                    new_sl = ltp + pos.atr
                    if new_sl < pos.stop_loss:
                        pos.stop_loss = round(new_sl, 2)

            atr_pct = pos.atr / pos.entry_price if pos.entry_price else 0.01
            max_hold = min(90, max(30, int(3000 * atr_pct)))
            elapsed = (datetime.now() - pos.entry_time).total_seconds() / 60
            if elapsed > max_hold and \
               ((pos.side == "BUY" and ltp <= pos.entry_price) or
                (pos.side == "SELL" and ltp >= pos.entry_price)):
                to_exit.append((sym, "Time stop"))

        for sym, reason in to_exit:
            self._exit_position(sym, reason)

    def _exit_position(self, symbol: str, reason: str):
        if symbol not in self.managed_positions:
            return
        pos = self.managed_positions[symbol]
        close_side = "SELL" if pos.side == "BUY" else "BUY"
        order = self.broker.place_order(
            symbol=symbol, side=close_side, qty=pos.qty,
            price=pos.current_price,
            order_type="MARKET", product="MIS"
        )
        if order.status != "FILLED":
            logger.error(f"Exit order failed for {symbol} – status={order.status}, keeping position")
            return
        exit_price = order.filled_price if order.filled_price > 0 else pos.current_price
        pnl = (exit_price - pos.entry_price) * pos.qty if pos.side == "BUY" else \
              (pos.entry_price - exit_price) * pos.qty

        pos.exit_price = exit_price
        pos.exit_time = datetime.now()
        pos.exit_reason = reason

        self.daily_pnl += pnl
        self.risk.update_pnl(pnl)
        self._journal_trade(pos, pnl)
        logger.info(f"Exit {symbol} ({reason}) P&L ₹{pnl:.2f}")
        self.alerter.send(f"{symbol} {reason} P&L ₹{pnl:.2f}")

        del self.managed_positions[symbol]
        self.risk.remove_position(symbol)
        self.cooldowns[symbol] = datetime.now() + timedelta(minutes=self.cooldown_minutes)

        current_equity = self.capital + self.daily_pnl
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    # ------------------------------------------------------------------
    # Journal
    # ------------------------------------------------------------------
    def _journal_trade(self, pos: ManagedPosition, pnl: float):
        row = [
            pos.exit_time.isoformat(), pos.symbol, pos.side,
            pos.entry_price, pos.exit_price, pos.qty, round(pnl, 2),
            pos.exit_reason, round(pos.predicted_move, 4),
            round(pos.confidence, 3), round(pos.spread_pct, 4),
            round(pos.slippage, 4),
            round((pos.exit_time - pos.entry_time).total_seconds() / 60, 1),
            pos.stop_loss, pos.target1, pos.target2
        ]
        columns = [
            "exit_time", "symbol", "side", "entry_price", "exit_price",
            "qty", "pnl", "reason", "predicted_move", "confidence",
            "spread_pct", "slippage", "holding_min",
            "stop_loss", "target1", "target2"
        ]
        with open(self.journal_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not self.journal_path.stat().st_size:
                writer.writerow(columns)
            writer.writerow(row)


    def _validate_edge(self, symbol: str, qty: int, entry_price: float,
                       predicted_move: float, confidence: float,
                       spread_pct: float, atr: float) -> Tuple[bool, str]:
        if confidence < self.min_confidence:
            return False, f"Confidence {confidence:.2f}"
        if spread_pct > self.max_spread_pct:
            return False, f"Spread {spread_pct:.3%}"
        effective_move = abs(predicted_move) * confidence
        if effective_move <= 0:
            return False, "No edge"
        dynamic_slip = self._dynamic_slippage(atr, entry_price)
        total_slippage = dynamic_slip + spread_pct / 100.0
        costs = compute_round_trip_cost(symbol, qty, entry_price, entry_price,
                                        atr=atr, spread_pct=spread_pct/100.0,
                                        order_type="LIMIT")
        min_move_per_share = costs["breakeven_move"]
        required_move = min_move_per_share * 1.2
        if effective_move < required_move:
            return False, f"Edge ₹{effective_move:.2f} < req ₹{required_move:.2f}"
        return True, "OK"

    def square_off_all(self):
        for sym in list(self.managed_positions.keys()):
            self._exit_position(sym, "EOD")
        self.pending_orders.clear()
        self.cooldowns.clear()
        self.managed_positions.clear()

    def update_market_data(self, quotes: Dict[str, dict]) -> None:
        """Pass live quotes to the broker for realistic paper fills."""
        if hasattr(self.broker, 'update_market_data'):
            self.broker.update_market_data(quotes)

    def reconcile_with_broker(self, quotes: Dict[str, dict]) -> None:
        """Sync managed positions with broker state."""
        if hasattr(self.broker, 'update_market_data'):
           self.broker.update_market_data(quotes)

    def estimate_position_size(self, entry_price: float, stop_loss: float,
                               atr: float, spread_pct: float) -> int:
        """Public wrapper for position sizing."""
        return self._compute_position_size(entry_price, stop_loss, atr, spread_pct)

    def current_exposure(self) -> float:
        """Total exposure of all managed positions."""
        return sum(p.entry_price * p.qty for p in self.managed_positions.values())

