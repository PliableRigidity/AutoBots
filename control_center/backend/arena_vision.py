"""Arena calibration, rectification, background subtraction, and opponent tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time
from typing import Optional

import cv2
import numpy as np

from control_center.backend.vision import TagDetection
from control_center.models.state import (AcquisitionSource, OpponentState, RobotPose,
                                         TrackingState)


@dataclass(slots=True)
class OpponentCandidate:
    bbox_rect: tuple[int, int, int, int]
    centroid_rect: tuple[float, float]
    floor_rect: tuple[float, float]
    arena_xy: tuple[float, float]
    area: float
    confidence: float
    contour: np.ndarray


@dataclass(slots=True)
class ArenaVisionResult:
    self_pose: RobotPose = field(default_factory=RobotPose)
    opponent: OpponentState = field(default_factory=OpponentState)
    homography_valid: bool = False
    calibration_error: Optional[float] = None
    calibration_timestamp: Optional[str] = None
    background_loaded: bool = False
    background_progress: Optional[tuple[int, int]] = None
    landmark_status: str = "NOT RUN"
    candidates: list[OpponentCandidate] = field(default_factory=list)
    rectified_frame: Optional[np.ndarray] = None
    foreground_mask: Optional[np.ndarray] = None
    debug_frame: Optional[np.ndarray] = None
    debug_mode: str = "RAW"
    events: list[str] = field(default_factory=list)


class OpponentTracker:
    """Constant-velocity Kalman tracker in physical arena coordinates."""

    def __init__(self, prediction_timeout_s: float, lost_timeout_s: float) -> None:
        self.prediction_timeout_s = prediction_timeout_s
        self.lost_timeout_s = lost_timeout_s
        self.source = AcquisitionSource.NONE
        self.last_detection = 0.0
        self.last_update = 0.0
        self._active = False
        self._filter = cv2.KalmanFilter(4, 2)
        self._filter.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        self._filter.processNoiseCov = np.diag([2e-4, 2e-4, 8e-3, 8e-3]).astype(np.float32)
        self._filter.measurementNoiseCov = np.eye(2, dtype=np.float32) * 2e-3
        self._filter.errorCovPost = np.eye(4, dtype=np.float32)

    def clear(self) -> None:
        self._active = False
        self.source = AcquisitionSource.NONE
        self.last_detection = 0.0

    def acquire(self, x: float, y: float, timestamp: float, source: AcquisitionSource) -> None:
        self._filter.statePost = np.array([[x], [y], [0], [0]], np.float32)
        self._filter.statePre = self._filter.statePost.copy()
        self.last_detection = timestamp
        self.last_update = timestamp
        self.source = source
        self._active = True

    def update(self, measurement: tuple[float, float] | None, timestamp: float,
               confidence: float = 0.0) -> OpponentState:
        if not self._active:
            return OpponentState()
        dt = max(1e-3, min(0.25, timestamp - self.last_update))
        self.last_update = timestamp
        self._filter.transitionMatrix = np.array(
            [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
        prediction = self._filter.predict()
        detected = measurement is not None
        if detected:
            state = self._filter.correct(np.array([[measurement[0]], [measurement[1]]], np.float32))
            self.last_detection = timestamp
            tracking = TrackingState.TRACKED
        else:
            state = prediction
            age = timestamp - self.last_detection
            tracking = (TrackingState.PREDICTED if age <= self.prediction_timeout_s
                        else TrackingState.LOST)
        age = max(0.0, timestamp - self.last_detection)
        if age > self.lost_timeout_s:
            tracking = TrackingState.LOST
        return OpponentState(
            tracking_state=tracking, detected=detected,
            confidence=confidence if detected else max(0.0, 1.0 - age / self.lost_timeout_s),
            arena_x=float(state[0, 0]), arena_y=float(state[1, 0]),
            vx=float(state[2, 0]), vy=float(state[3, 0]), timestamp=timestamp,
            last_detection_age=age, acquisition_source=self.source)


class ArenaLandmarkDetector:
    """Non-authoritative landmark candidate detector for future auto-relocalization."""

    def detect(self, frame: np.ndarray) -> dict[str, object]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, (0, 0, 175), (180, 75, 255))
        contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if cv2.contourArea(c) > 500]
        confidence = min(0.5, sum(cv2.contourArea(c) for c in contours) / max(frame.shape[:2]) ** 2)
        return {"white_regions": contours, "confidence": confidence,
                "status": "CANDIDATES" if contours else "NO CANDIDATES"}


class ArenaVisionProcessor:
    """Runs entirely on the vision worker thread; UI methods only set small requests."""

    def __init__(self, config: dict, root: Path) -> None:
        self.log = logging.getLogger(__name__)
        self.root = root
        self.config = config
        vision = config.get("vision", {})
        arena = config.get("arena", {})
        self.arena_width = float(arena.get("width_m", config.get("arena_width_m", 1.15)))
        self.arena_height = float(arena.get("height_m", config.get("arena_height_m", 1.15)))
        self.rect_width = int(vision.get("rectified_width_px", 700))
        self.rect_height = int(vision.get("rectified_height_px", 700))
        self.threshold = int(vision.get("foreground_threshold", 28))
        self.min_area = float(vision.get("min_candidate_area", 350))
        self.max_area = float(vision.get("max_candidate_area", 80000))
        self.kernel_size = max(1, int(vision.get("morphology_kernel", 5)))
        self.self_exclusion_m = float(vision.get("self_exclusion_radius_m", 0.12))
        self.background_target = int(vision.get("background_frame_count", 60))
        self.calibration_path = root / str(vision.get("calibration_file", "config/arena_calibration.npz"))
        self.background_path = root / str(vision.get("background_file", "config/arena_background.png"))
        self.background_meta_path = self.background_path.with_suffix(".json")
        self.H: np.ndarray | None = None
        self.H_inv: np.ndarray | None = None
        self.calibration_error: float | None = None
        self.calibration_timestamp: str | None = None
        self.background: np.ndarray | None = None
        self._background_frames: list[np.ndarray] = []
        self._capture_background = False
        self._auto_acquire = False
        self._manual_roi: tuple[int, int, int, int] | None = None
        self._lock = threading.Lock()
        self.tracker = OpponentTracker(float(vision.get("prediction_timeout_s", 0.5)),
                                       float(vision.get("opponent_lost_timeout_s", 1.5)))
        self.landmarks = ArenaLandmarkDetector()
        self._landmark_status = "NOT RUN"
        self.debug_mode = "RAW"
        self._load_calibration()
        self._load_background()

    @property
    def calibrated(self) -> bool:
        return self.H is not None and self.H_inv is not None

    def calibrate(self, image_points: list[tuple[float, float]]) -> tuple[bool, str]:
        references = self.config.get("arena", {}).get("calibration_reference_points_m", [])
        if len(image_points) < 4 or len(references) != len(image_points):
            return False, "Calibration requires matching configured reference points"
        src = np.asarray(image_points, np.float32)
        if abs(cv2.contourArea(src.reshape(-1, 1, 2))) < 1000 or not cv2.isContourConvex(src.astype(np.int32)):
            return False, "Calibration points must form a large, non-crossing convex polygon"
        dst_m = np.asarray(references, np.float32)
        dst = np.column_stack((dst_m[:, 0] / self.arena_width * self.rect_width,
                               (self.arena_height - dst_m[:, 1]) / self.arena_height * self.rect_height))
        H, _ = cv2.findHomography(src, dst, cv2.RANSAC)
        if H is None or not np.isfinite(H).all() or abs(np.linalg.det(H)) < 1e-9:
            return False, "Homography calculation failed"
        projected = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
        error = float(np.sqrt(np.mean(np.sum((projected - dst) ** 2, axis=1))))
        if error > float(self.config.get("vision", {}).get("max_reprojection_error_px", 8.0)):
            return False, f"Reprojection error too high: {error:.2f}px"
        self.H, self.H_inv = H, np.linalg.inv(H)
        self.calibration_error = error
        self.calibration_timestamp = datetime.now(timezone.utc).isoformat()
        self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.calibration_path, homography=H, error=error,
                 timestamp=self.calibration_timestamp,
                 rectified_size=np.array([self.rect_width, self.rect_height]))
        self.background = None
        self.log.info("Arena calibration completed: error=%.3fpx", error)
        return True, f"Calibration saved; error {error:.2f}px"

    def request_background(self) -> tuple[bool, str]:
        if not self.calibrated:
            return False, "Calibrate the arena before capturing a background"
        with self._lock:
            self._background_frames = []
            self._capture_background = True
        self.log.info("Background capture started: target=%d", self.background_target)
        return True, f"Capturing background 0/{self.background_target}"

    def request_auto_acquire(self) -> None:
        with self._lock:
            self._auto_acquire = True

    def request_manual_roi(self, roi: tuple[int, int, int, int]) -> None:
        with self._lock:
            self._manual_roi = roi

    def clear_track(self) -> None:
        self.tracker.clear()

    def cycle_debug_mode(self) -> str:
        modes = ("RAW", "RECTIFIED", "FOREGROUND", "CANDIDATES", "SELF MASK")
        self.debug_mode = modes[(modes.index(self.debug_mode) + 1) % len(modes)]
        return self.debug_mode

    def pixel_to_arena(self, point: tuple[float, float]) -> tuple[float, float] | None:
        if self.H is None:
            return None
        rect = cv2.perspectiveTransform(np.array([[point]], np.float32), self.H)[0, 0]
        return (float(rect[0] / self.rect_width * self.arena_width),
                float((self.rect_height - rect[1]) / self.rect_height * self.arena_height))

    def arena_to_pixel(self, point: tuple[float, float]) -> tuple[float, float] | None:
        if self.H_inv is None:
            return None
        rect = np.array([[[point[0] / self.arena_width * self.rect_width,
                           (self.arena_height - point[1]) / self.arena_height * self.rect_height]]],
                        np.float32)
        raw = cv2.perspectiveTransform(rect, self.H_inv)[0, 0]
        return float(raw[0]), float(raw[1])

    def process(self, frame: np.ndarray, own: TagDetection | None,
                timestamp: float) -> ArenaVisionResult:
        result = ArenaVisionResult(homography_valid=self.calibrated,
                                   calibration_error=self.calibration_error,
                                   calibration_timestamp=self.calibration_timestamp,
                                   background_loaded=self.background is not None,
                                   landmark_status=self._landmark_status)
        if own is not None and self.calibrated:
            xy = self.pixel_to_arena(own.center)
            heading_point = (own.center[0] + 40 * np.cos(own.image_heading_rad),
                             own.center[1] + 40 * np.sin(own.image_heading_rad))
            heading_xy = self.pixel_to_arena(heading_point)
            if xy and heading_xy:
                theta = float(np.arctan2(heading_xy[1] - xy[1], heading_xy[0] - xy[0]))
                result.self_pose = RobotPose(x=xy[0], y=xy[1], theta=theta,
                                             valid=True, confidence=1.0)
        if not self.calibrated:
            result.opponent = self.tracker.update(None, timestamp)
            return result
        rectified = cv2.warpPerspective(frame, self.H, (self.rect_width, self.rect_height))
        result.rectified_frame = rectified
        result.debug_mode = self.debug_mode
        if self.debug_mode == "RECTIFIED":
            result.debug_frame = rectified.copy()
        with self._lock:
            capture_background = self._capture_background
        if capture_background:
            self._background_frames.append(rectified.copy())
            result.background_progress = (len(self._background_frames), self.background_target)
            if len(self._background_frames) >= self.background_target:
                self.background = np.median(np.stack(self._background_frames), axis=0).astype(np.uint8)
                self.background_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(self.background_path), self.background)
                self.background_meta_path.write_text(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "rectified_size": [self.rect_width, self.rect_height],
                    "calibration_timestamp": self.calibration_timestamp,
                    "frame_count": len(self._background_frames),
                }, indent=2), encoding="utf-8")
                with self._lock:
                    self._capture_background = False
                    self._background_frames = []
                result.background_loaded = True
                result.background_progress = None
                self.log.info("Background capture completed: %s", self.background_path)
                result.events.append(f"Background capture completed: {self.background_target} frames")
            return result
        if self.background is None or self.background.shape != rectified.shape:
            result.opponent = self.tracker.update(None, timestamp)
            return result
        candidates, mask, self_mask = self._foreground_candidates(rectified, result.self_pose)
        result.candidates, result.foreground_mask = candidates, mask
        if self.debug_mode == "FOREGROUND":
            result.debug_frame = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        elif self.debug_mode == "SELF MASK":
            result.debug_frame = cv2.cvtColor(self_mask, cv2.COLOR_GRAY2BGR)
        elif self.debug_mode == "CANDIDATES":
            debug = rectified.copy()
            for candidate in candidates:
                cv2.drawContours(debug, [candidate.contour], -1, (0, 165, 255), 2)
                x, y, w, h = candidate.bbox_rect
                cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 165, 255), 2)
            result.debug_frame = debug
        with self._lock:
            auto, manual_roi = self._auto_acquire, self._manual_roi
            self._auto_acquire = False
            self._manual_roi = None
        selected: OpponentCandidate | None = None
        source: AcquisitionSource | None = None
        direct_measurement: tuple[float, float] | None = None
        if manual_roi:
            selected = self._candidate_in_raw_roi(candidates, manual_roi)
            if selected is None:
                x, y, w, h = manual_roi
                arena = self.pixel_to_arena((x + w / 2, y + h))
                if arena:
                    self.tracker.acquire(*arena, timestamp, AcquisitionSource.MANUAL)
                    source = AcquisitionSource.MANUAL
                    direct_measurement = arena
                    result.events.append("Opponent manually acquired from selected ROI")
            else:
                source = AcquisitionSource.MANUAL
        elif auto and candidates:
            selected = max(candidates, key=lambda c: c.confidence)
            source = AcquisitionSource.AUTO
            result.events.append("Opponent auto-acquired")
        elif auto:
            result.events.append("No valid opponent candidate found")
        elif self.tracker.source != AcquisitionSource.NONE and candidates:
            current = self.tracker.update(None, timestamp)
            if current.arena_x is not None and current.arena_y is not None:
                selected = min(candidates, key=lambda c: (c.arena_xy[0] - current.arena_x) ** 2 +
                                                         (c.arena_xy[1] - current.arena_y) ** 2)
        if selected and source:
            self.tracker.acquire(*selected.arena_xy, timestamp, source)
            if source == AcquisitionSource.MANUAL:
                result.events.append("Opponent manually acquired")
        measurement = selected.arena_xy if selected else direct_measurement
        tracked = self.tracker.update(measurement, timestamp,
                                      selected.confidence if selected else 0.0)
        if selected:
            tracked.bbox = self._rect_bbox_to_raw(selected.bbox_rect)
            tracked.floor_point = self.arena_to_pixel(selected.arena_xy)
            if tracked.bbox:
                x, y, w, h = tracked.bbox
                tracked.image_x, tracked.image_y = x + w / 2, y + h / 2
        result.opponent = tracked
        return result

    def detect_landmarks(self, frame: np.ndarray) -> dict[str, object]:
        found = self.landmarks.detect(frame)
        self._landmark_status = str(found["status"])
        return found

    def _foreground_candidates(
            self, frame: np.ndarray, self_pose: RobotPose
    ) -> tuple[list[OpponentCandidate], np.ndarray, np.ndarray]:
        current_lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        background_lab = cv2.cvtColor(self.background, cv2.COLOR_BGR2LAB)
        diff = cv2.absdiff(current_lab, background_lab)
        magnitude = np.max(diff, axis=2)
        mask = np.where(magnitude >= self.threshold, 255, 0).astype(np.uint8)
        kernel = np.ones((self.kernel_size, self.kernel_size), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        self_mask = np.full(mask.shape, 255, np.uint8)
        if self_pose.valid and self_pose.x is not None and self_pose.y is not None:
            center = (int(self_pose.x / self.arena_width * self.rect_width),
                      int((self.arena_height - self_pose.y) / self.arena_height * self.rect_height))
            radius = int(self.self_exclusion_m / self.arena_width * self.rect_width)
            cv2.circle(mask, center, radius, 0, -1)
            cv2.circle(self_mask, center, radius, 0, -1)
        self._apply_static_masks(mask)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[OpponentCandidate] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if not self.min_area <= area <= self.max_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            bottom = contour[contour[:, 0, 1].argmax(), 0].astype(float)
            arena = (float(bottom[0] / self.rect_width * self.arena_width),
                     float((self.rect_height - bottom[1]) / self.rect_height * self.arena_height))
            confidence = min(1.0, max(0.05, area / max(self.min_area * 8, 1)))
            candidates.append(OpponentCandidate((x, y, w, h), (x + w / 2, y + h / 2),
                                                tuple(bottom), arena, area, confidence, contour))
        return candidates, mask, self_mask

    def _apply_static_masks(self, mask: np.ndarray) -> None:
        for pit_name in ("pit_1", "pit_2"):
            pit = self.config.get("arena", {}).get(pit_name, {})
            if all(pit.get(key) is not None for key in ("x", "y", "radius")):
                center = (int(float(pit["x"]) / self.arena_width * self.rect_width),
                          int((self.arena_height - float(pit["y"])) / self.arena_height * self.rect_height))
                radius = int(float(pit["radius"]) / self.arena_width * self.rect_width)
                cv2.circle(mask, center, radius, 0, -1)

    def _candidate_in_raw_roi(self, candidates: list[OpponentCandidate], roi: tuple[int, int, int, int]) -> OpponentCandidate | None:
        x, y, w, h = roi
        for candidate in candidates:
            point = self.arena_to_pixel(candidate.arena_xy)
            if point and x <= point[0] <= x + w and y <= point[1] <= y + h:
                return candidate
        return None

    def _rect_bbox_to_raw(self, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        if self.H_inv is None:
            return None
        x, y, w, h = bbox
        corners = np.array([[[x, y], [x + w, y], [x + w, y + h], [x, y + h]]], np.float32)
        raw = cv2.perspectiveTransform(corners, self.H_inv)[0]
        x0, y0 = np.min(raw, axis=0).astype(int)
        x1, y1 = np.max(raw, axis=0).astype(int)
        return int(x0), int(y0), int(x1 - x0), int(y1 - y0)

    def _load_calibration(self) -> None:
        if not self.calibration_path.exists():
            return
        try:
            data = np.load(self.calibration_path, allow_pickle=False)
            H = np.asarray(data["homography"], dtype=float)
            if H.shape == (3, 3) and np.isfinite(H).all() and abs(np.linalg.det(H)) > 1e-9:
                self.H, self.H_inv = H, np.linalg.inv(H)
                self.calibration_error = float(data["error"])
                self.calibration_timestamp = str(data["timestamp"])
        except Exception:
            self.log.exception("Saved arena calibration is invalid; ignoring it")

    def _load_background(self) -> None:
        if not self.background_path.exists() or not self.calibrated:
            return
        if self.background_meta_path.exists():
            try:
                metadata = json.loads(self.background_meta_path.read_text(encoding="utf-8"))
                if metadata.get("calibration_timestamp") != self.calibration_timestamp:
                    self.log.warning("Saved background belongs to a different calibration; ignoring it")
                    return
            except Exception:
                self.log.exception("Background metadata is invalid; ignoring saved background")
                return
        image = cv2.imread(str(self.background_path))
        if image is not None and image.shape[:2] == (self.rect_height, self.rect_width):
            self.background = image
