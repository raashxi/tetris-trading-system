"""Portfolio and trade risk controls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


MAX_POSITIONS = 5
MAX_SECTOR_CONCENTRATION = 2
DAILY_LOSS_LIMIT_PCT = 0.02
INTRADAY_DRAWDOWN_LIMIT_PCT = 0.05
RISK_PER_TRADE_PCT = 0.01
STOP_LOSS_ATR_MULT = 2.0
MAX_CAPITAL_PER_STOCK_PCT = 0.05
MAX_GROSS_EXPOSURE_PCT = 0.80
CORRELATION_THRESHOLD = 0.85
MAX_BID_ASK_SPREAD_PCT = 0.10  # percent units, 0.10 means 0.10%
MAX_ADV_PARTICIPATION_PCT = 0.01


@dataclass
class Position:
    symbol: str
    side: str
    qty: int
    entry_price: float
    entry_time: datetime
    stop_loss: float
    target1: float
    target2: float
    sector: str = "Unknown"
    atr: float = 0.0
    beta: float = 1.0
    current_price: float = field(default=0.0)

    @property
    def signed_qty(self) -> int:
        return self.qty if self.side.upper() == "BUY" else -self.qty

    @property
    def market_value(self) -> float:
        return abs(self.qty * (self.current_price or self.entry_price))

    @property
    def unrealized_pnl(self) -> float:
        price = self.current_price or self.entry_price
        if self.side.upper() == "BUY":
            return (price - self.entry_price) * self.qty
        return (self.entry_price - price) * self.qty


class RiskManager:
    """Enforces pre-trade and intraday portfolio risk limits."""

    def __init__(
        self,
        capital: float,
        daily_pnl: float = 0.0,
        *,
        max_positions: int = MAX_POSITIONS,
        max_sector_concentration: int = MAX_SECTOR_CONCENTRATION,
        daily_loss_limit_pct: float = DAILY_LOSS_LIMIT_PCT,
        intraday_drawdown_limit_pct: float = INTRADAY_DRAWDOWN_LIMIT_PCT,
        risk_per_trade_pct: float = RISK_PER_TRADE_PCT,
        max_capital_per_stock_pct: float = MAX_CAPITAL_PER_STOCK_PCT,
        max_gross_exposure_pct: float = MAX_GROSS_EXPOSURE_PCT,
        max_adv_participation_pct: float = MAX_ADV_PARTICIPATION_PCT,
    ) -> None:
        self.capital = float(capital)
        self.daily_pnl = float(daily_pnl)
        self.positions: List[Position] = []
        self.peak_equity = float(capital)
        self.max_positions = max_positions
        self.max_sector_concentration = max_sector_concentration
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.intraday_drawdown_limit_pct = intraday_drawdown_limit_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_capital_per_stock_pct = max_capital_per_stock_pct
        self.max_gross_exposure_pct = max_gross_exposure_pct
        self.max_adv_participation_pct = max_adv_participation_pct

    def mark_to_market(self, quotes: Dict[str, dict]) -> None:
        for pos in self.positions:
            quote = quotes.get(pos.symbol, {}) if quotes else {}
            ltp = float(quote.get("ltp") or 0.0)
            if ltp > 0:
                pos.current_price = ltp
        eq = self.equity()
        if eq > self.peak_equity:
            self.peak_equity = eq

    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions)

    def equity(self) -> float:
        return self.capital + self.daily_pnl + self.total_unrealized_pnl()

    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity()) / self.peak_equity)

    def gross_exposure(self) -> float:
        return sum(p.market_value for p in self.positions)

    def net_exposure(self) -> float:
        return sum(p.signed_qty * (p.current_price or p.entry_price) for p in self.positions)

    def sector_exposure(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for p in self.positions:
            result[p.sector] = result.get(p.sector, 0.0) + p.market_value
        return result

    def should_halt_intraday(self) -> bool:
        return self.drawdown_pct() >= self.intraday_drawdown_limit_pct

    def update_pnl(self, pnl_change: float) -> None:
        self.daily_pnl += pnl_change
        eq = self.equity()
        if eq > self.peak_equity:
            self.peak_equity = eq

    def can_open_position(
        self,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        qty: int = 0,
        price: float = 0.0,
        sector: str = "Unknown",
        *,
        correlation: float = 0.0,
        beta: float = 1.0,
        avg_daily_volume: Optional[float] = None,
    ) -> Tuple[bool, str]:
        if len(self.positions) >= self.max_positions:
            return False, f"Max positions ({self.max_positions}) reached"
        if self.daily_pnl <= -self.capital * self.daily_loss_limit_pct:
            return False, "Daily loss limit hit"
        if self.should_halt_intraday():
            return False, "Intraday drawdown limit hit"
        if symbol and self.has_position(symbol):
            return False, f"Already positioned in {symbol}"

        sector_ok, sector_reason = self.check_sector_limit(sector)
        if not sector_ok:
            return False, sector_reason

        corr_ok, corr_reason = self.check_correlation_limit(symbol or "", correlation)
        if not corr_ok:
            return False, corr_reason

        proposed_exposure = max(0, qty) * max(0.0, price)
        if proposed_exposure:
            if proposed_exposure > self.capital * self.max_capital_per_stock_pct:
                return False, "Per-symbol capital cap exceeded"
            if self.gross_exposure() + proposed_exposure > self.capital * self.max_gross_exposure_pct:
                return False, "Gross exposure cap exceeded"
            if avg_daily_volume and qty / avg_daily_volume > self.max_adv_participation_pct:
                return False, "ADV participation cap exceeded"

        return True, "OK"

    def check_sector_limit(self, sector: str) -> Tuple[bool, str]:
        count = sum(1 for p in self.positions if p.sector == sector)
        if count >= self.max_sector_concentration:
            return False, f"Sector '{sector}' limit reached"
        return True, "OK"

    def check_correlation_limit(self, new_symbol: str, correlation: float) -> Tuple[bool, str]:
        if correlation >= CORRELATION_THRESHOLD:
            return False, f"Correlation too high ({correlation:.2f}) with {new_symbol}"
        return True, "OK"

    def check_bid_ask_spread(self, spread_pct: float) -> Tuple[bool, str]:
        if spread_pct > MAX_BID_ASK_SPREAD_PCT:
            return False, f"Spread too wide ({spread_pct:.3f}%)"
        return True, "OK"

    def compute_position_size(
        self,
        price: float,
        atr: float,
        *,
        stop_loss: Optional[float] = None,
        max_position_value: Optional[float] = None,
    ) -> int:
        if price <= 0:
            return 0
        risk_per_share = abs(price - stop_loss) if stop_loss is not None else STOP_LOSS_ATR_MULT * atr
        if risk_per_share <= 0:
            return 0
        risk_qty = int((self.capital * self.risk_per_trade_pct) / risk_per_share)
        value_cap = max_position_value or (self.capital * self.max_capital_per_stock_pct)
        capital_qty = int(value_cap / price)
        return max(0, min(risk_qty, capital_qty))

    @staticmethod
    def compute_stop_loss(entry: float, atr: float, side: str) -> float:
        if side.upper() == "BUY":
            return round(entry - STOP_LOSS_ATR_MULT * atr, 2)
        return round(entry + STOP_LOSS_ATR_MULT * atr, 2)

    @staticmethod
    def compute_targets(entry: float, predicted_move: float, side: str) -> Tuple[float, float]:
        direction = 1 if side.upper() == "BUY" else -1
        move = abs(predicted_move)
        return (
            round(entry + direction * move, 2),
            round(entry + direction * 1.5 * move, 2),
        )

    def add_position(
        self,
        symbol: str,
        side: str,
        qty: int,
        entry_price: float,
        atr: float,
        sector: str = "Unknown",
        stop_loss: float = 0.0,
        target1: float = 0.0,
        target2: float = 0.0,
        beta: float = 1.0,
    ) -> Position:
        self.remove_position(symbol)
        pos = Position(
            symbol=symbol,
            side=side.upper(),
            qty=int(qty),
            entry_price=float(entry_price),
            entry_time=datetime.now(),
            stop_loss=float(stop_loss),
            target1=float(target1),
            target2=float(target2),
            sector=sector,
            atr=float(atr),
            beta=float(beta),
            current_price=float(entry_price),
        )
        self.positions.append(pos)
        return pos

    def remove_position(self, symbol: str) -> None:
        self.positions = [p for p in self.positions if p.symbol != symbol]

    def has_position(self, symbol: str) -> bool:
        return any(p.symbol == symbol for p in self.positions)

    def get_position_count(self) -> int:
        return len(self.positions)
