"""Fast end-to-end tests for the opponent trajectory subsystem."""

from __future__ import annotations

import json

import numpy as np
import torch

from autobot.prediction.opponent_trajectory.arena import ArenaMap, point_in_polygon
from autobot.prediction.opponent_trajectory.config import TrajectoryConfig
from autobot.prediction.opponent_trajectory.dataset import TrajectoryDataset
from autobot.prediction.opponent_trajectory.inference import OpponentTrajectoryPredictor
from autobot.prediction.opponent_trajectory.model import build_model
from autobot.prediction.opponent_trajectory.simulator import TrajectorySimulator
from autobot.prediction.opponent_trajectory.train import train


def test_simulator_is_bounded_and_deterministic() -> None:
    config = TrajectoryConfig(observation_noise_std=0.005)
    first = TrajectorySimulator(config, seed=123).generate(200)
    second = TrajectorySimulator(config, seed=123).generate(200)
    np.testing.assert_array_equal(first, second)
    assert np.all((first[:, 0] >= 0) & (first[:, 0] <= config.arena_width))
    assert np.all((first[:, 1] >= 0) & (first[:, 1] <= config.arena_height))
    assert np.isfinite(first).all()


def test_behaviour_labels_and_configured_hazard_avoidance(tmp_path) -> None:
    pit = [[0.48, 0.48], [0.67, 0.48], [0.67, 0.67], [0.48, 0.67]]
    arena = ArenaMap(pits=[pit])
    config = TrajectoryConfig(observation_noise_std=0.0)
    states, labels = TrajectorySimulator(config, seed=31, arena=arena).generate_with_labels(300)
    assert states.shape == (300, 4)
    assert labels.shape == (300,)
    assert len(np.unique(labels)) > 1
    assert not any(point_in_polygon(point, pit) for point in states[:, :2])
    output = tmp_path / "arena.png"
    arena.visualize(output)
    assert output.is_file() and output.stat().st_size > 0


def test_dataset_and_model_shapes() -> None:
    config = TrajectoryConfig(dataset_size=20)
    dataset = TrajectoryDataset(config, size=3, seed=9)
    history, target = dataset[0]
    assert history.shape == (10, 4)
    assert target.shape == (5, 2)
    np.testing.assert_array_equal(history.numpy(), dataset[0][0].numpy())
    output = build_model(config)(history.unsqueeze(0))
    assert output.shape == (1, 5, 2)


def test_smoke_train_checkpoint_and_inference(tmp_path) -> None:
    config = TrajectoryConfig(
        dataset_size=40, hidden_size=16, num_layers=1, dropout=0.0,
        batch_size=8, epochs=1, patience=1, seed=7,
    )
    run_dir = train(config, tmp_path / "smoke", device="cpu")
    expected = {"config.json", "best_model.pt", "last_model.pt", "train_history.csv",
                "loss_curve.png", "arena_map.png"}
    assert expected.issubset({path.name for path in run_dir.iterdir()})
    predictor = OpponentTrajectoryPredictor.from_checkpoint(run_dir / "best_model.pt", device="cpu")
    raw = TrajectorySimulator(config, seed=88).generate(config.history_length)
    prediction = predictor.predict(raw)
    batched = predictor.predict(np.stack([raw, raw]))
    assert prediction.shape == (5, 2)
    assert batched.shape == (2, 5, 2)
    assert np.isfinite(prediction).all()
    assert json.loads((run_dir / "config.json").read_text())["seed"] == 7
