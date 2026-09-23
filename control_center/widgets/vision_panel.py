"""Vision / arena tracking status and control panel."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QPushButton,
                               QSizePolicy, QVBoxLayout)

from control_center.backend.command_manager import CommandManager
from control_center.models.state import WorldState
from control_center.widgets.common import Panel, set_status, status_row


class VisionPanel(Panel):
    def __init__(self, commands: CommandManager) -> None:
        super().__init__("VISION / ARENA")
        self.commands = commands
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(self.title)

        self.values = {}
        for key, label, value in [
            ("camera",     "Camera",           "UNAVAILABLE"),
            ("calibrated", "Arena calibrated", "NO"),
            ("homography", "Homography",       "INVALID"),
            ("background", "Background",       "NOT LOADED"),
            ("self",       "Own robot",        "LOST"),
            ("opponent",   "Opponent",         "LOST"),
            ("confidence", "Confidence",       "--"),
            ("calib_err",  "Calib error",      "--"),
        ]:
            row, widget = status_row(label, value)
            self.values[key] = widget
            layout.addWidget(row)

        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(5)
        btn_grid.setVerticalSpacing(5)

        self.recal = QPushButton("RECALIBRATE ARENA")
        self.capture_bg = QPushButton("CAPTURE BACKGROUND")
        self.auto_acq = QPushButton("AUTO ACQUIRE")
        self.select_opp = QPushButton("SELECT OPPONENT")
        self.clear = QPushButton("CLEAR TRACK")
        self.clear.setObjectName("warningButton")

        for btn in (self.recal, self.capture_bg, self.auto_acq, self.select_opp, self.clear):
            btn.setMinimumHeight(30)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        btn_grid.addWidget(self.recal,      0, 0, 1, 2)
        btn_grid.addWidget(self.capture_bg, 1, 0, 1, 2)
        btn_grid.addWidget(self.auto_acq,   2, 0)
        btn_grid.addWidget(self.select_opp, 2, 1)
        btn_grid.addWidget(self.clear,      3, 0, 1, 2)

        layout.addLayout(btn_grid)

        self.recal.clicked.connect(commands.request_recalibrate_arena)
        self.capture_bg.clicked.connect(commands.request_capture_background)
        self.auto_acq.clicked.connect(commands.request_auto_acquire_opponent)
        self.select_opp.clicked.connect(commands.request_select_opponent)
        self.clear.clicked.connect(commands.request_clear_track)

    def update_state(self, state: WorldState) -> None:
        v = state.vision
        cal = state.calibration

        cam_status = state.health.camera.value
        set_status(self.values["camera"], cam_status)

        set_status(self.values["calibrated"], "CALIBRATED" if cal.valid else "NOT CALIBRATED")
        set_status(self.values["homography"], "VALID" if v.homography_valid else "INVALID")
        set_status(self.values["background"], "LOADED" if v.background_loaded else "NOT LOADED")
        set_status(self.values["self"], "DETECTED" if v.self_detected else "LOST")

        opp_state = v.opponent_tracking_state.value
        set_status(self.values["opponent"], opp_state)

        if v.opponent_detected or v.opponent_tracking_state.value in ("TRACKED", "PREDICTED"):
            conf_text = f"{v.opponent_confidence:.0%}" if v.opponent_confidence > 0 else "--"
        else:
            conf_text = "--"
        self.values["confidence"].setText(conf_text)

        if v.calibration_error is not None:
            self.values["calib_err"].setText(f"{v.calibration_error * 1000:.1f} mm")
        else:
            self.values["calib_err"].setText("--")
