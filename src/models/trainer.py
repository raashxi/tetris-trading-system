"""Full‑spec trainer: RF + XGBoost + LSTM with Optuna tuning and walk‑forward."""
from __future__ import annotations

import gc
import os
import pickle
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from loguru import logger
from sklearn.metrics import mean_absolute_error, accuracy_score, f1_score, balanced_accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.ensemble import RandomForestClassifier
import xgboost as xgb
import optuna

from src.data.fetcher import fetch_historical
from src.features.technical import add_all_features
from src.features.target import add_target
from src.models.ensemble import StackingEnsemble

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
logger.info(f"Using device: {device}")

MODEL_DIR = Path("/app/models")
MODEL_DIR.mkdir(exist_ok=True)

MIN_SHARPE = 0.0
MIN_WIN_RATE = 0.52
MIN_IC = 0.01


class LSTMRegressor(nn.Module):
    """2‑layer LSTM with batch norm and dropout."""
    def __init__(self, input_dim: int, hidden_dim: int = 128, dropout: float = 0.2):
        super().__init__()
        self.lstm1 = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.dropout1 = nn.Dropout(dropout)
        self.lstm2 = nn.LSTM(hidden_dim, 64, batch_first=True)
        self.bn2 = nn.BatchNorm1d(64)
        self.dropout2 = nn.Dropout(dropout)
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 1)

    def forward(self, x):
        x, _ = self.lstm1(x)
        x = x[:, -1, :]           # last time step
        x = self.bn1(x)
        x = self.dropout1(x)
        x = x.unsqueeze(1)        # add time dim for second LSTM
        x, _ = self.lstm2(x)
        x = x[:, -1, :]
        x = self.bn2(x)
        x = self.dropout2(x)
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return x.squeeze()


def create_sequences(X: np.ndarray, y: np.ndarray, seq_len: int = 20):
    """Convert time‑series data into sequences for LSTM."""
    xs, ys = [], []
    for i in range(len(X) - seq_len):
        xs.append(X[i:i+seq_len])
        ys.append(y[i+seq_len])
    return np.array(xs), np.array(ys)


