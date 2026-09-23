"""Main native Qt window and application composition root."""

from __future__ import annotations

import logging
import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QScrollArea,
                               QSplitter, QVBoxLayout, QWidget)

from control_center.backend.camera_worker import (CameraWorker, DetectionBuffer,
                                                  LatestDisplayFrame, LatestFrameBuffer,
                                                  VisionWorker)
from control_center.backend.command_manager import CommandManager
from control_center.backend.state_store import StateStore
from control_center.models.state import RobotPose, Status, WorldState
from control_center.widgets.camera_view import CameraView
from control_center.widgets.control_panel import ControlPanel
from control_center.widgets.event_log import EventLog
from control_center.widgets.minimap import Minimap
from control_center.widgets.robot_status import RobotStatusPanel
from control_center.widgets.system_health import SystemHealthPanel
from control_center.widgets.vision_arena_panel import VisionArenaPanel


class MainWindow(QMainWindow):
    def __init__(self, config: dict, demo: bool = False) -> None:
        super().__init__()
        self.log = logging.getLogger(__name__)
        self.config = config
        self.demo = demo
        state = WorldState(source="demo" if demo else "real")
        arena_config = config.get("arena", {})
        state.calibration.width_m = float(arena_config.get("width_m", config.get("arena_width_m", 1.15)))
        state.calibration.height_m = float(arena_config.get("height_m", config.get("arena_height_m", 1.15)))
        state.calibration.hazards = self._configured_hazards(arena_config)
        self.store = StateStore(state)
        self.commands = CommandManager(self.store)
        self.frame_buffer = LatestFrameBuffer()
        self.detection_buffer = DetectionBuffer()
        self.display_buffer = LatestDisplayFrame()
        self.vision_worker = VisionWorker(config, self.frame_buffer, self.detection_buffer, self)
        self.camera_worker = CameraWorker(
            config, self.frame_buffer, self.detection_buffer, self.display_buffer, self)
        self._display_sequence = 0
        self._last_detected = False
        self._last_opponent_state = "NONE"
        self._camera_was_open: bool | None = None
        self._build_ui()
        self._connect_signals()
        self.resize(1600, 950)
        self.setMinimumSize(1200, 720)
        self.setWindowTitle("AutoBot Control Center")
        self.event_log.add_event("Control Center started")
        if demo:
            self.event_log.add_event("DEMO MODE enabled — displayed telemetry is simulated")
            self._start_demo()
        self.store.publish()
        self.vision_worker.start()
        self.camera_worker.start()
        self.display_timer = QTimer(self)
        refresh_hz = max(1, int(config.get("ui_refresh_hz", 30)))
        self.display_timer.timeout.connect(self._display_latest_frame)
        self.display_timer.setTimerType(Qt.TimerType.PreciseTimer)
        # Poll at twice the target display rate. Conversion only happens when the
        # sequence changes, avoiding phase misses between two independent 30 Hz loops.
        self.display_timer.start(max(1, round(1000 / (refresh_hz * 2))))

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)
        banner = QHBoxLayout()
        title = QLabel("AUTOBOT CONTROL CENTER")
        title.setObjectName("appTitle")
        banner.addWidget(title)
        banner.addStretch()
        self.mode_badge = QLabel("DEMO MODE" if self.demo else "LIVE / LOCAL")
        self.mode_badge.setObjectName("demoBadge" if self.demo else "modeBadge")
        banner.addWidget(self.mode_badge)
        root.addLayout(banner)

        self.camera = CameraView()
        self.minimap = Minimap()
        self.robot_status = RobotStatusPanel()
        self.controls = ControlPanel(self.commands)
        self.health = SystemHealthPanel()
        self.vision_panel = VisionArenaPanel()
        self.event_log = EventLog()

        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(self.camera)
        left.addWidget(self.vision_panel)
        left.setStretchFactor(0, 4)
        left.setStretchFactor(1, 1)
        sidebar_content = QWidget()
        sidebar_content.setObjectName("sidebarContent")
        sidebar_layout = QVBoxLayout(sidebar_content)
        sidebar_layout.setContentsMargins(5, 0, 5, 0)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(self.minimap)
        sidebar_layout.addWidget(self.robot_status)
        sidebar_layout.addWidget(self.controls)
        sidebar_layout.addWidget(self.health)
        sidebar_layout.addStretch(1)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName("sidebarScroll")
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sidebar_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.sidebar_scroll.setMinimumWidth(390)
        self.sidebar_scroll.setWidget(sidebar_content)
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.addWidget(left)
        self.body_splitter.addWidget(self.sidebar_scroll)
        self.body_splitter.setStretchFactor(0, 3)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setSizes([1150, 420])
        root.addWidget(self.body_splitter, 4)
        root.addWidget(self.event_log, 1)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.camera_worker.vision_ready.connect(self._on_vision)
        self.camera_worker.camera_status.connect(self._on_camera_status)
        self.camera_worker.camera_connecting.connect(self.camera.set_connecting)
        self.camera_worker.worker_error.connect(self._on_worker_error)
        self.vision_worker.worker_error.connect(self._on_worker_error)
        self.vision_worker.event.connect(self.event_log.add_event)
        self.vision_worker.calibration_result.connect(self._on_calibration_result)
        self.commands.event.connect(self.event_log.add_event)
        self.store.state_changed.connect(self.robot_status.update_state)
        self.store.state_changed.connect(self.controls.update_state)
        self.store.state_changed.connect(self.health.update_state)
        self.store.state_changed.connect(self.vision_panel.update_state)
        self.store.state_changed.connect(self.minimap.update_state)
        self.store.vision_changed.connect(self.camera.update_vision)
        self.vision_panel.recalibrate_requested.connect(self._begin_calibration)
        self.vision_panel.background_requested.connect(self.vision_worker.request_background_capture)
        self.vision_panel.auto_acquire_requested.connect(self.vision_worker.request_auto_acquire)
        self.vision_panel.select_opponent_requested.connect(self._begin_opponent_selection)
        self.vision_panel.clear_track_requested.connect(self.vision_worker.request_clear_track)
        self.vision_panel.debug_requested.connect(self.vision_worker.request_debug_cycle)
        self.camera.calibration_complete.connect(self.vision_worker.request_calibration)
        self.camera.roi_complete.connect(self.vision_worker.request_manual_roi)
        QTimer.singleShot(10000, self._camera_startup_watchdog)

    def _on_camera_status(self, ok: bool, message: str) -> None:
        self.store.state.health.camera = Status.OK if ok else Status.UNAVAILABLE
        self.camera.set_camera_status(ok, message)
        if ok != self._camera_was_open:
            self.event_log.add_event(message)
            self.log.info(message)
        self._camera_was_open = ok
        self.store.publish()

    def _on_vision(self, vision) -> None:
        if vision.self_detected != self._last_detected:
            message = (f"AprilTag {vision.tag_id} detected" if vision.self_detected
                       else "AprilTag lost")
            self.event_log.add_event(message)
            self.log.info(message)
        self._last_detected = vision.self_detected
        opponent_state = vision.opponent.tracking_state.value
        if opponent_state != self._last_opponent_state:
            message = f"Opponent tracking: {self._last_opponent_state} → {opponent_state}"
            self.event_log.add_event(message)
            self.log.info(message)
            self._last_opponent_state = opponent_state
        self.store.update_vision(vision)

    def _on_worker_error(self, message: str) -> None:
        self.event_log.add_event(message)
        self.log.error(message)

    def _camera_startup_watchdog(self) -> None:
        if self._camera_was_open is None:
            message = "Camera startup exceeded 10 seconds; check device availability or backend logs"
            self.camera.set_camera_status(False, message)
            self.store.state.health.camera = Status.UNAVAILABLE
            self.event_log.add_event(message)
            self.log.error(message)
            self.store.publish()

    def _display_latest_frame(self) -> None:
        sequence, frame = self.display_buffer.snapshot(self._display_sequence)
        if frame is not None:
            self._display_sequence = sequence
            self.camera.set_frame(frame)

    def _begin_calibration(self) -> None:
        references = self.config.get("arena", {}).get("calibration_reference_points_m", [])
        if len(references) < 4:
            self._on_worker_error("Calibration reference points are not configured")
            return
        self.camera.begin_calibration(len(references))
        message = ("Arena calibration started: click reference points in configured order "
                   "(near-left, near-right, far-right, far-left)")
        self.event_log.add_event(message)
        self.log.info(message)

    def _begin_opponent_selection(self) -> None:
        if not self.store.state.calibration.valid:
            self._on_worker_error("Calibrate the arena before selecting an opponent")
            return
        self.camera.begin_opponent_selection()
        self.event_log.add_event("Manual opponent selection: drag a rectangle around the target")

    def _on_calibration_result(self, ok: bool, message: str) -> None:
        if not ok:
            self._on_worker_error(message)

    @staticmethod
    def _configured_hazards(arena_config: dict) -> list[list[tuple[float, float]]]:
        hazards: list[list[tuple[float, float]]] = []
        for pit_name in ("pit_1", "pit_2"):
            pit = arena_config.get(pit_name, {})
            if all(pit.get(key) is not None for key in ("x", "y", "radius")):
                hazards.append([
                    (float(pit["x"]) + float(pit["radius"]) * math.cos(i * math.pi / 12),
                     float(pit["y"]) + float(pit["radius"]) * math.sin(i * math.pi / 12))
                    for i in range(24)])
        vertices = arena_config.get("flipper", {}).get("vertices", [])
        if vertices:
            hazards.append([(float(x), float(y)) for x, y in vertices])
        return hazards

    def _start_demo(self) -> None:
        state = self.store.state
        state.telemetry.battery_voltage = 6.2
        state.telemetry.imu_status = Status.OK
        state.telemetry.espnow_status = Status.OK
        state.telemetry.robot_link_status = Status.OK
        state.telemetry.firmware = "DEMO"
        state.telemetry.control_loop_hz = 200.0
        state.telemetry.rssi_dbm = -48.0
        state.telemetry.link_quality = 99.0
        state.health.estimator = Status.OK
        state.health.espnow = Status.OK
        state.health.control = Status.OK
        self._demo_phase = 0.0
        self.demo_timer = QTimer(self)
        self.demo_timer.timeout.connect(self._update_demo)
        self.demo_timer.start(100)

    def _update_demo(self) -> None:
        self._demo_phase += 0.04
        state = self.store.state
        pose = RobotPose(x=0.575 + 0.32 * math.cos(self._demo_phase),
                         y=0.575 + 0.32 * math.sin(self._demo_phase),
                         theta=self._demo_phase + math.pi / 2, valid=True, confidence=0.92)
        state.camera_pose = pose
        state.fused_pose = pose
        self.store.publish()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.log.info("Control Center stopping")
        self.event_log.add_event("Control Center stopping")
        self.display_timer.stop()
        self.camera_worker.stop()
        if not self.camera_worker.wait(3000):
            self.log.error("Camera worker did not stop within 3 seconds")
        self.vision_worker.stop()
        if not self.vision_worker.wait(3000):
            self.log.error("Vision worker did not stop within 3 seconds")
        event.accept()
