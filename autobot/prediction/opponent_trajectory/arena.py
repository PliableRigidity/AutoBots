"""Configurable arena geometry and hazard-aware steering utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PolygonPatch
import numpy as np

Polygon = list[list[float]]


def _closest_on_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    delta = end - start
    fraction = np.dot(point - start, delta) / max(float(np.dot(delta, delta)), 1e-12)
    return start + np.clip(fraction, 0.0, 1.0) * delta


def point_in_polygon(point: np.ndarray, polygon: Polygon) -> bool:
    """Return whether a point lies inside a simple polygon."""
    x, y = point
    inside = False
    vertices = np.asarray(polygon, dtype=float)
    previous = vertices[-1]
    for current in vertices:
        if (current[1] > y) != (previous[1] > y):
            crossing = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x < crossing:
                inside = not inside
        previous = current
    return inside


@dataclass
class ArenaMap:
    """Arena boundaries and optional measured/static feature polygons."""

    width: float = 1.15
    height: float = 1.15
    pits: list[Polygon] = field(default_factory=list)
    flipper: Polygon = field(default_factory=list)
    restricted: list[Polygon] = field(default_factory=list)

    @property
    def hazards(self) -> list[Polygon]:
        return [*self.pits, *self.restricted]

    def nearest_polygon_vector(self, point: np.ndarray, polygons: list[Polygon] | None = None) -> tuple[np.ndarray, float]:
        best_vector, best_distance = np.zeros(2), float("inf")
        for polygon in self.hazards if polygons is None else polygons:
            vertices = np.asarray(polygon, dtype=float)
            for index, start in enumerate(vertices):
                closest = _closest_on_segment(point, start, vertices[(index + 1) % len(vertices)])
                vector = point - closest
                distance = float(np.linalg.norm(vector))
                if distance < best_distance:
                    best_vector, best_distance = vector, distance
            if point_in_polygon(point, polygon):
                best_vector, best_distance = -best_vector, -best_distance
        return best_vector, best_distance

    def wall_repulsion(self, point: np.ndarray, margin: float) -> np.ndarray:
        force = np.zeros(2)
        distances = (point[0], self.width - point[0], point[1], self.height - point[1])
        directions = (np.array([1.0, 0.0]), np.array([-1.0, 0.0]),
                      np.array([0.0, 1.0]), np.array([0.0, -1.0]))
        for distance, direction in zip(distances, directions):
            if distance < margin:
                force += direction * (margin - distance) / margin
        return force

    def hazard_repulsion(self, point: np.ndarray, margin: float = 0.12) -> np.ndarray:
        vector, distance = self.nearest_polygon_vector(point)
        if not np.isfinite(distance) or distance >= margin:
            return np.zeros(2)
        norm = np.linalg.norm(vector)
        direction = vector / norm if norm > 1e-9 else np.array([1.0, 0.0])
        return direction * (margin - distance) / margin

    def is_safe(self, point: np.ndarray) -> bool:
        return (0 <= point[0] <= self.width and 0 <= point[1] <= self.height
                and not any(point_in_polygon(point, polygon) for polygon in self.hazards))

    def visualize(self, path: str | Path) -> None:
        """Save a labelled arena-map image."""
        figure, axis = plt.subplots(figsize=(6, 6))
        axis.add_patch(plt.Rectangle((0, 0), self.width, self.height, fill=False, lw=2, label="boundary"))
        for index, polygon in enumerate(self.pits):
            axis.add_patch(PolygonPatch(polygon, color="black", alpha=0.65, label="pit" if index == 0 else None))
        for index, polygon in enumerate(self.restricted):
            axis.add_patch(PolygonPatch(polygon, color="red", alpha=0.25, label="restricted" if index == 0 else None))
        if self.flipper:
            axis.add_patch(PolygonPatch(self.flipper, color="orange", alpha=0.35, label="flipper"))
        axis.set(xlim=(-0.03, self.width + 0.03), ylim=(-0.03, self.height + 0.03),
                 xlabel="x (m)", ylabel="y (m)", title="Configured arena map")
        axis.set_aspect("equal"); axis.grid(alpha=0.2)
        if self.pits or self.restricted or self.flipper:
            axis.legend()
        figure.tight_layout(); figure.savefig(path, dpi=150); plt.close(figure)


def arena_from_config(config: object) -> ArenaMap:
    return ArenaMap(config.arena_width, config.arena_height, config.pit_polygons,
                    config.flipper_polygon, config.restricted_regions)
