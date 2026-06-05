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

import numpy as np
import pandas as pd

from src.features.target import add_target
from src.features.technical import add_all_features


class FeatureNoLookaheadTests(unittest.TestCase):
    def _sample_ohlcv(self, rows: int = 320) -> pd.DataFrame:
        idx = pd.date_range("2026-04-01 09:15", periods=rows, freq="5min")
        base = 100 + np.linspace(0, 5, rows)
        wiggle = np.sin(np.arange(rows) / 8.0)
        close = base + wiggle
        open_ = close + 0.05
        high = np.maximum(open_, close) + 0.2
        low = np.minimum(open_, close) - 0.2
        volume = 10_000 + (np.arange(rows) % 30) * 100
        nifty_close = 20_000 + np.linspace(0, 20, rows) + np.cos(np.arange(rows) / 10.0)
        return pd.DataFrame({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "nifty_close": nifty_close,
        }, index=idx)

    def test_features_at_t_do_not_change_when_future_rows_change(self):
        raw = self._sample_ohlcv()
        features = add_all_features(raw)
        point = features.index[-8]
        before = features.loc[point].copy()

        mutated = raw.copy()
        future_mask = mutated.index > point
        mutated.loc[future_mask, ["open", "high", "low", "close", "nifty_close"]] *= 1.5
        mutated.loc[future_mask, "volume"] *= 10
        after = add_all_features(mutated).loc[point]

        pd.testing.assert_series_equal(before, after, check_names=False)

    def test_target_is_next_bar_return(self):
        raw = self._sample_ohlcv(260)
        features = add_all_features(raw)
        targeted = add_target(features)
        idx = targeted.index[10]
        expected = features["close"].pct_change().shift(-1).loc[idx]
        self.assertAlmostEqual(targeted.loc[idx, "target_return"], expected)


if __name__ == "__main__":
    unittest.main()
