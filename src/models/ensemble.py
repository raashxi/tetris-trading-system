"""
Stacking Ensemble — Level‑2 Ridge meta‑learner.

Takes predictions from RF, XGBoost, and LSTM as input,
fits a Ridge regression on validation residuals,
and outputs point prediction + 95% confidence interval.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import Ridge


class StackingEnsemble:
    """Robust ensemble with built‑in confidence bounds."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.meta = Ridge(alpha=alpha, fit_intercept=True)
        self._lower_q: float = 0.0
        self._upper_q: float = 0.0
        self._fitted: bool = False

    def fit(self, base_preds: np.ndarray, y_true: np.ndarray) -> None:
        """
        Args:
            base_preds: shape (n_samples, 3) — [RF_pred, XGB_pred, LSTM_pred]
            y_true: true target values (same length)
        """
        if base_preds.ndim != 2 or base_preds.shape[1] != 3:
            raise ValueError("base_preds must be (n_samples, 3)")

        self.meta.fit(base_preds, y_true)
        residuals = y_true - self.meta.predict(base_preds)

        # 95 % empirical quantiles
        self._lower_q = np.quantile(residuals, 0.025)
        self._upper_q = np.quantile(residuals, 0.975)
        self._fitted = True

    def predict(self, base_preds: np.ndarray) -> tuple:
        """
        Returns:
            (predicted_mean, lower_bound, upper_bound)
        """
        if not self._fitted:
            raise RuntimeError("Ensemble not fitted yet")
        mean = self.meta.predict(base_preds)
        lower = mean + self._lower_q
        upper = mean + self._upper_q
        return mean, lower, upper