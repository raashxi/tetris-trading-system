"""Broker abstractions for paper and Zerodha live execution."""
from __future__ import annotations

import random
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from kiteconnect import KiteConnect
except Exception:  # pragma: no cover - keeps local tests importable without Kite.
    KiteConnect = object

from loguru import logger

from src.auth.session import get_kite_session
from src.trading.cost_model import COSTS


class Order:
    """Small normalized order record used by both paper and live brokers."""

    def __init__(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        order_type: str = "LIMIT",
        product: str = "MIS",
    ) -> None:
        self.order_id = str(uuid.uuid4())[:12]
        self.symbol = symbol
        self.side = side.upper()
        self.qty = int(qty)
        self.price = float(price or 0.0)
        self.order_type = order_type.upper()
        self.product = product
        self.status = "PENDING"
        self.filled_qty = 0
        self.filled_price = 0.0
        self.timestamp = datetime.now()
        self.message = ""


class Broker(ABC):
    """Abstract broker interface."""

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        order_type: str = "LIMIT",
        product: str = "MIS",
    ) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_positions(self) -> List[Dict]:
        ...

    @abstractmethod
    def get_account_balance(self) -> float:
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> str:
        ...

    @abstractmethod
    def get_order_fill(self, order_id: str) -> Tuple[int, float]:
        ...

    def update_market_data(self, quotes: Dict[str, dict]) -> None:
        """Optional hook used by paper execution for realistic market orders."""
        return None


class PaperBroker(Broker):
    """
    Deterministic enough for testing, conservative enough for paper trading.

    Positions are netted by symbol. A SELL against an existing BUY reduces or
    closes the long; it does not create an independent synthetic short unless
    quantity exceeds the long.
    """

    def __init__(
        self,
        capital: float = 100_000,
        *,
        rejection_rate: float = 0.0,
        delay_range: Tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.capital = float(capital)
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Dict] = {}
        self.market_data: Dict[str, dict] = {}
        self._rejection_rate = rejection_rate
        self._delay_range = delay_range

    def update_market_data(self, quotes: Dict[str, dict]) -> None:
        for symbol, quote in (quotes or {}).items():
            if quote and quote.get("ltp", 0) > 0:
                self.market_data[symbol] = quote

    def set_market_price(
        self,
        symbol: str,
        price: float,
        *,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        volume: Optional[float] = None,
    ) -> None:
        self.market_data[symbol] = {
            "ltp": float(price),
            "bid": float(bid if bid is not None else price),
            "ask": float(ask if ask is not None else price),
            "volume": volume or 0,
            "exchange_timestamp": datetime.now().isoformat(),
        }

    def _reference_price(self, symbol: str, side: str, price: float, order_type: str) -> float:
        quote = self.market_data.get(symbol, {})
        ltp = float(quote.get("ltp") or 0.0)
        bid = float(quote.get("bid") or 0.0)
        ask = float(quote.get("ask") or 0.0)

        if order_type == "MARKET":
            if side == "BUY" and ask > 0:
                return ask
            if side == "SELL" and bid > 0:
                return bid
            if ltp > 0:
                return ltp
            return float(price or 0.0)

        return float(price or ltp or 0.0)

    @staticmethod
    def _slippage_pct(order_type: str) -> float:
        base = COSTS.get("base_slippage_pct", COSTS.get("slippage_pct", 0.0005))
        return base * (1.5 if order_type == "MARKET" else 1.0)

    def _fill_price(self, symbol: str, side: str, price: float, order_type: str) -> float:
        def _fill_price(self, symbol: str, side: str, price: float, order_type: str) -> float:
            if order_type == "MARKET" and price <= 0:
                return 0.0   # will cause fill_price=0 → status rejection later
        ref = self._reference_price(symbol, side, price, order_type)
        if ref <= 0:
            return 0.0
        slip = max(0.0, random.gauss(self._slippage_pct(order_type), 0.0001))
        return round(ref * (1 + slip if side == "BUY" else 1 - slip), 2)

    def _net_position(self, symbol: str, side: str, qty: int, fill_price: float) -> None:
        signed_qty = qty if side == "BUY" else -qty
        current = self.positions.get(symbol)
        if current is None:
            self.positions[symbol] = {
                "symbol": symbol,
                "qty_signed": signed_qty,
                "qty": abs(signed_qty),
                "side": "BUY" if signed_qty > 0 else "SELL",
                "avg_price": fill_price,
            }
            return

        old_signed = int(current["qty_signed"])
        new_signed = old_signed + signed_qty
        if new_signed == 0:
            del self.positions[symbol]
            return

        same_direction = old_signed * signed_qty > 0
        if same_direction:
            old_abs = abs(old_signed)
            new_abs = abs(new_signed)
            avg = ((current["avg_price"] * old_abs) + (fill_price * qty)) / new_abs
        else:
            avg = current["avg_price"] if abs(new_signed) < abs(old_signed) else fill_price

        current.update({
            "qty_signed": new_signed,
            "qty": abs(new_signed),
            "side": "BUY" if new_signed > 0 else "SELL",
            "avg_price": round(avg, 2),
        })

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        order_type: str = "LIMIT",
        product: str = "MIS",
    ) -> Order:
        order = Order(symbol, side, qty, price, order_type, product)
        self.orders[order.order_id] = order

        if order.qty <= 0 or order.side not in {"BUY", "SELL"}:
            order.status = "REJECTED"
            order.message = "Invalid side or quantity"
            return order

        if random.random() < self._rejection_rate:
            order.status = "REJECTED"
            order.message = "Simulated rejection"
            logger.warning(f"Paper order rejected: {order.order_id}")
            return order

        if self._delay_range != (0.0, 0.0):
            time.sleep(random.uniform(*self._delay_range))

        fill_price = self._fill_price(order.symbol, order.side, order.price, order.order_type)
        if fill_price <= 0:
            order.status = "REJECTED"
            order.message = "No valid market/reference price"
            logger.warning(f"Paper order rejected with no valid price: {order.order_id}")
            return order

        fill_qty = order.qty
        if order.qty > 1000:
            fill_qty = max(1, int(order.qty * random.uniform(0.7, 1.0)))

        order.status = "FILLED" if fill_qty == order.qty else "PARTIALLY_FILLED"
        order.filled_qty = fill_qty
        order.filled_price = fill_price
        self._net_position(order.symbol, order.side, fill_qty, fill_price)
        logger.info(f"Paper fill: {order.side} {fill_qty} {order.symbol} @ {fill_price:.2f}")
        return order

    def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if order and order.status in {"PENDING", "OPEN"}:
            order.status = "CANCELLED"
            return True
        return False

    def get_positions(self) -> List[Dict]:
        return [
            {
                "symbol": p["symbol"],
                "side": p["side"],
                "qty": p["qty"],
                "avg_price": p["avg_price"],
            }
            for p in self.positions.values()
            if p["qty"] > 0
        ]

    def get_account_balance(self) -> float:
        return self.capital

    def get_order_status(self, order_id: str) -> str:
        order = self.orders.get(order_id)
        return order.status if order else "UNKNOWN"

    def get_order_fill(self, order_id: str) -> Tuple[int, float]:
        order = self.orders.get(order_id)
        if order and order.status in {"FILLED", "PARTIALLY_FILLED"}:
            return order.filled_qty, order.filled_price
        return 0, 0.0


