"""Configuration and normalization for trajectory prediction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass
class TrajectoryConfig:
    """All reproducible model, data, simulation, and training settings."""

    arena_width: float = 1.15
    arena_height: float = 1.15
    timestep: float = 1.0 / 25.0
    history_length: int = 10
    prediction_horizon: int = 5
    input_features: int = 4
    velocity_scale: float = 1.0
    max_speed: float = 0.8
    max_acceleration: float = 2.5
    max_angular_velocity: float = 5.0
    motion_noise_std: float = 0.04
    observation_noise_std: float = 0.003
    wall_margin: float = 0.08
    pit_polygons: list[list[list[float]]] = field(default_factory=list)
    flipper_polygon: list[list[float]] = field(default_factory=list)
    restricted_regions: list[list[list[float]]] = field(default_factory=list)
    dataset_size: int = 20_000
    hidden_size: int = 96
    num_layers: int = 2
    dropout: float = 0.1
    batch_size: int = 256
    epochs: int = 30
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    velocity_loss_weight: float = 0.0
    patience: int = 7
    seed: int = 42

    @property
    def tracking_frequency_hz(self) -> float:
        return 1.0 / self.timestep

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "TrajectoryConfig":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items() if key in known})

    def normalize_history(self, history: np.ndarray) -> np.ndarray:
        result = np.asarray(history, dtype=np.float32).copy()
        result[..., 0] /= self.arena_width
        result[..., 1] /= self.arena_height
        result[..., 2:4] /= self.velocity_scale
        return result

    def normalize_positions(self, positions: np.ndarray) -> np.ndarray:
        return np.asarray(positions, dtype=np.float32) / np.array(
            [self.arena_width, self.arena_height], dtype=np.float32
        )

    def denormalize_positions(self, positions: np.ndarray) -> np.ndarray:
        return np.asarray(positions, dtype=np.float32) * np.array(
            [self.arena_width, self.arena_height], dtype=np.float32
        )
