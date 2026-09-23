"""Compact arena calibration and opponent-tracking status/controls."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout

from control_center.models.state import VisionState, WorldState
from control_center.widgets.common import Panel, set_status


class VisionArenaPanel(Panel):
    recalibrate_requested = Signal()
    background_requested = Signal()
    auto_acquire_requested = Signal()
    select_opponent_requested = Signal()
    clear_track_requested = Signal()
    debug_requested = Signal()

    def __init__(self) -> None:
        super().__init__("VISION / ARENA TRACKING")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        layout.addWidget(self.title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        self.values: dict[str, QLabel] = {}
        rows = [
            ("camera", "Camera", "OPENING"), ("fps", "Capture / vision", "--"),
            ("resolution", "Resolution / age", "--"), ("calibration", "Homography", "INVALID"),
            ("background", "Background", "NOT LOADED"), ("landmarks", "Landmarks", "NOT RUN"),
            ("self", "Self AprilTag", "LOST"), ("self_pose", "Self X / Y / heading", "--"),
            ("opponent", "Opponent", "NONE"), ("confidence", "Confidence", "--"),
            ("opponent_pose", "Opponent X / Y", "--"), ("velocity", "Opponent vx / vy", "--"),
            ("age", "Last detection age", "--"),
        ]
        for row, (key, text, initial) in enumerate(rows):
            grid.addWidget(QLabel(text), row, 0)
            value = QLabel(initial)
            value.setWordWrap(False)
            grid.addWidget(value, row, 1)
            self.values[key] = value
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        buttons = QGridLayout()
        self.recalibrate = QPushButton("RECALIBRATE ARENA")
        self.background = QPushButton("CAPTURE BACKGROUND")
        self.auto_acquire = QPushButton("AUTO ACQUIRE OPPONENT")
        self.select = QPushButton("SELECT OPPONENT")
        self.clear = QPushButton("CLEAR TRACK")
        self.debug = QPushButton("DEBUG VIEW")
        for button in (self.recalibrate, self.background, self.auto_acquire,
                       self.select, self.clear, self.debug):
            button.setMinimumHeight(34)
        buttons.addWidget(self.recalibrate, 0, 0)
        buttons.addWidget(self.background, 0, 1)
        buttons.addWidget(self.auto_acquire, 1, 0, 1, 2)
        buttons.addWidget(self.select, 2, 0)
        buttons.addWidget(self.clear, 2, 1)
        buttons.addWidget(self.debug, 3, 0, 1, 2)
        layout.addLayout(buttons)
        self.recalibrate.clicked.connect(self.recalibrate_requested)
        self.background.clicked.connect(self.background_requested)
        self.auto_acquire.clicked.connect(self.auto_acquire_requested)
        self.select.clicked.connect(self.select_opponent_requested)
        self.clear.clicked.connect(self.clear_track_requested)
        self.debug.clicked.connect(self.debug_requested)

    def update_state(self, state: WorldState) -> None:
        vision = state.vision
        set_status(self.values["camera"], vision.camera_state)
        self.values["fps"].setText(f"{vision.capture_fps:.1f} / {vision.vision_fps:.1f} FPS")
        resolution = f"{vision.resolution[0]}×{vision.resolution[1]}" if vision.resolution else "--"
        self.values["resolution"].setText(f"{resolution} / {vision.frame_age_ms:.0f} ms")
        set_status(self.values["calibration"], "VALID" if vision.homography_valid else "INVALID")
        if vision.calibration_error is not None:
            self.values["calibration"].setText(f"VALID · {vision.calibration_error:.2f}px")
        background = "LOADED" if vision.background_loaded else "NOT LOADED"
        if vision.background_progress:
            background = f"CAPTURING {vision.background_progress[0]}/{vision.background_progress[1]}"
        set_status(self.values["background"], background)
        self.values["landmarks"].setText(vision.landmark_status)
        set_status(self.values["self"], "TRACKED" if vision.self_detected else "LOST")
        self.values["self_pose"].setText(self._pose_text(vision))
        opponent = vision.opponent
        set_status(self.values["opponent"], opponent.tracking_state.value)
        self.values["confidence"].setText(f"{opponent.confidence:.0%}" if opponent.tracking_state.value != "NONE" else "--")
        self.values["opponent_pose"].setText(
            f"{opponent.arena_x:.3f} / {opponent.arena_y:.3f} m"
            if opponent.arena_x is not None and opponent.arena_y is not None else "--")
        self.values["velocity"].setText(
            f"{opponent.vx:.2f} / {opponent.vy:.2f} m/s"
            if opponent.vx is not None and opponent.vy is not None else "--")
        self.values["age"].setText(
            f"{opponent.last_detection_age * 1000:.0f} ms · {opponent.acquisition_source.value}"
            if opponent.last_detection_age is not None else "--")
        self.background.setEnabled(vision.homography_valid)

    @staticmethod
    def _pose_text(vision: VisionState) -> str:
        pose = vision.self_pose
        if not pose.valid or pose.x is None or pose.y is None:
            return "--"
        heading = f"{pose.theta:.2f} rad" if pose.theta is not None else "--"
        return f"{pose.x:.3f} / {pose.y:.3f} m / {heading}"
