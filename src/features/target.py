"""Target engineering for 90-minute directional predictions."""
from __future__ import annotations

import pandas as pd


def add_target(df: pd.DataFrame, horizon: int = 18) -> pd.DataFrame:
    """
    horizon=18 means 18 × 5min = 90 minutes.
    Target: 1 if next 90-min return > 0, else 0 (balanced classes).
    """
    df = df.copy()
    future_close = df["close"].shift(-horizon)
    future_return = (future_close - df["close"]) / df["close"]
    df["target_return"] = future_return
    df["target_direction"] = (future_return > 0.0).astype(int)
    return df.dropna(subset=["target_return"])