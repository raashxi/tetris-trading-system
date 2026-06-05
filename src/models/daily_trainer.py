"""Train daily EOD prediction models with walk-forward validation, purge gaps, and cost-adjusted returns."""
from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.data.daily_fetcher import fetch_daily
from src.data.fetcher import NIFTY50_SYMBOLS
from src.features.daily_features import add_daily_features
from src.features.daily_target import add_target

EOD_MODEL_DIR = Path("/app/models/eod")
EOD_MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Thresholds for daily models
MIN_WIN_RATE = 0.52
MIN_SHARPE = 0.2
PURGE_DAYS = 5          # remove days around fold boundary
EMBARGO_DAYS = 10        # skip days after training ends

# Estimated round‑trip cost for delivery trades (approx 0.1%)
EST_COST_PCT = 0.001


class DailyTrainer:
    """Trains RF + XGBoost for next-day direction prediction using walk‑forward CV."""

    def __init__(self, symbol: str, train_years: int = 3, step_months: int = 3):
        self.symbol = symbol
        self.train_years = train_years
        self.step_months = step_months
        self.rf_model: Optional[RandomForestClassifier] = None
        self.xgb_model: Optional[XGBClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: list = []
        self.win_rate: float = 0.0
        self.sharpe: float = 0.0
        self.cost_adj_win_rate: float = 0.0

    def prepare_data(self) -> Optional[Tuple[pd.DataFrame, pd.Series]]:
        """Fetch daily data, compute features and target."""
        df = fetch_daily(self.symbol, days=self.train_years * 365)
        if df is None or len(df) < 300:
            logger.warning(f"Not enough daily data for {self.symbol}")
            return None

        nifty_df = fetch_daily("NIFTY 50", days=self.train_years * 365)
        df = add_daily_features(df, nifty_df)
        df = add_target(df)

        if df.empty:
            return None

        drop_cols = ["open", "high", "low", "close", "volume",
                     "target_return", "target_direction"]
        self.feature_cols = [c for c in df.columns if c not in drop_cols]

        X = df[self.feature_cols]
        y = df["target_direction"].astype(int)
        logger.info(f"{self.symbol}: {len(X)} samples, {len(self.feature_cols)} features")
        return X, y

    def train(self) -> bool:
        """Walk‑forward training with purge and embargo gaps."""
        data = self.prepare_data()
        if data is None:
            return False

        X, y = data
        n = len(X)
        step_size = self.step_months * 21  # ~21 trading days per month

        all_y_true = []
        all_y_pred = []
        all_returns = []

        # First training window: first 18 months
        train_start = 0
        train_end = int(n * 0.6)  # 60% initial train

        while train_end + step_size + EMBARGO_DAYS <= n:
            # Validation window
            val_start = train_end + EMBARGO_DAYS
            val_end = min(val_start + step_size, n - PURGE_DAYS)

            if val_end - val_start < 20:
                break

            # Fit scaler ONLY on training data
            scaler = StandardScaler()
            X_train = scaler.fit_transform(X.iloc[train_start:train_end])
            X_val = scaler.transform(X.iloc[val_start:val_end])

            y_train = y.iloc[train_start:train_end].values.ravel()
            y_val = y.iloc[val_start:val_end].values.ravel()

            # Train RF
            rf = RandomForestClassifier(
                n_estimators=200, max_depth=8, min_samples_leaf=10,
                random_state=42, n_jobs=-1
            )
            rf.fit(X_train, y_train)

            # Train XGB
            xgb = XGBClassifier(
                n_estimators=500, max_depth=5, learning_rate=0.01,
                subsample=0.8, random_state=42, verbosity=0
            )
            xgb.fit(X_train, y_train)

            # Ensemble probabilities
            rf_prob = rf.predict_proba(X_val)[:, 1]
            xgb_prob = xgb.predict_proba(X_val)[:, 1]
            ensemble_prob = (rf_prob + xgb_prob) / 2
            ensemble_pred = (ensemble_prob > 0.5).astype(int)

            all_y_true.extend(y_val)
            all_y_pred.extend(ensemble_pred)

            # Cost‑adjusted returns for validation period
            actual_returns = X.iloc[val_start:val_end]["return_1d"].values
            for i, pred in enumerate(ensemble_pred):
                if pred == 1:
                    ret = actual_returns[i] - EST_COST_PCT
                else:
                    ret = 0  # no trade
                all_returns.append(ret)

            # Slide window forward
            train_end += step_size

        if len(all_y_true) < 30:
            logger.warning(f"Not enough validation samples for {self.symbol}")
            return False

        # Compute metrics
        self.win_rate = accuracy_score(all_y_true, all_y_pred)
        self.cost_adj_win_rate = sum(1 for r in all_returns if r > 0) / len(all_returns) if all_returns else 0
        self.sharpe = (np.mean(all_returns) / np.std(all_returns) * np.sqrt(252)) if np.std(all_returns) > 0 else 0

        logger.info(f"  Walk‑forward Win Rate: {self.win_rate:.3f}")
        logger.info(f"  Cost‑adjusted Win Rate: {self.cost_adj_win_rate:.3f}")
        logger.info(f"  Sharpe: {self.sharpe:.3f}")

        if self.win_rate < MIN_WIN_RATE and self.cost_adj_win_rate < MIN_WIN_RATE:
            logger.warning(f"{self.symbol} below thresholds. Discarding.")
            return False

        # Fit final models on ALL data for production use
        final_scaler = StandardScaler()
        X_all = final_scaler.fit_transform(X)
        y_all = y.values.ravel()

        self.scaler = final_scaler
        self.rf_model = RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=10,
            random_state=42, n_jobs=-1
        )
        self.rf_model.fit(X_all, y_all)
        self.xgb_model = XGBClassifier(
            n_estimators=500, max_depth=5, learning_rate=0.01,
            subsample=0.8, random_state=42, verbosity=0
        )
        self.xgb_model.fit(X_all, y_all)

        self._save()
        return True

    def _save(self) -> None:
        """Save models and metadata."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = EOD_MODEL_DIR / f"{self.symbol}_{ts}.pkl"
        with open(path, "wb") as f:
            pickle.dump({
                "rf": self.rf_model,
                "xgb": self.xgb_model,
                "scaler": self.scaler,
                "feature_cols": self.feature_cols,
                "win_rate": self.win_rate,
                "cost_adj_win_rate": self.cost_adj_win_rate,
                "sharpe": self.sharpe,
            }, f)
        logger.info(f"  EOD model saved: {path}")

    def predict(self, X: pd.DataFrame) -> dict:
        """Generate prediction for latest data."""
        if self.rf_model is None:
            self._load()
        if self.rf_model is None:
            return None
        X_scaled = self.scaler.transform(X[self.feature_cols])
        rf_prob = self.rf_model.predict_proba(X_scaled)[:, 1]
        xgb_prob = self.xgb_model.predict_proba(X_scaled)[:, 1]
        prob = float((rf_prob[-1] + xgb_prob[-1]) / 2)
        direction = 1 if prob > 0.5 else 0
        confidence = 2 * abs(prob - 0.5)
        return {"direction": direction, "probability": round(prob, 4), "confidence": round(confidence, 4)}

    def _load(self) -> bool:
        """Load latest model from disk."""
        versions = sorted(EOD_MODEL_DIR.glob(f"{self.symbol}_*.pkl"))
        if not versions:
            return False
        with open(versions[-1], "rb") as f:
            data = pickle.load(f)
        self.rf_model = data["rf"]
        self.xgb_model = data["xgb"]
        self.scaler = data["scaler"]
        self.feature_cols = data["feature_cols"]
        self.win_rate = data.get("win_rate", 0.0)
        self.cost_adj_win_rate = data.get("cost_adj_win_rate", 0.0)
        self.sharpe = data.get("sharpe", 0.0)
        return True


def train_all_eod(max_symbols: int = 50) -> Dict[str, bool]:
    """Train EOD models for Nifty 50 with walk‑forward validation."""
    symbols = [s.replace(".NS", "") for s in NIFTY50_SYMBOLS[:max_symbols]]
    results = {}
    for i, sym in enumerate(symbols):
        logger.info(f"=== EOD Training {sym} ({i+1}/{len(symbols)}) ===")
        try:
            t = DailyTrainer(sym)
            success = t.train()
            results[sym] = success
        except Exception as e:
            logger.error(f"EOD training failed for {sym}: {e}")
            results[sym] = False
    passed = sum(1 for v in results.values() if v)
    logger.info(f"EOD training done: {passed}/{len(results)} passed")
    return results