from __future__ import annotations

import sys
import types
import unittest


class _Logger:
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None
        return _noop


sys.modules.setdefault("loguru", types.SimpleNamespace(logger=_Logger()))
sys.modules.setdefault("keyring", types.SimpleNamespace(
    get_password=lambda *args, **kwargs: None,
    set_password=lambda *args, **kwargs: None,
))
sys.modules.setdefault("kiteconnect", types.SimpleNamespace(KiteConnect=object))
sys.modules.setdefault("requests", types.SimpleNamespace(
    post=lambda *args, **kwargs: types.SimpleNamespace(status_code=200, text="OK")
))

from src.trading.cost_model import compute_round_trip_cost
from src.trading.execution import PaperBroker
from src.trading.order_manager import OrderManager
from src.trading.risk import RiskManager
from src.trading.strategy import Strategy


class _Alerter:
    def send(self, *args, **kwargs):
        return True


class TradingSafetyTests(unittest.TestCase):
    def test_paper_market_exit_uses_market_price_and_nets_flat(self):
        broker = PaperBroker(rejection_rate=0.0)
        broker.set_market_price("TEST", 100.0, bid=99.95, ask=100.05)

        entry = broker.place_order("TEST", "BUY", 10, 100.0, order_type="LIMIT")
        self.assertEqual(entry.status, "FILLED")
        self.assertGreater(entry.filled_price, 0)

        broker.set_market_price("TEST", 101.0, bid=100.95, ask=101.05)
        exit_order = broker.place_order("TEST", "SELL", 10, 0, order_type="MARKET")
        self.assertEqual(exit_order.status, "FILLED")
        self.assertGreater(exit_order.filled_price, 0)
        self.assertEqual(broker.get_positions(), [])

    def test_order_manager_keeps_position_when_exit_rejected(self):
        broker = PaperBroker(rejection_rate=0.0)
        broker.set_market_price("TEST", 100.0, bid=99.95, ask=100.05)
        risk = RiskManager(100_000)
        manager = OrderManager(broker, risk, _Alerter(), capital=100_000)

        submitted = manager.submit_signal(
            symbol="TEST",
            side="BUY",
            qty=10,
            price=100.0,
            stop_loss=98.0,
            target1=103.0,
            target2=105.0,
            atr=1.0,
            predicted_move=3.0,
            confidence=0.90,
            spread_pct=0.02,
            sector="Test",
        )
        self.assertTrue(submitted)
        manager.process_pending_orders()
        self.assertIn("TEST", manager.managed_positions)

        broker._rejection_rate = 1.0
        exited = manager.exit_position("TEST", "test rejection")
        self.assertFalse(exited)
        self.assertIn("TEST", manager.managed_positions)

    def test_strategy_short_targets_stay_below_entry(self):
        signal = Strategy().generate_signal(
            symbol="TEST",
            current_price=100.0,
            atr=1.0,
            predicted_move=-2.0,
            confidence=0.90,
            bid_ask_spread_pct=0.02,
            lower_bound=-2.5,
            upper_bound=-0.5,
        )
        self.assertEqual(signal.side, "SELL")
        self.assertGreater(signal.stop_loss, signal.entry_price)
        self.assertLess(signal.target1, signal.entry_price)
        self.assertLess(signal.target2, signal.target1)

    def test_cost_model_charges_market_impact_with_adv(self):
        no_impact = compute_round_trip_cost("TEST", 100, 100.0, 100.0, atr=1.0)
        with_impact = compute_round_trip_cost(
            "TEST",
            100,
            100.0,
            100.0,
            atr=1.0,
            avg_daily_volume=1_000,
        )
        self.assertGreater(with_impact["total_cost"], no_impact["total_cost"])
        self.assertGreater(with_impact["buy_costs"]["participation_rate"], 0)


if __name__ == "__main__":
    unittest.main()