class ModelTrainer:
    """Handles per‑symbol training with walk‑forward, Optuna tuning, ensemble."""

    def __init__(self, symbol: str, train_days: int = 20, step_days: int = 5, purge_days: int = 1):
        self.symbol = symbol
        self.train_days = train_days
        self.step_days = step_days
        self.purge_days = purge_days

        # Placeholders
        self.rf_model: Optional[RandomForestClassifier] = None
        self.xgb_model: Optional[xgb.XGBRegressor] = None
        self.lstm_model: Optional[LSTMRegressor] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: List[str] = []
        self.ensemble: Optional[StackingEnsemble] = None
        self.sharpe: float = 0.0
        self.ic: float = 0.0
        self.win_rate: float = 0.0

    def _load_data(self) -> Optional[pd.DataFrame]:
        raw = fetch_historical(self.symbol, "5minute", self.train_days + 30)
        if raw is None:
            return None
        df = add_all_features(raw)
        df = add_target(df)
        return df

    def _feature_columns(self, df: pd.DataFrame) -> List[str]:
        drop = ["open","high","low","close","volume","target_return","target_direction"]
        return [c for c in df.columns if c not in drop]

    def _fit_arrays(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, StandardScaler, List[str]]:
        feature_cols = self._feature_columns(df)
        self.feature_cols = feature_cols
        X = df[feature_cols].values
        y = df["target_direction"].astype(int).values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        return X_scaled, y, scaler, feature_cols

    def _transform_arrays(
        self,
        df: pd.DataFrame,
        scaler: StandardScaler,
        feature_cols: List[str],
    ) -> Tuple[np.ndarray, np.ndarray]:
        X = df[feature_cols].values
        y = df["target_direction"].astype(int).values
        return scaler.transform(X), y

    def _prepare_arrays(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, StandardScaler]:
        X, y, scaler, _ = self._fit_arrays(df)
        return X, y, scaler

    def _tune_rf(self, X_train, y_train, X_val, y_val, n_trials: int = 30):
        def objective(trial):
            n_estimators = trial.suggest_int("n_estimators", 50, 300)
            max_depth = trial.suggest_int("max_depth", 3, 12)
            min_samples_leaf = trial.suggest_int("min_samples_leaf", 5, 30)
            model = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                min_samples_leaf=min_samples_leaf,
                random_state=42,
                n_jobs=-1,
                class_weight='balanced'
            )
            model.fit(X_train, y_train)
            preds = model.predict(X_val)
            return mean_absolute_error(y_val, preds)
        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = study.best_params
        model = RandomForestClassifier(**best, random_state=42, n_jobs=-1, class_weight='balanced')
        model.fit(X_train, y_train)
        return model

    def _tune_xgb(self, X_train, y_train, X_val, y_val, n_trials: int = 30):
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)

        def objective(trial):
            params = {
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.001, 0.1, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
                "verbosity": 0,
                "tree_method": "hist",
                "scale_pos_weight": len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1),
            }
            model = xgb.train(params, dtrain, num_boost_round=params["n_estimators"],
                              evals=[(dval, "val")], early_stopping_rounds=30, verbose_eval=False)
            preds = model.predict(dval)
            return mean_absolute_error(y_val, preds)
        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = study.best_params
        best.pop("n_estimators", None)
        final_model = xgb.train(best, dtrain, num_boost_round=1000,
                                evals=[(dval, "val")], early_stopping_rounds=30, verbose_eval=False)
        return final_model

    def _train_lstm(self, X_train, y_train, X_val, y_val, input_dim: int, epochs: int = 50):
        seq_len = 20
        X_seq, y_seq = create_sequences(X_train, y_train, seq_len)
        X_val_seq, y_val_seq = create_sequences(X_val, y_val, seq_len)
        if len(X_seq) == 0 or len(X_val_seq) == 0:
            raise ValueError("Insufficient rows for LSTM sequence training")

        # Convert to tensors
        X_tens = torch.tensor(X_seq, dtype=torch.float32).to(device)
        y_tens = torch.tensor(y_seq, dtype=torch.float32).to(device)
        X_val_tens = torch.tensor(X_val_seq, dtype=torch.float32).to(device)
        y_val_tens = torch.tensor(y_val_seq, dtype=torch.float32).to(device)

        model = LSTMRegressor(input_dim).to(device)
        optimizer = optim.AdamW(model.parameters(), lr=1e-3)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        criterion = nn.MSELoss()

        best_loss = float("inf")
        patience = 10
        counter = 0

        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()
            output = model(X_tens)
            loss = criterion(output, y_tens)
            loss.backward()
            optimizer.step()
            scheduler.step()

            model.eval()
            with torch.no_grad():
                val_output = model(X_val_tens)
                val_loss = criterion(val_output, y_val_tens).item()

            if val_loss < best_loss:
                best_loss = val_loss
                counter = 0
                torch.save(model.state_dict(), f"/tmp/lstm_{self.symbol}.pt")
            else:
                counter += 1
                if counter >= patience:
                    break

        # Load best
        model.load_state_dict(torch.load(f"/tmp/lstm_{self.symbol}.pt"))
        model.eval()
        return model

    def _compute_metrics(self, y_true, y_pred) -> Tuple[float, float, float, float]:
        mae = mean_absolute_error(y_true, y_pred)
        ic = np.corrcoef(y_true, y_pred)[0, 1] if len(y_true) > 1 else 0.0
        direction_pred = (pd.Series(y_pred) > 0).astype(int)
        direction_actual = (pd.Series(y_true) > 0).astype(int)
        wr = (direction_pred == direction_actual).mean()
        # Directional strategy proxy before costs. This is only an approval
        # screen; live use still requires separate cost-adjusted backtests.
        returns = pd.Series(np.where(direction_pred, y_true, -y_true))  # rough
        sharpe = (returns.mean() / returns.std() * np.sqrt(252 * 75)) if returns.std() > 0 else 0.0
        return mae, ic, wr, sharpe

    def train(self) -> bool:
        df = self._load_data()
        if df is None or len(df) < 500:
            logger.error(f"Insufficient data for {self.symbol}")
            return False

        # Walk‑forward splits
        n = len(df)
        indices = np.arange(n)
        step = self.step_days * 75  # approx 75 5-min bars per day
        train_start = self.train_days * 75
        purge = self.purge_days * 75

        all_rf_preds, all_xgb_preds, all_lstm_preds, all_true = [], [], [], []

        for test_start in range(train_start, n - step, step):
            train_end = test_start - purge
            if train_end <= 0:
                continue
            train_df = df.iloc[:train_end]
            val_bars = min(step, max(100, len(train_df) // 5))
            if len(train_df) <= val_bars + 100:
                continue
            fit_df = train_df.iloc[:-val_bars]
            val_df = train_df.iloc[-val_bars:]
            test_df = df.iloc[test_start:test_start+step]

            X_train, y_train, scaler, feature_cols = self._fit_arrays(fit_df)
            X_val, y_val = self._transform_arrays(val_df, scaler, feature_cols)
            X_test, y_test = self._transform_arrays(test_df, scaler, feature_cols)

            # Tune & train RF
            rf = self._tune_rf(X_train, y_train, X_val, y_val, n_trials=20)
            rf_pred = rf.predict(X_test)

            # Tune & train XGBoost
            xg = self._tune_xgb(X_train, y_train, X_val, y_val, n_trials=20)
            xg_pred = xg.predict(xgb.DMatrix(X_test))

            # Train LSTM (no tuning, use best config from spec)
            lstm = self._train_lstm(X_train, y_train, X_val, y_val, input_dim=X_train.shape[1])
            X_seq_test, _ = create_sequences(X_test, y_test, 20)
            if len(X_seq_test) == 0:
                continue
            with torch.no_grad():
                lstm_pred = lstm(torch.tensor(X_seq_test, dtype=torch.float32).to(device)).cpu().numpy()
            all_true.extend(y_test[20:])
            all_rf_preds.extend(rf_pred[20:])
            all_xgb_preds.extend(xg_pred[20:])
            all_lstm_preds.extend(lstm_pred)

        # Ensure lengths match (may be off due to sequence creation)
        min_len = min(len(all_true), len(all_rf_preds), len(all_xgb_preds), len(all_lstm_preds))
        if min_len < 100:
            logger.error(f"Insufficient out-of-sample predictions for {self.symbol}")
            return False
        all_true = np.array(all_true[:min_len])
        rf_preds = np.array(all_rf_preds[:min_len])
        xgb_preds = np.array(all_xgb_preds[:min_len])
        lstm_preds = np.array(all_lstm_preds[:min_len])

        # Ensemble training
        base_preds = np.column_stack([rf_preds, xgb_preds, lstm_preds])
        self.ensemble = StackingEnsemble()
        self.ensemble.fit(base_preds, all_true)
        final_preds, lower, upper = self.ensemble.predict(base_preds)

        # Metrics
        _, self.ic, self.win_rate, self.sharpe = self._compute_metrics(all_true, final_preds)
        
        # Additional classification metrics
        ensemble_pred_binary = (final_preds > 0).astype(int)
        accuracy = accuracy_score(all_true, ensemble_pred_binary)
        f1 = f1_score(all_true, ensemble_pred_binary, zero_division=0)
        balanced_acc = balanced_accuracy_score(all_true, ensemble_pred_binary)
        logger.info(f"Accuracy: {accuracy:.3f}, F1: {f1:.3f}, Balanced Acc: {balanced_acc:.3f}")
        self.win_rate = accuracy
        
        logger.info(f"{self.symbol} | IC: {self.ic:.3f} | WR: {self.win_rate:.2%} | Sharpe: {self.sharpe:.2f}")

        if self.sharpe < MIN_SHARPE or self.ic < MIN_IC or self.win_rate < MIN_WIN_RATE:
            logger.warning(f"{self.symbol} did not meet thresholds. Model discarded.")
            return False

        # Save best models (re-train on full dataset up to last point)
        holdout = max(100, min(len(df) // 5, self.step_days * 75))
        fit_df = df.iloc[:-holdout]
        val_df = df.iloc[-holdout:]
        X_full, y_full, scaler, feature_cols = self._fit_arrays(fit_df)
        X_val, y_val = self._transform_arrays(val_df, scaler, feature_cols)
        self.rf_model = self._tune_rf(X_full, y_full, X_val, y_val, n_trials=20)
        self.xgb_model = self._tune_xgb(X_full, y_full, X_val, y_val, n_trials=20)
        self.lstm_model = self._train_lstm(X_full, y_full, X_val, y_val, X_full.shape[1])
        self.scaler = scaler
        self._save()
        return True

    def _save(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = MODEL_DIR / f"{self.symbol}_{ts}.pkl"
        with open(path, "wb") as f:
            pickle.dump({
                "rf": self.rf_model,
                "xgb": self.xgb_model,
                "lstm_state": self.lstm_model.state_dict() if self.lstm_model else None,
                "scaler": self.scaler,
                "feature_cols": self.feature_cols,
                "ensemble": self.ensemble,
                "metrics": {"sharpe": self.sharpe, "ic": self.ic, "win_rate": self.win_rate},
            }, f)
        # Keep only last 3 versions
        versions = sorted(MODEL_DIR.glob(f"{self.symbol}_*.pkl"))
        for old in versions[:-3]:
            old.unlink()
        logger.info(f"Model saved: {path}")

    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return final prediction, lower, upper for given features."""
        if self.scaler is None:
            self._load()
        X_scaled = self.scaler.transform(X)
        rf_pred = self.rf_model.predict(X_scaled)
        xgb_pred = self.xgb_model.predict(xgb.DMatrix(X_scaled))
        # LSTM prediction requires sequences
        X_seq, _ = create_sequences(X_scaled, np.zeros(len(X_scaled)), 20)  # dummy y
        with torch.no_grad():
            lstm_pred = self.lstm_model(torch.tensor(X_seq, dtype=torch.float32).to(device)).cpu().numpy()
        # Align lengths
        base_preds = np.column_stack([rf_pred[:len(lstm_pred)],
                                      xgb_pred[:len(lstm_pred)],
                                      lstm_pred])
        return self.ensemble.predict(base_preds)

    def _load(self) -> bool:
        versions = sorted(MODEL_DIR.glob(f"{self.symbol}_*.pkl"))
        if not versions:
            return False
        with open(versions[-1], "rb") as f:
            data = pickle.load(f)
        self.rf_model = data["rf"]
        self.xgb_model = data["xgb"]
        self.lstm_model = LSTMRegressor(len(data["feature_cols"])).to(device)
        self.lstm_model.load_state_dict(data["lstm_state"])
        self.scaler = data["scaler"]
        self.feature_cols = data["feature_cols"]
        self.ensemble = data["ensemble"]
        self.sharpe = data["metrics"]["sharpe"]
        self.ic = data["metrics"]["ic"]
        self.win_rate = data["metrics"]["win_rate"]
        return True                                        
    

def train_all(active_only: bool = True, max_symbols: int = 10) -> Dict[str, bool]:
    """
    Train models for multiple symbols.

    Args:
        active_only: If True, train only first max_symbols
        max_symbols: Number of symbols to train

    Returns:
        Dict mapping symbol to success/failure
    """
    from src.data.fetcher import NIFTY50_SYMBOLS

    symbols = NIFTY50_SYMBOLS[:max_symbols] if active_only else NIFTY50_SYMBOLS
    symbols = [s.replace(".NS", "") for s in symbols]

    results = {}
    for i, sym in enumerate(symbols):
        logger.info(f"=== Training {sym} ({i+1}/{len(symbols)}) ===")
        try:
            trainer = ModelTrainer(sym)
            success = trainer.train()
            results[sym] = success
        except Exception as e:
            logger.error(f"Failed to train {sym}: {e}")
            results[sym] = False

    trained = sum(1 for v in results.values() if v)
    logger.info(f"Training complete: {trained}/{len(results)} models passed thresholds")
    return results


def retrain_all_models(active_only: bool = True, max_symbols: int = 10) -> Dict[str, bool]:
    """Compatibility entry point used by scripts/daily_retrain.sh."""
    return train_all(active_only=active_only, max_symbols=max_symbols)