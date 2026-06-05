"""Target engineering for daily EOD predictions."""
from __future__ import annotations

import pandas as pd


def add_target(df: pd.DataFrame, threshold: float = 0.005) -> pd.DataFrame:
    """
    Add target columns for next-day prediction.

    Args:
        df: DataFrame with 'close' column and datetime index
        threshold: minimum return to be considered a tradeable move (0.005 = 0.5%)

    Returns:
        DataFrame with added columns:
        - target_return: (next_close - current_close) / current_close
        - target_direction: 1 if target_return > threshold, 0 otherwise
    """
    df = df.copy()

    # Next day's return
    df["target_return"] = df["close"].pct_change().shift(-1)

    # Binary target: 1 if next day's return exceeds threshold
    df["target_direction"] = (df["target_return"] > threshold).astype(int)

    return df.dropna(subset=["target_return"])