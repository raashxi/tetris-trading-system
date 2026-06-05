"""
Production orchestrator – regimes, signal ranking, adaptive caching,
capital‑aware pacing, and full lifecycle integration.
"""
from __future__ import annotations

import sys, os, time, signal
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from src.data.calendar import is_market_open, MarketStatus, minutes_to_close
from src.data.fetcher import fetch_historical, fetch_live_quote, NIFTY50_SYMBOLS
from src.features.technical import add_all_features
from src.trading.risk import RiskManager
from src.trading.strategy import Strategy
from src.trading.execution import PaperBroker, LiveZerodhaBroker
from src.trading.order_manager import OrderManager
from src.trading.cost_model import minimum_move_for_profit
from src.models.predictor import Predictor
from src.monitoring.alerter import Alerter

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
APP_ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).resolve().parent.parent))
STOP_FILE = Path(os.environ.get("STOP_FILE", APP_ROOT / "STOP"))
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models" if Path("/app/models").exists() else APP_ROOT / "models"))


def load_settings() -> dict:
    path = APP_ROOT / "config" / "settings.yaml"
    if not path.exists():
        return {}
    with path.open("r") as f:
        return yaml.safe_load(f) or {}


SETTINGS = load_settings()
MODE = os.environ.get("TRADING_MODE", SETTINGS.get("trading", {}).get("mode", "PAPER"))
CAPITAL = float(os.environ.get("TRADING_CAPITAL", 1_00_000))

# ---------------------------------------------------------------------------
# LOGGING & ALERTING
# ---------------------------------------------------------------------------
logger.add(
    "logs/trading_bot_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
)
alerter = Alerter()


def load_sector_map() -> Dict[str, str]:
    path = APP_ROOT / "config" / "nifty50_symbols.yaml"
    if not path.exists():
        return {}
    try:
        with path.open("r") as f:
            data = yaml.safe_load(f) or {}
        return {row["symbol"]: row.get("sector", "Unknown") for row in data.get("symbols", [])}
    except Exception as exc:
        logger.warning(f"Could not load sector map: {exc}")
        return {}


SECTOR_MAP = load_sector_map()


# ---------------------------------------------------------------------------
# POSITION SIZING HELPER (mirrors OrderManager logic for pre‑filter)
# ---------------------------------------------------------------------------
def compute_position_size(entry_price: float, stop_loss: float,
                          atr: float, spread_pct: float) -> int:
    """
    Risk‑based sizing: 1% capital risk, adjusted for expected slip + spread.
    Used by pre‑filter to estimate realistic quantity, not executed.
    """
    if entry_price <= 0:
        return 0
    dynamic_slip = 0.0005 + min(0.3 * (atr / entry_price), 0.005)
    half_spread = spread_pct / 100.0 / 2.0
    adjusted_entry = entry_price * (1 + half_spread + dynamic_slip)
    sl_distance = abs(adjusted_entry - stop_loss)
    if sl_distance <= 1e-6:
        return 0
    risk_amount = CAPITAL * 0.01
    raw_qty = int(risk_amount / sl_distance)
    max_qty = int(CAPITAL * 0.05 / adjusted_entry)
    return max(1, min(raw_qty, max_qty))


