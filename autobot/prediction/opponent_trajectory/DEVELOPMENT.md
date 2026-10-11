# Trajectory predictor development log

All figures below are lightweight reproducibility checks, not final model claims. Generated runs
live under `runs/trajectory_predictor/` and are intentionally ignored by Git.

## Version 1 — baseline

- Preserved model/API: two-layer 96-unit GRU with an MLP offset head.
- Data: original six-mode synthetic generator, 800 samples, 5-step horizon, 25 Hz.
- Training: 3 epochs, batch 64, AdamW at 1e-3, CPU.
- Test: 3 tests passed at the time of the baseline run.
- Metrics: MAE 1.419 cm, ADE 2.221 cm, FDE 2.988 cm.
- Run: `smoke_validation`.

## Version 2 — richer motion

- Added 15 labelled motion behaviours: straight, acceleration, braking, reversing, arcs, smooth
  and sudden turns, stop/go, charge, retreat, evasive, zig-zag, wall-following, aggressive, and
  defensive motion.
- Added configurable maximum speed, acceleration, angular velocity, motion noise, observation
  noise, timestep, arena dimensions, and wall margin.
- Motion uses bounded acceleration/turning and continuous integration; no position teleportation.
- Existing LR scheduling, early stopping, saved configuration, and checkpoint behavior retained.
- Smoke: 5,000 samples, 5 epochs, batch 256, 5 steps, RTX 4090 Laptop GPU.
- Metrics: MAE 1.109 cm, ADE 1.744 cm, FDE 2.962 cm.
- Warm single-sequence inference (500 calls after 30 warmups): 1.251 ms CPU, 1.043 ms CUDA;
  95,530 trainable parameters. This is an initial Python API measurement, not the full v19 suite.
- Conclusion: better overall ADE than v1 despite substantially more diverse motion. Use a full
  100k+ run before treating the small FDE difference as significant.
- Run: `v02_motion_smoke`.

## Version 3 — horizon analysis

- Added configurable horizon and tracking frequency CLI arguments.
- Added per-step MSE, MAE, mean displacement error, and median displacement error.
- Added CSV output and error plots by both future step and physical time.
- Smoke: 3,000 samples, 4 epochs, batch 256, 15 steps (0.6 s), 25 Hz, GPU.
- Metrics: overall ADE 7.525 cm and FDE 15.523 cm. ADE increases from 1.667 cm at 40 ms to
  15.523 cm at 600 ms, demonstrating the expected uncertainty growth.
- Run: `v03_horizon15_smoke`.

## Version 4 — arena-aware trajectories

- Added `ArenaMap` with boundary, pit, flipper, and restricted-region polygons.
- Added wall/hazard repulsion and hazard approach/circle behaviours.
- Added arena visualization to every run. Default pits remain empty because repository calibration
  does not contain measured pit geometry.
- Tests cover configured hazard avoidance and map rendering.
- Smoke: illustrative central pit, 1,000 samples, 2 epochs, batch 128, 5 steps, GPU.
- Metrics: MAE 2.891 cm, ADE 4.521 cm, FDE 6.072 cm.
- Conclusion: functionality is validated, but this deliberately short run is undertrained and is
  not better than v2. The arena-aware generator is retained; v2 remains the best measured model.
- Run: `v04_arena_smoke`.

## Next version

Version 5 should add a feature-builder abstraction and compare the original four state features
against wall/pit context using identical seeds and datasets. It should not become the default
unless the controlled comparison improves held-out trajectory error.
