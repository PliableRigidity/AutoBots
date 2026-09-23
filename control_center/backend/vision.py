"""Reusable AprilTag detection extracted from the original camera experiment."""

from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(slots=True)
class TagDetection:
    tag_id: int
    corners: np.ndarray
    center: tuple[int, int]
    image_heading_rad: float
    camera_tvec: np.ndarray | None = None
    camera_rvec: np.ndarray | None = None


class AprilTagTracker:
    FAMILY_MAP = {
        "DICT_APRILTAG_16h5": cv2.aruco.DICT_APRILTAG_16h5,
        "DICT_APRILTAG_25h9": cv2.aruco.DICT_APRILTAG_25h9,
        "DICT_APRILTAG_36h10": cv2.aruco.DICT_APRILTAG_36h10,
        "DICT_APRILTAG_36h11": cv2.aruco.DICT_APRILTAG_36h11,
    }

    def __init__(self, family: str, self_tag_id: int, tag_size_m: float | None = None,
                 camera_matrix: list | None = None,
                 distortion_coefficients: list | None = None) -> None:
        dictionary_id = self.FAMILY_MAP.get(family, cv2.aruco.DICT_APRILTAG_36h11)
        dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        self._detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        self.self_tag_id = self_tag_id
        self.tag_size_m = tag_size_m
        self.camera_matrix = (np.asarray(camera_matrix, np.float64)
                              if camera_matrix is not None else None)
        self.distortion = (np.asarray(distortion_coefficients, np.float64)
                           if distortion_coefficients is not None else None)

    def detect(self, frame_bgr: np.ndarray) -> tuple[list[TagDetection], TagDetection | None]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        detections: list[TagDetection] = []
        if ids is None:
            return detections, None
        for raw_corners, raw_id in zip(corners, ids.flatten()):
            points = raw_corners.reshape(4, 2)
            center = tuple(np.mean(points, axis=0).astype(int))
            # Heading is image-space only. It must not be used as world heading before calibration.
            top_midpoint = (points[0] + points[1]) / 2.0
            heading = math.atan2(float(top_midpoint[1] - center[1]), float(top_midpoint[0] - center[0]))
            detection = TagDetection(int(raw_id), points, center, heading)
            self._estimate_pose(detection)
            detections.append(detection)
        own = next((item for item in detections if item.tag_id == self.self_tag_id), None)
        return detections, own

    def _estimate_pose(self, detection: TagDetection) -> None:
        if self.tag_size_m is None or self.camera_matrix is None or self.distortion is None:
            return
        half = float(self.tag_size_m) / 2.0
        object_points = np.array([[-half, half, 0], [half, half, 0],
                                  [half, -half, 0], [-half, -half, 0]], np.float32)
        ok, rvec, tvec = cv2.solvePnP(
            object_points, detection.corners.astype(np.float32), self.camera_matrix,
            self.distortion, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if ok and np.isfinite(tvec).all():
            detection.camera_rvec = rvec.reshape(3)
            detection.camera_tvec = tvec.reshape(3)

    @staticmethod
    def draw(frame: np.ndarray, detections: list[TagDetection], own: TagDetection | None) -> np.ndarray:
        for detection in detections:
            points = detection.corners.astype(int)
            cv2.polylines(frame, [points], True, (70, 210, 120), 2, cv2.LINE_AA)
            cx, cy = detection.center
            cv2.circle(frame, (cx, cy), 5, (40, 90, 255), -1)
            cv2.putText(frame, f"TAG {detection.tag_id}", (cx + 9, cy - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (70, 210, 120), 2, cv2.LINE_AA)
        if own is not None:
            cx, cy = own.center
            length = 42
            end = (int(cx + length * math.cos(own.image_heading_rad)),
                   int(cy + length * math.sin(own.image_heading_rad)))
            cv2.arrowedLine(frame, (cx, cy), end, (255, 190, 40), 2, cv2.LINE_AA, tipLength=0.25)
        return frame
