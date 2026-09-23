"""Live OpenCV frame display."""

import time

import cv2
from PySide6.QtCore import QPoint, QRect, Signal, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from control_center.models.state import VisionState
from control_center.widgets.common import Panel, set_status


class InteractiveImageLabel(QLabel):
    calibration_complete = Signal(object)
    roi_complete = Signal(object)

    def __init__(self) -> None:
        super().__init__("CAMERA INITIALISING")
        self.mode: str | None = None
        self.required_points = 4
        self.points: list[tuple[float, float]] = []
        self._drag_start: QPoint | None = None
        self._drag_end: QPoint | None = None
        self.setMouseTracking(True)

    def begin_calibration(self, count: int) -> None:
        self.mode = "calibration"
        self.required_points = max(4, count)
        self.points = []
        self.update()

    def begin_roi(self) -> None:
        self.mode = "roi"
        self._drag_start = None
        self._drag_end = None
        self.update()

    def cancel_interaction(self) -> None:
        self.mode = None
        self.points = []
        self._drag_start = self._drag_end = None
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self.mode is None:
            return super().mousePressEvent(event)
        if self.mode == "calibration":
            point = self._widget_to_image(event.position().toPoint())
            if point is not None:
                self.points.append(point)
                if len(self.points) >= self.required_points:
                    points = list(self.points)
                    self.cancel_interaction()
                    self.calibration_complete.emit(points)
            self.update()
        elif self.mode == "roi":
            self._drag_start = event.position().toPoint()
            self._drag_end = self._drag_start

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.mode == "roi" and self._drag_start is not None:
            self._drag_end = event.position().toPoint()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.mode != "roi" or self._drag_start is None:
            return super().mouseReleaseEvent(event)
        self._drag_end = event.position().toPoint()
        start = self._widget_to_image(self._drag_start)
        end = self._widget_to_image(self._drag_end)
        if start and end:
            x0, x1 = sorted((int(start[0]), int(end[0])))
            y0, y1 = sorted((int(start[1]), int(end[1])))
            if x1 - x0 >= 5 and y1 - y0 >= 5:
                self.roi_complete.emit((x0, y0, x1 - x0, y1 - y0))
        self.cancel_interaction()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#f0bf55"), 2))
        if self.mode == "calibration":
            for index, point in enumerate(self.points):
                widget_point = self._image_to_widget(point)
                if widget_point:
                    painter.drawEllipse(widget_point, 6, 6)
                    painter.drawText(widget_point + QPoint(8, -8), str(index + 1))
            painter.drawText(15, 25, f"CALIBRATION: click point {len(self.points)+1}/{self.required_points}")
        elif self.mode == "roi":
            painter.drawText(15, 25, "SELECT OPPONENT: drag a rectangle")
            if self._drag_start and self._drag_end:
                painter.drawRect(QRect(self._drag_start, self._drag_end).normalized())

    def _pixmap_rect(self) -> QRect | None:
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return None
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        return QRect(x, y, pixmap.width(), pixmap.height())

    def _widget_to_image(self, point: QPoint) -> tuple[float, float] | None:
        rect = self._pixmap_rect()
        if rect is None or not rect.contains(point) or not hasattr(self, "image_size"):
            return None
        width, height = self.image_size
        return ((point.x() - rect.x()) / rect.width() * width,
                (point.y() - rect.y()) / rect.height() * height)

    def _image_to_widget(self, point: tuple[float, float]) -> QPoint | None:
        rect = self._pixmap_rect()
        if rect is None or not hasattr(self, "image_size"):
            return None
        width, height = self.image_size
        return QPoint(int(rect.x() + point[0] / width * rect.width()),
                      int(rect.y() + point[1] / height * rect.height()))


class CameraView(Panel):
    calibration_complete = Signal(object)
    roi_complete = Signal(object)

    def __init__(self) -> None:
        super().__init__("LIVE CAMERA")
        self.image = InteractiveImageLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(560, 340)
        self.image.setStyleSheet("background: #080b0f; color: #7f8996;")
        self.camera_status = QLabel("CONNECTING")
        self.self_status = QLabel("SELF: LOST")
        self.vision_status = QLabel("VISION INITIALISING")
        self.opponent_status = QLabel("OPPONENT: WIP")
        self.metrics = QLabel("0.0 FPS  |  --")
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.camera_status)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.image, 1)
        footer = QHBoxLayout()
        footer.addWidget(self.self_status)
        footer.addSpacing(18)
        footer.addWidget(self.vision_status)
        footer.addSpacing(18)
        footer.addWidget(self.opponent_status)
        footer.addStretch()
        footer.addWidget(self.metrics)
        layout.addLayout(footer)
        self._last_pixmap: QPixmap | None = None
        self._capture_fps = 0.0
        self._vision_fps = 0.0
        self._gui_fps = 0.0
        self._last_gui_frame = 0.0
        self._conversion_ms = 0.0
        self._resolution = "--"
        self.image.calibration_complete.connect(self.calibration_complete)
        self.image.roi_complete.connect(self.roi_complete)

    def set_frame(self, frame) -> None:
        started = time.perf_counter()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        self.image.image_size = (width, height)
        image = QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888)
        self._last_pixmap = QPixmap.fromImage(image)
        self._rescale()
        finished = time.perf_counter()
        now = finished
        if self._last_gui_frame:
            instant_fps = 1.0 / max(now - self._last_gui_frame, 1e-6)
            self._gui_fps = instant_fps if not self._gui_fps else 0.9 * self._gui_fps + 0.1 * instant_fps
        self._last_gui_frame = now
        sample_ms = (finished - started) * 1000.0
        self._conversion_ms = sample_ms if not self._conversion_ms else 0.9 * self._conversion_ms + 0.1 * sample_ms
        self._update_metrics()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._last_pixmap:
            self.image.setPixmap(self._last_pixmap.scaled(
                self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def set_camera_status(self, ok: bool, message: str) -> None:
        set_status(self.camera_status, "CONNECTED" if ok else "ERROR")
        if not ok:
            self.image.clear()
            self.image.setText("CAMERA ERROR\n" + message)

    def set_connecting(self, message: str) -> None:
        set_status(self.camera_status, "CONNECTING")
        self.image.setText("CAMERA INITIALISING\n" + message)

    def begin_calibration(self, count: int) -> None:
        self.image.begin_calibration(count)

    def begin_opponent_selection(self) -> None:
        self.image.begin_roi()

    def update_vision(self, state: VisionState) -> None:
        set_status(self.self_status, "SELF: DETECTED" if state.self_detected else "SELF: LOST")
        set_status(self.vision_status, "VISION LIVE" if state.detector_available else "VISION INITIALISING")
        self._capture_fps = state.capture_fps
        self._vision_fps = state.vision_fps
        self._resolution = f"{state.resolution[0]}×{state.resolution[1]}" if state.resolution else "--"
        self.metrics.setToolTip(
            f"Capture read: {state.capture_read_ms:.1f} ms\n"
            f"AprilTag: {state.detection_ms:.1f} ms\n"
            f"Overlay: {state.overlay_ms:.2f} ms\n"
            f"BGR→QPixmap/UI: {self._conversion_ms:.1f} ms\n"
            f"Detection age: {state.detection_age_ms:.1f} ms")
        self._update_metrics()

    def _update_metrics(self) -> None:
        self.metrics.setText(
            f"CAM {self._capture_fps:.1f}  |  VISION {self._vision_fps:.1f}  |  "
            f"GUI {self._gui_fps:.1f} FPS  |  {self._resolution}")
