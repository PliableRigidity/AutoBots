"""Shared, typed state contract for UI, hardware backends, and future simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Optional


class Status(str, Enum):
    OK = "OK"
    READY = "READY"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILSAFE = "FAILSAFE"
    WIP = "WIP"
    LOCAL_ONLY = "LOCAL ONLY"
    NO_DATA = "NO DATA"


class ControlMode(str, Enum):
    NONE = "NONE"
    MANUAL = "MANUAL"
    AUTO = "AUTO"


class TrackingState(str, Enum):
    NONE = "NONE"
    TRACKED = "TRACKED"
    PREDICTED = "PREDICTED"
    LOST = "LOST"


class AcquisitionSource(str, Enum):
    NONE = "NONE"
    AUTO = "AUTO"
    MANUAL = "MANUAL"


@dataclass(slots=True)
class RobotPose:
    x: Optional[float] = None
    y: Optional[float] = None
    theta: Optional[float] = None
    vx: Optional[float] = None
    vy: Optional[float] = None
    omega: Optional[float] = None
    valid: bool = False
    confidence: float = 0.0


@dataclass(slots=True)
class OpponentState:
    tracking_state: TrackingState = TrackingState.NONE
    detected: bool = False
    confidence: float = 0.0
    bbox: Optional[tuple[int, int, int, int]] = None
    image_x: Optional[float] = None
    image_y: Optional[float] = None
    floor_point: Optional[tuple[float, float]] = None
    arena_x: Optional[float] = None
    arena_y: Optional[float] = None
    vx: Optional[float] = None
    vy: Optional[float] = None
    timestamp: float = 0.0
    last_detection_age: Optional[float] = None
    acquisition_source: AcquisitionSource = AcquisitionSource.NONE


@dataclass(slots=True)
class VisionState:
    # Camera capture metrics
    fps: float = 0.0  # Backward-compatible alias for capture_fps.
    capture_fps: float = 0.0
    vision_fps: float = 0.0
    capture_read_ms: float = 0.0
    detection_ms: float = 0.0
    overlay_ms: float = 0.0
    frame_timestamp: float = 0.0
    detection_timestamp: float = 0.0
    detection_age_ms: float = 0.0
    resolution: Optional[tuple[int, int]] = None
    detector_available: bool = False
    # Arena calibration status
    arena_calibrated: bool = False
    homography_valid: bool = False
    background_loaded: bool = False
    calibration_error: Optional[float] = None
    # Own-robot detection (AprilTag)
    self_detected: bool = False
    tag_id: Optional[int] = None
    image_center: Optional[tuple[int, int]] = None
    image_heading_rad: Optional[float] = None
    # Opponent tracking
    opponent_detected: bool = False
    opponent_tracking_state: TrackingState = TrackingState.LOST
    opponent_confidence: float = 0.0
    opponent_auto_acquired: bool = False
    camera_state: str = "OPENING"
    frame_age_ms: float = 0.0
    calibration_timestamp: Optional[str] = None
    landmark_status: str = "NOT RUN"
    background_progress: Optional[tuple[int, int]] = None
    opponent: OpponentState = field(default_factory=OpponentState)
    self_pose: RobotPose = field(default_factory=RobotPose)
    self_camera_xyz: Optional[tuple[float, float, float]] = None


@dataclass(slots=True)
class RobotTelemetry:
    battery_voltage: Optional[float] = None
    imu_status: Status = Status.DISCONNECTED
    espnow_status: Status = Status.DISCONNECTED
    elrs_status: Status = Status.UNAVAILABLE
    robot_link_status: Status = Status.DISCONNECTED
    firmware: Optional[str] = None
    control_loop_hz: Optional[float] = None
    rssi_dbm: Optional[float] = None
    link_quality: Optional[float] = None
    reported_robot_mode: Optional[str] = None
    failsafe: Optional[bool] = None


# --- Optional / Legacy: Ultrasonic TDOA ---
# Not part of the primary localization pipeline.
# Retained for potential future redundant localization use only.

@dataclass(slots=True)
class TdoaChannel:
    status: Status = Status.NO_DATA
    arrival_timestamp_us: Optional[float] = None
    relative_delay_us: Optional[float] = None
    signal_quality: Optional[float] = None


@dataclass(slots=True)
class TdoaState:
    available: bool = False
    channels: list[TdoaChannel] = field(default_factory=lambda: [TdoaChannel() for _ in range(4)])
    update_rate_hz: Optional[float] = None
    solver_residual: Optional[float] = None
    x: Optional[float] = None
    y: Optional[float] = None
    confidence: Optional[float] = None
    rejected_channels: list[int] = field(default_factory=list)
    valid: bool = False

# --- End Optional / Legacy ---


@dataclass(slots=True)
class ArenaCalibration:
    width_m: float = 1.15
    height_m: float = 1.15
    homography: Optional[list[list[float]]] = None
    valid: bool = False
    background_loaded: bool = False
    homography_timestamp: float = 0.0
    calibration_error: Optional[float] = None
    calibration_id: Optional[str] = None
    hazards: list[list[tuple[float, float]]] = field(default_factory=list)


@dataclass(slots=True)
class ControlState:
    requested_arm: bool = False
    requested_mode: ControlMode = ControlMode.NONE
    software_stop: bool = False
    max_speed_percent: int = 50
    robot_acknowledgement: Status = Status.UNAVAILABLE


@dataclass(slots=True)
class HealthState:
    camera: Status = Status.UNAVAILABLE
    vision: Status = Status.UNAVAILABLE
    localization: Status = Status.UNAVAILABLE
    estimator: Status = Status.WIP
    espnow: Status = Status.DISCONNECTED
    elrs: Status = Status.UNAVAILABLE
    logging: Status = Status.READY
    control: Status = Status.LOCAL_ONLY


@dataclass(slots=True)
class LinkState:
    connected: bool = False
    detail: str = "No robot transport configured"


@dataclass(slots=True)
class WorldState:
    timestamp: float = field(default_factory=monotonic)
    self_pose: RobotPose = field(default_factory=RobotPose)
    opponent_pose: RobotPose = field(default_factory=RobotPose)
    fused_pose: RobotPose = field(default_factory=RobotPose)
    camera_pose: RobotPose = field(default_factory=RobotPose)
    vision: VisionState = field(default_factory=VisionState)
    telemetry: RobotTelemetry = field(default_factory=RobotTelemetry)
    calibration: ArenaCalibration = field(default_factory=ArenaCalibration)
    opponent: OpponentState = field(default_factory=OpponentState)
    control: ControlState = field(default_factory=ControlState)
    health: HealthState = field(default_factory=HealthState)
    source: str = "real"
