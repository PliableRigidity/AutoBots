"""Stable inference facade for future tracker integration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .config import TrajectoryConfig
from .model import build_model


class OpponentTrajectoryPredictor:
    """Load a checkpoint and predict physical future x/y coordinates."""

    def __init__(self, model: torch.nn.Module, config: TrajectoryConfig, device: torch.device) -> None:
        self.model, self.config, self.device = model, config, device
        self.model.eval()

    @classmethod
    def from_checkpoint(cls, path: str | Path, device: str | None = None) -> "OpponentTrajectoryPredictor":
        selected = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        checkpoint = torch.load(path, map_location=selected, weights_only=False)
        config = TrajectoryConfig.from_dict(checkpoint["config"])
        model = build_model(config).to(selected)
        model.load_state_dict(checkpoint["model_state_dict"])
        return cls(model, config, selected)

    def predict(self, history: np.ndarray | torch.Tensor) -> np.ndarray:
        """Predict ``[H,2]`` or batched ``[B,H,2]`` future positions in metres."""
        values = history.detach().cpu().numpy() if isinstance(history, torch.Tensor) else np.asarray(history)
        unbatched = values.ndim == 2
        if unbatched:
            values = values[None, ...]
        expected = (self.config.history_length, self.config.input_features)
        if values.ndim != 3 or tuple(values.shape[-2:]) != expected:
            raise ValueError(f"history must end in shape {expected}, got {values.shape}")
        normalized = self.config.normalize_history(values)
        tensor = torch.from_numpy(normalized).to(self.device)
        with torch.no_grad():
            prediction = self.model(tensor).cpu().numpy()
        physical = self.config.denormalize_positions(prediction)
        return physical[0] if unbatched else physical