# ---------------------------------------------------------------------------
# ENHANCED REGIME DETECTOR
# ---------------------------------------------------------------------------
class RegimeDetector:
    """
    Daily regime based on Nifty 5‑minute data.
    Uses a simple trend filter: price vs EMA(20), ATR for strength,
    and a VIX‑like threshold for volatility.
    """
    def __init__(self):
        self.nifty_trend = "SIDEWAYS"      # BULL, BEAR, SIDEWAYS
        self.is_high_vol = False
        self.last_check_date = None
        self.vix_threshold = 25.0           # India VIX equivalent
        self.ema_span = 20

    def update(self):
        today = datetime.now().date()
        if self.last_check_date == today:
            return
        try:
            # Fetch recent 2 days of 5‑minute data for Nifty index
            df = fetch_historical("NIFTY 50", "5minute", 2)
            if df is None or len(df) < 100:
                return
            # Compute features to get ATR and EMA
            feat = add_all_features(df)
            if feat.empty or "atr_14" not in feat.columns:
                return

            close = feat["close"]
            atr = feat["atr_14"].iloc[-1]
            price = close.iloc[-1]
            ema20 = close.ewm(span=self.ema_span).mean().iloc[-1]

            trend_pct = (price - ema20) / ema20
            self.is_high_vol = (atr / price) > 0.015

            if abs(trend_pct) < 0.01:          # <1 % from EMA → SIDEWAYS
                self.nifty_trend = "SIDEWAYS"
            elif trend_pct > 0:
                self.nifty_trend = "BULL" if not self.is_high_vol else "SIDEWAYS"
            else:
                self.nifty_trend = "BEAR" if not self.is_high_vol else "SIDEWAYS"

            self.last_check_date = today
            logger.info(f"Regime: {self.nifty_trend}, HighVol: {self.is_high_vol}")
        except Exception as e:
            logger.warning(f"Regime detection failed: {e}")

                # Save to JSON for dashboard
        try:
            import json
            from pathlib import Path
            regime_data = {
                "trend": self.nifty_trend,
                "vol": "HIGH" if self.is_high_vol else "NORMAL",
                "breadth": "NARROW",
                "liquidity": "RISK_ON",
                "playbook": {
                    "bias": "LONG" if self.nifty_trend == "BULL" else "SHORT" if self.nifty_trend == "BEAR" else "NEUTRAL",
                    "size_multiplier": 1.0,
                    "stop_multiplier": 1.0,
                    "preferred_setups": ["Momentum", "Breakout"],
                    "avoid_setups": ["Counter Trend", "Low Liquidity"]
                },
                "global_context": {
                    "SGX NIFTY": {"value": "—", "change_pct": 0},
                    "S&P500 FUT": {"value": "—", "change_pct": 0},
                    "CRUDE OIL": {"value": "—", "change_pct": 0},
                    "GOLD": {"value": "—", "change_pct": 0},
                    "USD/INR": {"value": "—", "change_pct": 0}
                },
                "sector_returns": {}
            }
            Path("/app/logs/regime.json").write_text(json.dumps(regime_data))
        except Exception:
            pass


regime_detector = RegimeDetector()


# ---------------------------------------------------------------------------
# TRADING SYSTEM (with enhanced caching & ranking)
# ---------------------------------------------------------------------------
class TradingSystem:
    def __init__(self):
        self.risk = RiskManager(capital=CAPITAL)
        self.strategy = Strategy()
        self.broker = PaperBroker(capital=CAPITAL) if MODE != "LIVE" else LiveZerodhaBroker()
        self.order_manager = OrderManager(self.broker, self.risk, alerter, capital=CAPITAL)
        self.cycle_count = 0
        self.predictors: Dict[str, Predictor] = {}

        # Feature cache: symbol -> (DataFrame, timestamp, last_atr)
        self.feature_cache: Dict[str, Tuple[pd.DataFrame, datetime, float]] = {}
        self.feature_cache_ttl = timedelta(minutes=5)
        self.atr_change_threshold = 0.2   # 20 % change triggers refresh

        trained = set(
            m.stem.split("_")[0]
            for m in MODEL_DIR.glob("*.pkl")
            if m.suffix == ".pkl"
        )
        all_syms = [s.replace(".NS", "") for s in NIFTY50_SYMBOLS]
        self.active_symbols = [s for s in all_syms if s in trained]
        logger.info(f"Trading {len(self.active_symbols)} stocks")


system = TradingSystem()


# ---------------------------------------------------------------------------
# KILL SWITCH & CLEANUP
# ---------------------------------------------------------------------------
def handle_exit(signum, frame):
    system.order_manager.square_off_all()
    alerter.send("Bot shut down.", priority="high")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)


