"""Deterministic procedural datasets for opponent trajectory prediction."""

from __future__ import annotations

import numpy as np
import torch
from torch.utils.data import Dataset

from .config import TrajectoryConfig
from .simulator import TrajectorySimulator


class TrajectoryDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Generate samples by index, avoiding a large on-disk dataset."""

    def __init__(self, config: TrajectoryConfig, size: int, seed: int) -> None:
        self.config, self.size, self.seed = config, size, seed

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        if index < 0 or index >= self.size:
            raise IndexError(index)
        c = self.config
        states = TrajectorySimulator(c, self.seed + index * 104729).generate(
            c.history_length + c.prediction_horizon
        )
        history = c.normalize_history(states[: c.history_length])
        future = c.normalize_positions(states[c.history_length :, :2])
        return torch.from_numpy(history), torch.from_numpy(future)


def create_datasets(config: TrajectoryConfig) -> tuple[TrajectoryDataset, TrajectoryDataset, TrajectoryDataset]:
    """Create deterministic 80/10/10 train, validation, and test datasets."""
    train_size = int(config.dataset_size * 0.8)
    validation_size = int(config.dataset_size * 0.1)
    test_size = config.dataset_size - train_size - validation_size
    return (
        TrajectoryDataset(config, train_size, config.seed),
        TrajectoryDataset(config, validation_size, config.seed + 10_000_000),
        TrajectoryDataset(config, test_size, config.seed + 20_000_000),
    )
