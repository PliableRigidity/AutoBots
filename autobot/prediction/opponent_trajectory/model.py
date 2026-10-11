"""Compact GRU trajectory predictor."""

from __future__ import annotations

import torch
from torch import nn


class GRUTrajectoryPredictor(nn.Module):
    """Encode motion history with a GRU and decode all future positions at once."""

    def __init__(self, input_features: int = 4, hidden_size: int = 96, num_layers: int = 2,
                 dropout: float = 0.1, prediction_horizon: int = 5) -> None:
        super().__init__()
        self.prediction_horizon = prediction_horizon
        self.gru = nn.GRU(
            input_features, hidden_size, num_layers=num_layers, batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size), nn.ReLU(), nn.Linear(hidden_size, prediction_horizon * 2)
        )

    def forward(self, history: torch.Tensor) -> torch.Tensor:
        _, hidden = self.gru(history)
        offsets = self.head(hidden[-1]).reshape(-1, self.prediction_horizon, 2)
        return history[:, -1, :2].unsqueeze(1) + offsets


def build_model(config: "object") -> GRUTrajectoryPredictor:
    return GRUTrajectoryPredictor(
        input_features=config.input_features, hidden_size=config.hidden_size,
        num_layers=config.num_layers, dropout=config.dropout,
        prediction_horizon=config.prediction_horizon,
    )
