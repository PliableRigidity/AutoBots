"""Synthetic, continuous 2D opponent motion generator."""

from __future__ import annotations

from enum import IntEnum

import numpy as np

from .arena import ArenaMap, arena_from_config
from .config import TrajectoryConfig


class MotionBehaviour(IntEnum):
    STRAIGHT = 0
    ACCELERATE = 1
    BRAKE = 2
    REVERSE = 3
    ARC = 4
    SMOOTH_TURN = 5
    SUDDEN_TURN = 6
    STOP_GO = 7
    CHARGE = 8
    RETREAT = 9
    EVASIVE = 10
    ZIGZAG = 11
    WALL_FOLLOW = 12
    AGGRESSIVE = 13
    DEFENSIVE = 14
    HAZARD_APPROACH = 15
    HAZARD_CIRCLE = 16


class TrajectorySimulator:
    """Generate labelled, plausible bounded trajectories using acceleration limits."""

    def __init__(self, config: TrajectoryConfig, seed: int | None = None,
                 arena: ArenaMap | None = None) -> None:
        self.config = config
        self.rng = np.random.default_rng(config.seed if seed is None else seed)
        self.arena = arena or arena_from_config(config)

    def generate(self, length: int, observation_noise: bool = True) -> np.ndarray:
        states, _ = self.generate_with_labels(length, observation_noise)
        return states

    def generate_with_labels(self, length: int, observation_noise: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Return states ``[N,4]`` and a behaviour label for each timestep."""
        if length < 2:
            raise ValueError("length must be at least 2")
        c, rng, dt = self.config, self.rng, self.config.timestep
        position = self._safe_start()
        heading = rng.uniform(-np.pi, np.pi)
        speed = rng.uniform(0.05, c.max_speed * 0.65)
        velocity = speed * np.array([np.cos(heading), np.sin(heading)])
        states = np.empty((length, 4), dtype=np.float32)
        labels = np.empty(length, dtype=np.int64)
        behaviour = self._choose_behaviour()
        segment_end = int(rng.integers(8, 24))
        phase = rng.uniform(0, 2 * np.pi)
        turn_rate = rng.uniform(-c.max_angular_velocity * 0.5, c.max_angular_velocity * 0.5)

        for index in range(length):
            if index >= segment_end:
                behaviour = self._choose_behaviour()
                segment_end = index + int(rng.integers(8, 26))
                turn_rate = rng.uniform(-c.max_angular_velocity, c.max_angular_velocity)
                phase = rng.uniform(0, 2 * np.pi)
            acceleration, steering = self._controls(behaviour, index, phase, position, velocity, turn_rate)
            acceleration += rng.normal(0.0, c.motion_noise_std)
            acceleration = float(np.clip(acceleration, -c.max_acceleration, c.max_acceleration))
            steering = float(np.clip(steering, -c.max_angular_velocity, c.max_angular_velocity))
            avoidance = 2.4 * self.arena.wall_repulsion(position + velocity * 0.18, c.wall_margin)
            avoidance += 3.2 * self.arena.hazard_repulsion(position + velocity * 0.18)
            if np.linalg.norm(avoidance) > 1e-8 and behaviour != MotionBehaviour.HAZARD_APPROACH:
                target = np.arctan2(avoidance[1], avoidance[0])
                steering += 2.0 * _angle_difference(target, heading)

            speed = float(np.clip(speed + acceleration * dt, 0.0, c.max_speed))
            if behaviour == MotionBehaviour.REVERSE and speed < 0.025:
                heading += np.pi
                speed = min(0.10, c.max_speed)
                behaviour = MotionBehaviour.STRAIGHT
            heading += np.clip(steering, -c.max_angular_velocity, c.max_angular_velocity) * dt
            desired = speed * np.array([np.cos(heading), np.sin(heading)])
            velocity = 0.65 * velocity + 0.35 * desired
            position += velocity * dt
            position, velocity = self._reflect_boundaries(position, velocity)
            if not self.arena.is_safe(position):
                position -= velocity * dt
                velocity *= -0.45
                heading = float(np.arctan2(velocity[1], velocity[0]))
            states[index] = (*position, *velocity)
            labels[index] = int(behaviour)

        if observation_noise and c.observation_noise_std > 0:
            states[:, :2] += rng.normal(0.0, c.observation_noise_std, (length, 2))
            states[:, 0] = np.clip(states[:, 0], 0.0, c.arena_width)
            states[:, 1] = np.clip(states[:, 1], 0.0, c.arena_height)
            states[1:, 2:4] = np.diff(states[:, :2], axis=0) / dt
            states[0, 2:4] = states[1, 2:4]
        return states, labels

    def _safe_start(self) -> np.ndarray:
        for _ in range(1000):
            point = self.rng.uniform([0.10, 0.10], [self.arena.width - 0.10, self.arena.height - 0.10])
            if self.arena.is_safe(point):
                return point
        raise RuntimeError("arena has no safe starting location")

    def _choose_behaviour(self) -> MotionBehaviour:
        upper = len(MotionBehaviour) if self.arena.hazards else int(MotionBehaviour.HAZARD_APPROACH)
        return MotionBehaviour(int(self.rng.integers(0, upper)))

    def _controls(self, behaviour: MotionBehaviour, index: int, phase: float,
                  position: np.ndarray, velocity: np.ndarray, turn_rate: float) -> tuple[float, float]:
        c, rng, t = self.config, self.rng, index * self.config.timestep
        acceleration, steering = 0.0, 0.0
        if behaviour == MotionBehaviour.ACCELERATE: acceleration = c.max_acceleration * 0.55
        elif behaviour == MotionBehaviour.BRAKE: acceleration = -c.max_acceleration * 0.8
        elif behaviour == MotionBehaviour.REVERSE: acceleration = -c.max_acceleration
        elif behaviour == MotionBehaviour.ARC: steering = turn_rate * 0.55
        elif behaviour == MotionBehaviour.SMOOTH_TURN: steering = c.max_angular_velocity * 0.5 * np.sin(t * 2.2 + phase)
        elif behaviour == MotionBehaviour.SUDDEN_TURN: steering = np.sign(turn_rate) * c.max_angular_velocity
        elif behaviour == MotionBehaviour.STOP_GO: acceleration = c.max_acceleration * (-0.7 if (index // 10) % 2 == 0 else 0.65)
        elif behaviour == MotionBehaviour.CHARGE:
            acceleration = c.max_acceleration * 0.85
            steering = _steer_toward(position, np.array([c.arena_width / 2, c.arena_height / 2]), velocity)
        elif behaviour == MotionBehaviour.RETREAT:
            acceleration = c.max_acceleration * 0.45
            centre = np.array([c.arena_width / 2, c.arena_height / 2])
            steering = _steer_toward(position, position - (centre - position), velocity)
        elif behaviour == MotionBehaviour.EVASIVE: steering = c.max_angular_velocity * 0.8 * np.sin(t * 8.0 + phase)
        elif behaviour == MotionBehaviour.ZIGZAG: steering = c.max_angular_velocity * 0.7 * (1 if np.sin(t * 5.0 + phase) >= 0 else -1)
        elif behaviour == MotionBehaviour.WALL_FOLLOW:
            distances = [position[0], c.arena_width-position[0], position[1], c.arena_height-position[1]]
            wall = int(np.argmin(distances)); targets = [np.pi/2, -np.pi/2, 0.0, np.pi]
            heading = np.arctan2(velocity[1], velocity[0]); steering = 2.0 * _angle_difference(targets[wall], heading)
            acceleration = c.max_acceleration * 0.15
        elif behaviour == MotionBehaviour.AGGRESSIVE:
            acceleration = c.max_acceleration * 0.7; steering = rng.normal(0, c.max_angular_velocity * 0.18)
        elif behaviour == MotionBehaviour.DEFENSIVE:
            acceleration = -c.max_acceleration * 0.1; steering = c.max_angular_velocity * 0.65 * np.sin(t * 6 + phase)
        elif behaviour in (MotionBehaviour.HAZARD_APPROACH, MotionBehaviour.HAZARD_CIRCLE) and self.arena.hazards:
            target = np.asarray(self.arena.hazards[0]).mean(axis=0)
            target_heading = np.arctan2(target[1] - position[1], target[0] - position[0])
            if behaviour == MotionBehaviour.HAZARD_CIRCLE: target_heading += np.pi / 2
            heading = np.arctan2(velocity[1], velocity[0]); steering = 2.2 * _angle_difference(target_heading, heading)
            acceleration = c.max_acceleration * 0.15
        return acceleration, steering

    def _reflect_boundaries(self, position: np.ndarray, velocity: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        for axis, bound in enumerate((self.arena.width, self.arena.height)):
            if position[axis] < 0:
                position[axis] = -position[axis]; velocity[axis] = abs(velocity[axis]) * 0.65
            elif position[axis] > bound:
                position[axis] = 2 * bound - position[axis]; velocity[axis] = -abs(velocity[axis]) * 0.65
        return np.clip(position, [0, 0], [self.arena.width, self.arena.height]), velocity


def _angle_difference(target: float, current: float) -> float:
    return float((target - current + np.pi) % (2 * np.pi) - np.pi)


def _steer_toward(position: np.ndarray, target: np.ndarray, velocity: np.ndarray) -> float:
    desired = np.arctan2(target[1] - position[1], target[0] - position[0])
    current = np.arctan2(velocity[1], velocity[0])
    return 2.0 * _angle_difference(desired, current)
