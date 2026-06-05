"""Prediction interface with dynamic, model‑agreement‑based confidence."""
from __future__ import annotations

from typing import Optional, Dict, Any
import xgboost as xgb
import numpy as np
import pandas as pd
from loguru import logger

from src.models.trainer import ModelTrainer


class Predictor:
    """
    Loads trained ensemble once, computes predictions from all base models,
    and derives confidence from model agreement and directional consistency.
    """

    _model_cache: Dict[str, ModelTrainer] = {}

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        if symbol not in Predictor._model_cache:
            trainer = ModelTrainer(symbol)
            if not trainer._load():
                logger.error(f"No trained model for {symbol}")
                Predictor._model_cache[symbol] = None
            else:
                Predictor._model_cache[symbol] = trainer
        self.trainer = Predictor._model_cache[symbol]

    def predict(self, features_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if self.trainer is None:
            return None

        X = features_df[self.trainer.feature_cols].values
        if X.shape[0] == 0:
            return None

        # Get individual base model predictions for the last row
        try:
            X_scaled = self.trainer.scaler.transform(X)
            # Random Forest prediction
            rf_pred = self.trainer.rf_model.predict(X_scaled)[-1]
            # XGBoost prediction
            dmatrix = xgb.DMatrix(X_scaled)
            try:
                xgb_pred = self.trainer.xgb_model.predict(
                    dmatrix,
                    iteration_range=(0, int(self.trainer.xgb_model.best_iteration) + 1),
                )[-1]
            except Exception:
                xgb_pred = self.trainer.xgb_model.predict(dmatrix)[-1]
            # LSTM prediction (needs sequence creation)
            seq_len = 20
            if len(X_scaled) >= seq_len:
                X_seq = X_scaled[-seq_len:].reshape(1, seq_len, -1)
                import torch
                self.trainer.lstm_model.eval()
                device = next(self.trainer.lstm_model.parameters()).device
                with torch.no_grad():
                    lstm_pred = self.trainer.lstm_model(
                        torch.tensor(X_seq, dtype=torch.float32).to(device)
                    ).item()
            else:
                return None
        except Exception as e:
            logger.error(f"Base prediction failed for {self.symbol}: {e}")
            return None

        # Discard LSTM if it's NaN (not enough data)
        base_preds = [rf_pred, xgb_pred]
        if not np.isnan(lstm_pred):
            base_preds.append(lstm_pred)
        base_preds = np.array(base_preds)

        # Meta‑learner gives final point prediction
        mean_pred = self.trainer.ensemble.meta.predict(base_preds.reshape(1, -1))[0]

        # Conservative confidence proxy from model agreement and stored OOS metrics.
        # This is not a true probability; strategy and OMS still require edge after costs.
        std_models = np.std(base_preds)
        # Use a reference volatility – can be training residual std (stored in ensemble? 
        # we don't have it, so use a simple constant 0.005 as fallback)
        ref_vol = 0.005   # typical 5-min return std
        if std_models > 0:
            # Use ratio of model agreement to typical volatility
            score = 1.0 - (std_models / ref_vol)
            score = max(0.0, min(1.0, score))
        else:
            score = 1.0
        score = max(0.0, min(1.0, score))

        # Directional agreement bonus/penalty
        signs = np.sign(base_preds)
        if np.all(signs == 1) or np.all(signs == -1):
            score *= 1.2
        elif not (np.any(signs == 1) and np.any(signs == -1)):
            score *= 1.0
        else:
            score *= 0.8

        metrics_quality = 0.5
        try:
            ic_quality = max(0.0, min(1.0, self.trainer.ic / 0.05))
            wr_quality = max(0.0, min(1.0, (self.trainer.win_rate - 0.50) / 0.05))
            sharpe_quality = max(0.0, min(1.0, self.trainer.sharpe / 1.0))
            metrics_quality = (ic_quality + wr_quality + sharpe_quality) / 3.0
        except Exception:
            metrics_quality = 0.35
        score *= metrics_quality


        score = round(min(1.0, max(0.0, score)), 4)

        # For compatibility, we still return the ensemble’s quantile-based bounds
        # (but they are constant; we can replace later with model‑disagreement bounds)
        _, lower, upper = self.trainer.ensemble.predict(base_preds.reshape(1, -1))

        return {
            "predicted_return": float(mean_pred),
            "lower_bound": float(lower[0]),
            "upper_bound": float(upper[0]),
            "confidence": score,
        }
