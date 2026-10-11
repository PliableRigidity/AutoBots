"""Evaluate a checkpoint on the deterministic held-out test split."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.utils.data import DataLoader

from .config import TrajectoryConfig
from .dataset import create_datasets
from .inference import OpponentTrajectoryPredictor


def evaluate(checkpoint_path: Path, examples: int = 5, device: str | None = None) -> dict[str, float]:
    predictor = OpponentTrajectoryPredictor.from_checkpoint(checkpoint_path, device)
    config = predictor.config
    _, _, test_data = create_datasets(config)
    loader = DataLoader(test_data, batch_size=config.batch_size, num_workers=0)
    predictions, targets = [], []
    for history, target in loader:
        # Dataset tensors are normalized for training; the public inference API
        # intentionally accepts tracker states in physical SI units.
        physical_history = history.numpy().copy()
        physical_history[..., 0] *= config.arena_width
        physical_history[..., 1] *= config.arena_height
        physical_history[..., 2:4] *= config.velocity_scale
        predictions.append(predictor.predict(physical_history))
        targets.append(config.denormalize_positions(target.numpy()))
    predicted = np.concatenate(predictions)
    actual = np.concatenate(targets)
    error = predicted - actual
    distances = np.linalg.norm(error, axis=-1)
    horizon_metrics = []
    for index in range(config.prediction_horizon):
        step_error = error[:, index]
        step_distance = distances[:, index]
        horizon_metrics.append({
            "step": index + 1,
            "time_s": (index + 1) * config.timestep,
            "mse_m2": float(np.mean(step_error ** 2)),
            "mae_m": float(np.mean(np.abs(step_error))),
            "average_displacement_error_m": float(np.mean(step_distance)),
            "median_displacement_error_m": float(np.median(step_distance)),
        })
    metrics = {
        "mse_m2": float(np.mean(error ** 2)),
        "mae_m": float(np.mean(np.abs(error))),
        "mae_cm": float(np.mean(np.abs(error)) * 100),
        "final_displacement_error_m": float(np.mean(distances[:, -1])),
        "final_displacement_error_cm": float(np.mean(distances[:, -1]) * 100),
        "average_displacement_error_m": float(np.mean(distances)),
        "average_displacement_error_cm": float(np.mean(distances) * 100),
        "test_samples": int(len(test_data)),
        "tracking_frequency_hz": config.tracking_frequency_hz,
        "prediction_horizon": config.prediction_horizon,
        "per_horizon": horizon_metrics,
    }
    run_dir = checkpoint_path.parent
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with (run_dir / "horizon_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=horizon_metrics[0].keys())
        writer.writeheader(); writer.writerows(horizon_metrics)
    _plot_horizon(horizon_metrics, run_dir / "error_by_horizon_step.png", "step", "Future timestep")
    _plot_horizon(horizon_metrics, run_dir / "error_by_horizon_time.png", "time_s", "Prediction time (s)")
    prediction_dir = run_dir / "predictions"; prediction_dir.mkdir(exist_ok=True)
    for index in range(min(examples, len(test_data))):
        normalized_history, _ = test_data[index]
        history = normalized_history.numpy().copy()
        history[:, 0] *= config.arena_width; history[:, 1] *= config.arena_height
        truth, estimate = actual[index], predicted[index]
        figure, axis = plt.subplots(figsize=(5, 5))
        axis.plot(history[:, 0], history[:, 1], "o-", label="observed history")
        axis.plot(truth[:, 0], truth[:, 1], "o-", label="ground truth")
        axis.plot(estimate[:, 0], estimate[:, 1], "o--", label="prediction")
        axis.set(xlim=(0, config.arena_width), ylim=(0, config.arena_height),
                 xlabel="x (m)", ylabel="y (m)", title=f"Test example {index + 1}")
        axis.set_aspect("equal", adjustable="box"); axis.grid(alpha=0.3); axis.legend()
        figure.tight_layout(); figure.savefig(prediction_dir / f"example_{index + 1:03d}.png", dpi=150)
        plt.close(figure)
    print(json.dumps(metrics, indent=2))
    return metrics


def _plot_horizon(rows: list[dict[str, float]], path: Path, x_key: str, x_label: str) -> None:
    figure, axis = plt.subplots(figsize=(7, 4))
    x = [row[x_key] for row in rows]
    axis.plot(x, [row["average_displacement_error_m"] * 100 for row in rows], "o-", label="mean")
    axis.plot(x, [row["median_displacement_error_m"] * 100 for row in rows], "o--", label="median")
    axis.set(xlabel=x_label, ylabel="Displacement error (cm)", title="Prediction error by horizon")
    axis.grid(alpha=0.3); axis.legend(); figure.tight_layout(); figure.savefig(path, dpi=150); plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--examples", type=int, default=5)
    parser.add_argument("--device", choices=["cpu", "cuda"], default=None)
    args = parser.parse_args()
    evaluate(args.checkpoint, args.examples, args.device)


if __name__ == "__main__":
    main()
