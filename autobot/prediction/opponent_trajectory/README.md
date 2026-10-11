# Opponent trajectory predictor

This self-contained subsystem predicts five future opponent positions from ten recent tracked
states. It is runnable without a camera or robot and is deliberately separated from perception,
planning, and control.

## Design

Each input timestep is `[x, y, vx, vy]` in metres and metres/second. The default input is
`[batch, 10, 4]`; the target/output is `[batch, 5, 2]`. Positions are scaled by the 1.15 m arena
dimensions and velocities by a stored velocity scale. The checkpoint contains the complete
configuration so inference applies the same normalization.

The simulator combines straight driving, acceleration/braking, arcs, smooth and sudden turns,
reversals, stop/go, charge/retreat, evasive and zig-zag motion, wall following, and aggressive or
defensive movement. Speed, acceleration, angular velocity, motion noise, observation noise,
timestep, and arena size are configurable. Motion is acceleration-limited and continuous.
Optional position noise emulates a future vision tracker. Samples are generated deterministically
by index and are not cached to disk. Internal behaviour labels are retained for future intent work.
The model is a two-layer GRU (96 hidden units by default) followed by a small MLP. The MLP
predicts offsets from the last observed position, providing a useful stationary baseline.

## Install and train

From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m autobot.prediction.opponent_trajectory.train --run-name baseline
```

The laptop-friendly default is 20,000 sequences (80/10/10 split), 30 epochs, and batch size 256.
Override these with `--dataset-size`, `--epochs`, and `--batch-size`. CUDA is selected when
available; pass `--device cpu` to force CPU.

Horizon and tracker frequency are also configurable:

```powershell
python -m autobot.prediction.opponent_trajectory.train --run-name horizon15 `
  --prediction-horizon 15 --tracking-frequency 25
```

Evaluate the best checkpoint:

```powershell
python -m autobot.prediction.opponent_trajectory.evaluate runs/trajectory_predictor/baseline/best_model.pt
```

Each run contains configuration, best/last checkpoints, CSV history, loss plot, JSON metrics, and
example prediction plots. Evaluation also writes per-step metrics to `horizon_metrics.csv` and
plots displacement error by future step and seconds. Generated runs and checkpoints are ignored.

## Arena geometry

`ArenaMap` represents the measured boundary plus optional pit, flipper, and restricted-zone
polygons. No pit coordinates are assumed by default. Configure measured geometry through
`TrajectoryConfig.pit_polygons`, `flipper_polygon`, and `restricted_regions`. The simulator can
avoid, approach, or circle hazards and saves `arena_map.png` with every training run.

```python
from autobot.prediction.opponent_trajectory import TrajectoryConfig

config = TrajectoryConfig(
    pit_polygons=[[[0.48, 0.48], [0.67, 0.48], [0.67, 0.67], [0.48, 0.67]]]
)
```

Use only physically measured coordinates for real experiments; the example above is illustrative.

## Inference

```python
import numpy as np
from autobot.prediction.opponent_trajectory import OpponentTrajectoryPredictor

predictor = OpponentTrajectoryPredictor.from_checkpoint(
    "runs/trajectory_predictor/baseline/best_model.pt"
)
history = np.zeros((10, 4), dtype=np.float32)  # tracker states in SI units
future_positions = predictor.predict(history)  # shape: (5, 2), metres
```

`predict()` also accepts `[batch, 10, 4]`. Later, the vision/tracking subsystem only needs to
supply ordered arena-coordinate states; it does not need to know about GRU internals.

Development results and version comparisons are recorded in [DEVELOPMENT.md](DEVELOPMENT.md).