# ---------------------------------------------------------------------------
# HELPER: QUOTE FRESHNESS
# ---------------------------------------------------------------------------
def is_quote_fresh(q: dict) -> bool:
    ts = q.get("exchange_timestamp") or q.get("last_trade_time") or q.get("timestamp")
    if ts is None:
        return True
    try:
        quote_time = datetime.fromisoformat(ts)
        now = datetime.now(quote_time.tzinfo) if quote_time.tzinfo else datetime.now()
        return (now - quote_time).total_seconds() <= 30
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PRE‑FILTER WITH REALISTIC SIZING
# ---------------------------------------------------------------------------
def pre_filter_signal(symbol: str, ltp: float, predicted_return: float,
                      confidence: float, spread_pct: float, atr: float,
                      avg_daily_volume: Optional[float] = None) -> Tuple[bool, float]:
    """
    Quick rejection of signals that would never pass OrderManager edge validation.
    Uses the same risk‑based sizing logic to compute realistic costs.
    """
    if confidence < 0.55:
        return False, 0.0
    if spread_pct > 0.1:    # 0.1 % maximum
        return False, 0.0

    # Estimate stop‑loss distance (2 * ATR)
    approx_stop = ltp - 2 * atr if predicted_return > 0 else ltp + 2 * atr
    # Realistic quantity
    qty = compute_position_size(ltp, approx_stop, atr, spread_pct)
    if qty == 0:
        return False, 0.0

    # Use dynamic cost model
    required_move = minimum_move_for_profit(
        symbol, qty, ltp,
        atr=atr,
        spread_pct=spread_pct / 100.0,
        avg_daily_volume=avg_daily_volume,
        profit_buffer_pct=0.5,
    )
    expected_move_abs = abs(predicted_return) * confidence * ltp
    if expected_move_abs < required_move:
        return False, required_move
    return True, required_move

    # Estimate stop‑loss distance (2 * ATR)
    approx_stop = ltp - 2 * atr if predicted_return > 0 else ltp + 2 * atr
    # Realistic quantity
    qty = compute_position_size(ltp, approx_stop, atr, spread_pct)
    if qty == 0:
        return False, 0.0

    # Use dynamic cost model
    required_move = minimum_move_for_profit(
        symbol, qty, ltp,
        atr=atr,
        spread_pct=spread_pct / 100.0,
        avg_daily_volume=avg_daily_volume,
        profit_buffer_pct=0.5,
    )
    effective_confidence = max(confidence, 0.3)  # floor at 0.3
    expected_move_abs = abs(predicted_return) * effective_confidence * ltp
    if expected_move_abs < required_move:
        return False, required_move
    return True, required_move


# ---------------------------------------------------------------------------
# SIGNAL RANKING
# ---------------------------------------------------------------------------
def signal_score(predicted_return: float, confidence: float, ltp: float,
                 required_move: float, atr: float, qty: int) -> float:
    """Rank by expected net rupees per rupee of stop risk."""
    expected_edge = max(0.0, abs(predicted_return) * confidence * ltp - required_move)
    risk_per_share = max(atr * 2.0, 0.01)
    return (expected_edge * qty) / (risk_per_share * qty)