class LiveZerodhaBroker(Broker):
    """Real Zerodha execution via Kite Connect."""

    def __init__(self) -> None:
        self.kite: Optional[KiteConnect] = get_kite_session()
        self._consecutive_failures = 0
        self._max_failures = 3
        self._circuit_breaker = False

    def _check_circuit(self) -> bool:
        if self._circuit_breaker:
            logger.warning("Circuit breaker active; order blocked")
            return False
        return True

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        order_type: str = "LIMIT",
        product: str = "MIS",
    ) -> Order:
        order = Order(symbol, side, qty, price, order_type, product)
        if not self._check_circuit() or not self.kite or qty <= 0:
            order.status = "REJECTED"
            return order

        try:
            kite_order_id = self.kite.place_order(
                variety="regular",
                exchange="NSE",
                tradingsymbol=symbol,
                transaction_type=side.upper(),
                quantity=int(qty),
                product=product,
                order_type=order_type.upper(),
                price=round(float(price), 2) if order_type.upper() != "MARKET" else 0,
            )
            order.order_id = str(kite_order_id["order_id"] if isinstance(kite_order_id, dict) else kite_order_id)
            order.status = "OPEN"
            self._consecutive_failures = 0
            logger.info(f"Live order placed: {order.order_id}")
            return order
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"Order failed: {e}")
            if self._consecutive_failures >= self._max_failures:
                self._circuit_breaker = True
                logger.error("Live execution circuit breaker activated")
            order.status = "REJECTED"
            order.message = str(e)
            return order

    def cancel_order(self, order_id: str) -> bool:
        if not self.kite:
            return False
        try:
            self.kite.cancel_order(variety="regular", order_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    def get_positions(self) -> List[Dict]:
        if not self.kite:
            return []
        try:
            positions = self.kite.positions()
            result = []
            for p in positions.get("net", []):
                qty = int(p.get("quantity", 0))
                if qty != 0:
                    result.append({
                        "symbol": p["tradingsymbol"],
                        "side": "BUY" if qty > 0 else "SELL",
                        "qty": abs(qty),
                        "avg_price": float(p.get("average_price", 0.0)),
                    })
            return result
        except Exception as e:
            logger.error(f"Positions fetch failed: {e}")
            return []

    def get_account_balance(self) -> float:
        if not self.kite:
            return 0.0
        try:
            margins = self.kite.margins()
            return float(margins.get("equity", {}).get("available", {}).get("cash", 0))
        except Exception as e:
            logger.error(f"Margin fetch failed: {e}")
            return 0.0

    def get_order_status(self, order_id: str) -> str:
        if not self.kite:
            return "UNKNOWN"
        try:
            for order in self.kite.orders():
                if str(order.get("order_id")) != str(order_id):
                    continue
                status = str(order.get("status", "")).upper()
                pending = int(order.get("pending_quantity", 0) or 0)
                filled = int(order.get("filled_quantity", 0) or 0)
                if status in {"COMPLETE", "FILLED"}:
                    return "FILLED"
                if status in {"REJECTED", "CANCELLED"}:
                    return "REJECTED"
                if filled > 0 and pending > 0:
                    return "PARTIALLY_FILLED"
                return "OPEN"
            return "UNKNOWN"
        except Exception as e:
            logger.error(f"Order status fetch failed: {e}")
            return "UNKNOWN"

    def get_order_fill(self, order_id: str) -> Tuple[int, float]:
        if not self.kite:
            return 0, 0.0
        try:
            for order in self.kite.orders():
                if str(order.get("order_id")) == str(order_id):
                    return int(order.get("filled_quantity", 0) or 0), float(order.get("average_price", 0.0) or 0.0)
            return 0, 0.0
        except Exception as e:
            logger.error(f"Order fill fetch failed: {e}")
            return 0, 0.0
