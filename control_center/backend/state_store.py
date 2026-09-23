"""Single source of truth for application state."""

from PySide6.QtCore import QObject, Signal

from control_center.models.state import RobotPose, Status, TrackingState, VisionState, WorldState


class StateStore(QObject):
    state_changed = Signal(object)
    vision_changed = Signal(object)

    def __init__(self, initial: WorldState) -> None:
        super().__init__()
        self._state = initial

    @property
    def state(self) -> WorldState:
        return self._state

    def publish(self) -> None:
        self.state_changed.emit(self._state)

    def update_vision(self, vision: VisionState) -> None:
        self._state.vision = vision
        self._state.opponent = vision.opponent
        self._state.self_pose = vision.self_pose
        self._state.camera_pose = vision.self_pose
        self._state.opponent_pose = RobotPose(
            x=vision.opponent.arena_x, y=vision.opponent.arena_y,
            vx=vision.opponent.vx, vy=vision.opponent.vy,
            valid=vision.opponent.tracking_state in (TrackingState.TRACKED, TrackingState.PREDICTED),
            confidence=vision.opponent.confidence)
        self._state.calibration.valid = vision.homography_valid
        self._state.calibration.background_loaded = vision.background_loaded
        self._state.calibration.calibration_error = vision.calibration_error
        self._state.calibration.calibration_id = vision.calibration_timestamp
        self._state.health.vision = Status.OK if vision.detector_available else Status.UNAVAILABLE
        self._state.health.localization = Status.OK if vision.homography_valid else Status.UNAVAILABLE
        self.vision_changed.emit(vision)
        self.publish()
