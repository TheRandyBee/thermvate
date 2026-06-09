# Thermal Dynamics Model
# Per-zone temperature prediction using Prophet + GBRT ensemble

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.ensemble import GradientBoostingRegressor
from dataclasses import dataclass, field
from typing import Optional
import joblib

@dataclass
class ThermalModelConfig:
    """Per-zone model configuration."""
    zone_name: str
    forecast_horizon_hours: int = 6
    retrain_interval_days: int = 7
    min_training_days: int = 3
    prophet_seasonality_mode: str = "multiplicative"
    prophet_seasonality_scale: float = 10.0
    prophet_uncertainty_samples: int = 0  # faster inference

    # Feature columns
    outdoor_temp_col: str = "outdoor_temp"
    hvac_state_col: str = "hvac_state"
    solar_irradiance_col: str = "solar_irradiance"

class ThermalModel:
    """
    Predicts zone temperature N hours ahead given HVAC state,
    outdoor conditions, and solar gain.

    Uses Prophet for baseline + GBRT for residual correction.
    """

    def __init__(self, config: ThermalModelConfig):
        self.config = config
        self.prophet: Optional[Prophet] = None
        self.residual_model: Optional[GradientBoostingRegressor] = None
        self._last_train_time: Optional[pd.Timestamp] = None

    def _prepare_data(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.Series]:
        """
        Prepare feature matrix and target.

        Expected columns in df:
        - ds: timestamp (pd.DatetimeIndex or column)
        - zone_temp: target temperature
        - outdoor_temp: exterior temperature
        - hvac_state: -1 (cool), 0 (off), 1 (heat)
        - solar_irradiance: W/m²
        - hour: extracted hour of day (optional, inferred)
        """
        data = df.copy()
        if "ds" not in data.columns:
            data["ds"] = data.index

        # Prophet needs 'ds' and 'y'
        prophet_df = data[["ds", "zone_temp"]].rename(
            columns={"zone_temp": "y"}
        ).copy()

        # Ensure numeric types
        for col in [
            self.config.outdoor_temp_col,
            self.config.hvac_state_col,
            self.config.solar_irradiance_col,
        ]:
            if col in data.columns:
                prophet_df[col] = data[col].astype(float)
            else:
                prophet_df[col] = 0.0

        # Add seasonality regressors to prophet
        prophet_df["hour_sin"] = np.sin(
            2 * np.pi * data["ds"].dt.hour / 24
        )
        prophet_df["hour_cos"] = np.cos(
            2 * np.pi * data["ds"].dt.hour / 24
        )

        return prophet_df

    def train(self, df: pd.DataFrame) -> dict:
        """Train the model ensemble on historical data."""
        prophet_df = self._prepare_data(df)

        # Train Prophet
        self.prophet = Prophet(
            seasonality_mode=self.config.prophet_seasonality_mode,
            seasonality_prior_scale=self.config.prophet_seasonality_scale,
            uncertainty_samples=self.config.prophet_uncertainty_samples,
            weekly_seasonality=True,
            daily_seasonality=False,
        )

        # Add regressors
        for col in [
            self.config.outdoor_temp_col,
            self.config.hvac_state_col,
            self.config.solar_irradiance_col,
            "hour_sin",
            "hour_cos",
        ]:
            if col in prophet_df.columns:
                self.prophet.add_regressor(col)

        self.prophet.fit(prophet_df)

        # Residual correction with GBRT
        predictions = self.prophet.predict(prophet_df)
        residuals = (
            prophet_df["y"].values - predictions["yhat"].values
        )

        features = prophet_df[
            [
                self.config.outdoor_temp_col,
                self.config.hvac_state_col,
                self.config.solar_irradiance_col,
                "hour_sin",
                "hour_cos",
            ]
        ].values

        self.residual_model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
        )
        self.residual_model.fit(features, residuals)

        self._last_train_time = pd.Timestamp.now()

        mae = np.mean(np.abs(residuals))
        rmse = np.sqrt(np.mean(residuals**2))
        return {"mae": float(mae), "rmse": float(rmse)}

    def predict(
        self,
        future_df: pd.DataFrame,
    ) -> np.ndarray:
        """
        Predict zone temperature for future timestamps.

        Args:
            future_df: DataFrame with future outdoor_temp, hvac_state,
                       solar_irradiance columns and ds timestamp index

        Returns:
            Array of predicted temperatures
        """
        if self.prophet is None or self.residual_model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        prophet_future = self._prepare_data(future_df)
        prophet_forecast = self.prophet.predict(prophet_future)

        features = prophet_future[
            [
                self.config.outdoor_temp_col,
                self.config.hvac_state_col,
                self.config.solar_irradiance_col,
                "hour_sin",
                "hour_cos",
            ]
        ].values

        residual_correction = self.residual_model.predict(features)
        return prophet_forecast["yhat"].values + residual_correction

    def save(self, path: str):
        """Save model to disk."""
        joblib.dump(
            {
                "config": self.config,
                "prophet": self.prophet,
                "residual_model": self.residual_model,
                "last_train_time": self._last_train_time,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "ThermalModel":
        """Load model from disk."""
        data = joblib.load(path)
        instance = cls(data["config"])
        instance.prophet = data["prophet"]
        instance.residual_model = data["residual_model"]
        instance._last_train_time = data["last_train_time"]
        return instance
