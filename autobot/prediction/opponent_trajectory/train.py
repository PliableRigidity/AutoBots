"""Command-line training entry point for the GRU predictor."""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from .config import TrajectoryConfig
from .dataset import create_datasets
from .model import build_model
from .arena import arena_from_config


def set_deterministic(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def trajectory_loss(prediction: torch.Tensor, target: torch.Tensor, velocity_weight: float) -> torch.Tensor:
    loss = nn.functional.mse_loss(prediction, target)
    if velocity_weight > 0 and prediction.shape[1] > 1:
        loss = loss + velocity_weight * nn.functional.mse_loss(
            torch.diff(prediction, dim=1), torch.diff(target, dim=1)
        )
    return loss


def save_checkpoint(path: Path, model: nn.Module, optimizer: torch.optim.Optimizer,
                    config: TrajectoryConfig, epoch: int, validation_loss: float) -> None:
    torch.save({
        "model_state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict(),
        "config": config.to_dict(), "epoch": epoch, "validation_loss": validation_loss,
        "normalization": {"position_scale": [config.arena_width, config.arena_height],
                          "velocity_scale": config.velocity_scale},
    }, path)


def _mean_loss(model: nn.Module, loader: DataLoader, device: torch.device,
               velocity_weight: float, optimizer: torch.optim.Optimizer | None = None) -> float:
    training = optimizer is not None
    model.train(training)
    total, count = 0.0, 0
    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for history, target in loader:
            history, target = history.to(device), target.to(device)
            if optimizer:
                optimizer.zero_grad(set_to_none=True)
            loss = trajectory_loss(model(history), target, velocity_weight)
            if optimizer:
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()
            total += loss.item() * history.shape[0]
            count += history.shape[0]
    return total / max(count, 1)


def train(config: TrajectoryConfig, output_dir: Path, device: str | None = None) -> Path:
    """Train a model and return the run directory."""
    set_deterministic(config.seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "config.json").write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    arena_from_config(config).visualize(output_dir / "arena_map.png")
    train_data, validation_data, _ = create_datasets(config)
    generator = torch.Generator().manual_seed(config.seed)
    train_loader = DataLoader(train_data, batch_size=config.batch_size, shuffle=True,
                              num_workers=0, generator=generator)
    validation_loader = DataLoader(validation_data, batch_size=config.batch_size, num_workers=0)
    selected_device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = build_model(config).to(selected_device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate,
                                  weight_decay=config.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=2)
    rows: list[dict[str, float | int]] = []
    best_loss, stale = float("inf"), 0
    for epoch in range(1, config.epochs + 1):
        train_loss = _mean_loss(model, train_loader, selected_device,
                                config.velocity_loss_weight, optimizer)
        validation_loss = _mean_loss(model, validation_loader, selected_device,
                                     config.velocity_loss_weight)
        scheduler.step(validation_loss)
        learning_rate = optimizer.param_groups[0]["lr"]
        rows.append({"epoch": epoch, "train_loss": train_loss,
                     "validation_loss": validation_loss, "learning_rate": learning_rate})
        save_checkpoint(output_dir / "last_model.pt", model, optimizer, config, epoch, validation_loss)
        if validation_loss < best_loss:
            best_loss, stale = validation_loss, 0
            save_checkpoint(output_dir / "best_model.pt", model, optimizer, config, epoch, validation_loss)
        else:
            stale += 1
        print(f"epoch={epoch:03d} train={train_loss:.6f} val={validation_loss:.6f} "
              f"lr={learning_rate:.2e} best={best_loss:.6f}")
        if stale >= config.patience:
            print(f"early stopping after {epoch} epochs")
            break
    with (output_dir / "train_history.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    figure, axis = plt.subplots(figsize=(7, 4))
    axis.plot([r["epoch"] for r in rows], [r["train_loss"] for r in rows], label="train")
    axis.plot([r["epoch"] for r in rows], [r["validation_loss"] for r in rows], label="validation")
    axis.set(xlabel="Epoch", ylabel="Loss (normalized MSE)", title="Trajectory predictor training")
    axis.grid(alpha=0.3); axis.legend(); figure.tight_layout()
    figure.savefig(output_dir / "loss_curve.png", dpi=150); plt.close(figure)
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--output-root", type=Path, default=Path("runs/trajectory_predictor"))
    parser.add_argument("--dataset-size", type=int, default=TrajectoryConfig.dataset_size)
    parser.add_argument("--epochs", type=int, default=TrajectoryConfig.epochs)
    parser.add_argument("--batch-size", type=int, default=TrajectoryConfig.batch_size)
    parser.add_argument("--learning-rate", type=float, default=TrajectoryConfig.learning_rate)
    parser.add_argument("--prediction-horizon", type=int, default=TrajectoryConfig.prediction_horizon)
    parser.add_argument("--tracking-frequency", type=float, default=1.0 / TrajectoryConfig.timestep)
    parser.add_argument("--seed", type=int, default=TrajectoryConfig.seed)
    parser.add_argument("--device", choices=["cpu", "cuda"], default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.prediction_horizon < 1 or args.tracking_frequency <= 0:
        raise SystemExit("prediction horizon and tracking frequency must be positive")
    config = TrajectoryConfig(dataset_size=args.dataset_size, epochs=args.epochs,
                              batch_size=args.batch_size, learning_rate=args.learning_rate, seed=args.seed)
    config.prediction_horizon = args.prediction_horizon
    config.timestep = 1.0 / args.tracking_frequency
    run_name = args.run_name or datetime.now().strftime("gru_%Y%m%d_%H%M%S")
    path = train(config, args.output_root / run_name, args.device)
    print(f"run saved to {path}")


if __name__ == "__main__":
    main()