# ---------------------------------------------------------------------------
# MAIN CYCLE
# ---------------------------------------------------------------------------
def run_cycle():
    if STOP_FILE.exists():
        system.order_manager.square_off_all()
        sys.exit(0)

    if is_market_open() != MarketStatus.OPEN:
        return

    system.cycle_count += 1
    logger.info(f"=== Cycle {system.cycle_count} ===")
    
    # Run intraday scanner every 3 cycles (~15 minutes)
    if system.cycle_count % 3 == 0:
        try:
            from src.scanner.intraday_scanner import scan_all
            scan_all()
        except Exception:
            pass
    
    # Mean reversion scanner (every cycle, independent of ML)
    if system.cycle_count % 2 == 0:  # every 10 minutes
        try:
            from src.trading.mean_reversion import MeanReversionStrategy
            mr = MeanReversionStrategy()
            mr_signals = mr.scan_all(system.active_symbols[:20])  # top 20 liquid stocks
            for sig in mr_signals[:3]:  # max 3 MR positions
                # Skip if already in position
                if system.order_manager.managed_positions.get(sig["symbol"]) or \
                   any(o.get("symbol") == sig["symbol"] for o in system.order_manager.pending_orders.values()):
                    continue
                
                system.order_manager.submit_signal(
                    symbol=sig["symbol"],
                    side=sig["side"],
                    qty=0,  # OrderManager will size it
                    price=sig["entry_price"],
                    stop_loss=sig["stop_loss"],
                    target1=sig["target"],
                    target2=sig["target"],
                    atr=sig.get("atr", sig["entry_price"] * 0.02),
                    predicted_move=sig["target"] - sig["entry_price"],
                    confidence=sig["confidence"],
                    spread_pct=0.02,
                    sector="Unknown",
                )
                logger.info(f"MR SIGNAL: {sig['side']} {sig['symbol']} | {sig['reason']}")
        except Exception:
            pass

    if minutes_to_close() <= 15:
        system.order_manager.process_pending_orders()
        quotes = fetch_live_quote(system.active_symbols)
        if quotes:
            system.order_manager.update_market_data(quotes)
        system.order_manager.square_off_all()
        logger.info("Close window reached; entries blocked and positions squared off.")
        return

    # Update regime (daily)
    regime_detector.update()
    regime = regime_detector.nifty_trend
    high_volatility = regime_detector.is_high_vol

    system.order_manager.process_pending_orders()
    quotes = fetch_live_quote(system.active_symbols)
    if not quotes:
        return
    system.order_manager.update_market_data(quotes)
    if system.cycle_count == 1:
        system.order_manager.reconcile_with_broker(quotes)
    system.order_manager.check_open_positions(quotes)
    if system.risk.should_halt_intraday():
        system.order_manager.square_off_all()
        alerter.send("Intraday drawdown halt triggered.", priority="high")
        return

    # ------------------------------------------------------------------
    # Collect all valid signal candidates (with ranking)
    # ------------------------------------------------------------------
    candidates: List[dict] = []   # each dict: {symbol, sig, qty, ...}
    now = datetime.now()

    for sym in system.active_symbols:
        if sym not in quotes:
            continue
        # Skip already managed or pending
        if system.order_manager.managed_positions.get(sym) or \
           any(o["symbol"] == sym for o in system.order_manager.pending_orders.values()):
            continue

        q = quotes[sym]
        if not is_quote_fresh(q):
            continue

        ltp = q.get("ltp", 0)
        if ltp <= 0:
            continue

        # Predictor cache
        if sym not in system.predictors:
            system.predictors[sym] = Predictor(sym)

        # Adaptive feature cache: refresh if ATR changed significantly
        cached = system.feature_cache.get(sym)
        need_refresh = True
        if cached and (now - cached[1]) < system.feature_cache_ttl:
            _, _, last_atr = cached
            # Quick ATR check from live data (approximation)
            if last_atr > 0 and abs(last_atr - ltp * 0.02) / last_atr < system.atr_change_threshold:
                need_refresh = False   # use cache
        if need_refresh:
            df = fetch_historical(sym, "5minute", 5)
            if df is None or len(df) < 200:
                continue
            try:
                feat = add_all_features(df)
                atr = feat["atr_14"].dropna().iloc[-1] if "atr_14" in feat.columns else ltp * 0.02
                system.feature_cache[sym] = (feat, now, atr)
            except Exception:
                logger.exception(f"Feature error {sym}")
                continue
        else:
            feat = cached[0]
            atr = cached[2]

        # Get prediction
        try:
            pred = system.predictors[sym].predict(feat)
        except Exception:
            logger.exception(f"Prediction error {sym}")
            continue
        if pred is None:
            continue

        predicted_return = pred["predicted_return"]
        confidence = pred.get("confidence", 0.5)

        # Spread with explicit fallback (5 bps when missing)
        spread_pct = ((q.get("ask", 0) - q.get("bid", 0)) / ltp * 100) \
                     if q.get("bid", 0) > 0 and q.get("ask", 0) > 0 else 0.05

        avg_daily_volume = q.get("avg_daily_volume") or q.get("volume")

        # Pre-filter
        ok, required_move = pre_filter_signal(
            sym, ltp, predicted_return, confidence, spread_pct, atr, avg_daily_volume
        )
        if not ok:
            continue

        # Regime filter
        if regime == "BEAR" and predicted_return > 0:
            continue
        if regime == "BULL" and predicted_return < 0:
            continue

        sector = SECTOR_MAP.get(sym, "Unknown")
        # Generate signal (strategy determines side, stops, sizing)
        sig = system.strategy.generate_signal(
            symbol=sym,
            current_price=ltp,
            atr=atr,
            predicted_move=predicted_return * ltp,
            confidence=confidence,
            sector=sector,
            bid_ask_spread_pct=spread_pct,
            regime=regime,
            lower_bound=pred.get("lower_bound", 0.0) * ltp,   # in rupees
            upper_bound=pred.get("upper_bound", 0.0) * ltp,
        )

        if sig.side in ("BUY", "SELL"):
            # Order book confirmation
            from src.features.microstructure import confirm_signal
            ob_ok, ob_reason = confirm_signal(sig.side, q)
            if not ob_ok:
                logger.info(f"OB filter: {sig.symbol} {sig.side} rejected — {ob_reason}")
                continue

            est_qty = system.order_manager.estimate_position_size(
                sig.entry_price, sig.stop_loss, atr, spread_pct
            )
            if est_qty <= 0:
                continue
            candidates.append({
                "symbol": sig.symbol,
                "signal": sig,
                "estimated_qty": est_qty,
                "sector": sector,
                "atr": atr,
                "predicted_return": predicted_return,
                "confidence": confidence,
                "spread_pct": spread_pct,
                "avg_daily_volume": avg_daily_volume,
                "required_move": required_move,
                "score": signal_score(predicted_return, confidence, ltp, required_move, atr, est_qty),
            })

    # ------------------------------------------------------------------
    # Rank candidates by expected utility and apply capital‑aware pacing
    # ------------------------------------------------------------------
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Capital‑aware limits
    current_exposure = system.order_manager.current_exposure()
    available_capital = CAPITAL - current_exposure
    max_new_exposure = max(0.0, min(CAPITAL * 0.8 - current_exposure, available_capital * 0.8))
    new_trades = 0
    max_new_trades = min(
        1 if high_volatility else 3,
        system.order_manager.max_positions - len(system.order_manager.managed_positions),
    )

    for cand in candidates:
        if new_trades >= max_new_trades:
            break
        # Check capital constraint
        exposure_this_trade = cand["estimated_qty"] * cand["signal"].entry_price
        if exposure_this_trade > max_new_exposure:
            continue

        success = system.order_manager.submit_signal(
            symbol=cand["symbol"],
            side=cand["signal"].side,
            qty=cand["estimated_qty"],
            price=cand["signal"].entry_price,
            stop_loss=cand["signal"].stop_loss,
            target1=cand["signal"].target1,
            target2=cand["signal"].target2,
            atr=cand["atr"],
            predicted_move=cand["predicted_return"] * cand["signal"].entry_price,
            confidence=cand["confidence"],
            spread_pct=cand["spread_pct"],
            sector=cand["sector"],
            avg_daily_volume=cand["avg_daily_volume"],
        )
        time.sleep(0.1)  # rate limit between symbols
        if success:
            new_trades += 1
            max_new_exposure -= exposure_this_trade

            # ── Write live data for dashboard ──
    try:
        import json
        from pathlib import Path as _P
        
        # Positions
        pos_list = []
        for sym, pos in system.order_manager.managed_positions.items():
            pos_list.append({
                "symbol": sym,
                "side": pos.side,
                "qty": pos.qty,
                "entry_price": pos.entry_price,
                "ltp": pos.current_price,
                "pnl_inr": round((pos.current_price - pos.entry_price) * pos.qty, 2),
                "pnl_pct": round((pos.current_price / pos.entry_price - 1) * 100, 2),
                "stop_loss": pos.stop_loss,
                "target": pos.target2,
                "rr_ratio": round(abs(pos.target2 - pos.entry_price) / abs(pos.stop_loss - pos.entry_price), 1) if pos.stop_loss != pos.entry_price else 0,
                "recent_pnl_history": [],
            })
        _P("/app/logs/positions.json").write_text(json.dumps(pos_list))
        
        # Signals (last 20 from log)
        log_dir = _P("/app/logs")
        log_files = sorted(log_dir.glob("*.log"))
        signals = []
        if log_files:
            with open(log_files[-1]) as f:
                for line in f:
                    if "SIGNAL:" in line:
                        parts = line.split("SIGNAL:")[-1].strip()
                        time_str = line.split("|")[0].strip()
                        side = "BUY" if "BUY" in parts else "SELL"
                        sym = parts.split()[1] if len(parts.split()) > 1 else "?"
                        signals.append({
                            "time": time_str,
                            "symbol": sym,
                            "side": side,
                            "conviction": "MED",
                            "message": parts[:100],
                            "tags": [],
                        })
        _P("/app/logs/signals.json").write_text(json.dumps({"signals": signals[-20:]}))
    except Exception:
        pass

     # ── Momentum strategy (once per day, after 9:20 AM) ──
    if system.cycle_count == 1 and datetime.now().time() >= time(9, 20):
        try:
            from src.strategies.momentum_strategy import MomentumStrategy
            mom = MomentumStrategy()
            mom_signals = mom.scan_all(system.active_symbols)
            for sig in mom_signals:
                if system.order_manager.managed_positions.get(sig["symbol"]) or \
                   any(o.get("symbol") == sig["symbol"] for o in system.order_manager.pending_orders.values()):
                    continue
                system.order_manager.submit_signal(
                    symbol=sig["symbol"],
                    side=sig["side"],
                    qty=0,
                    price=sig["entry_price"],
                    stop_loss=sig["stop_loss"],
                    target1=sig["target"],
                    target2=sig["target"],
                    atr=sig.get("atr", sig["entry_price"] * 0.02),
                    predicted_move=sig["target"] - sig["entry_price"],
                    confidence=sig["confidence"],
                    spread_pct=0.02,
                    sector="Unknown",
                )
                logger.info(f"MOM SIGNAL: {sig['side']} {sig['symbol']} | {sig['reason']}")
        except Exception:
            pass

    logger.info(
        f"Cycle complete. Signals submitted: {new_trades}, "
        f"Positions: {len(system.order_manager.managed_positions)}, "
        f"Exposure: ₹{current_exposure:.0f}"
    )


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
def main():
    logger.info(f"🚀 Bot {MODE} | {len(system.active_symbols)} stocks | ₹{CAPITAL:,}")
    alerter.send(f"🤖 Bot started {MODE} mode.")

    # Optional: weekly performance review placeholder
    # if datetime.now().weekday() == 6:   # Sunday
    #     from src.monitoring.performance import weekly_report
    #     weekly_report()

    while True:
        try:
            run_cycle()
        except Exception as e:
            logger.exception(f"Fatal cycle error: {e}")
            alerter.send(f"❌ Cycle crash: {str(e)[:50]}")
        time.sleep(300)


if __name__ == "__main__":
    main()
