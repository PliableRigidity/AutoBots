"""Top-down arena drawing that never invents image-to-world coordinates."""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from control_center.models.state import RobotPose, WorldState
from control_center.widgets.common import Panel


class Minimap(Panel):
    def __init__(self) -> None:
        super().__init__("ARENA MINIMAP")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(5)
        layout.addWidget(self.title)
        center = QHBoxLayout()
        center.addStretch(1)
        self.canvas = ArenaCanvas()
        center.addWidget(self.canvas)
        center.addStretch(1)
        layout.addLayout(center)

    def update_state(self, state: WorldState) -> None:
        self.canvas.update_state(state)


class ArenaCanvas(QWidget):
    """A compact square arena canvas that cannot widen the sidebar."""

    def __init__(self) -> None:
        super().__init__()
        # A fixed logical square is intentional here: Qt layouts otherwise shrink
        # one axis independently inside a scrolled sidebar. Logical pixels still
        # follow the platform DPI scale, and 230 stays within the 180–260 target.
        self.setFixedSize(230, 230)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._state: WorldState | None = None

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(230, 230)

    def update_state(self, state: WorldState) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = 8
        side = max(1, min(self.width(), self.height()) - 2 * margin)
        arena = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        painter.setPen(QPen(QColor("#66717f"), 2))
        painter.setBrush(QColor("#10161d"))
        painter.drawRect(arena)

        state = self._state
        if state:
            # Hazard polygons (pits, flipper region)
            if state.calibration.hazards:
                painter.setPen(QPen(QColor("#8b3a3a"), 1))
                painter.setBrush(QColor(80, 20, 20, 100))
                for polygon in state.calibration.hazards:
                    if len(polygon) >= 2:
                        pts = [self._map(x, y, arena, state) for x, y in polygon]
                        for i in range(len(pts)):
                            painter.drawLine(pts[i], pts[(i + 1) % len(pts)])

            # Own robot: show vision pose with heading arrow (blue △)
            self._draw_pose_with_heading(painter, arena, state.camera_pose, state,
                                         QColor("#6fa8dc"), "SELF △")
            # Fused estimate (green ×) if different from camera pose
            self._draw_pose(painter, arena, state.fused_pose, state,
                            QColor("#55c889"), "FUSED ×")
            # Opponent (orange ○) with optional velocity arrow
            self._draw_opponent(painter, arena, state.opponent_pose, state)

        painter.setPen(QColor("#e8b85b"))
        if not state or not state.calibration.valid:
            painter.drawText(arena, Qt.AlignmentFlag.AlignCenter, "CALIBRATION REQUIRED")
        else:
            painter.drawText(int(arena.left() + 5), int(arena.top() + 16), "WORLD FRAME ACTIVE")

    @staticmethod
    def _map(x: float, y: float, arena: QRectF, state: WorldState) -> QPointF:
        return QPointF(arena.left() + x / state.calibration.width_m * arena.width(),
                       arena.bottom() - y / state.calibration.height_m * arena.height())

    def _draw_pose(self, painter: QPainter, arena: QRectF, pose: RobotPose,
                   state: WorldState, color: QColor, label: str) -> None:
        if not pose.valid or pose.x is None or pose.y is None:
            return
        point = self._map(pose.x, pose.y, arena, state)
        painter.setPen(QPen(color, 2))
        painter.setBrush(color)
        painter.drawEllipse(point, 5, 5)
        painter.drawText(point + QPointF(7, -7), label)

    def _draw_pose_with_heading(self, painter: QPainter, arena: QRectF, pose: RobotPose,
                                state: WorldState, color: QColor, label: str) -> None:
        if not pose.valid or pose.x is None or pose.y is None:
            return
        point = self._map(pose.x, pose.y, arena, state)
        painter.setPen(QPen(color, 2))
        painter.setBrush(color)
        painter.drawEllipse(point, 5, 5)
        painter.drawText(point + QPointF(7, -7), label)
        # Heading arrow: world +x is screen right, world +y is screen up (arena.bottom - y)
        if pose.theta is not None:
            arrow_len = 16
            sx = arrow_len * math.cos(pose.theta)
            sy = -arrow_len * math.sin(pose.theta)  # flip y: screen y is down
            tip = QPointF(point.x() + sx, point.y() + sy)
            painter.drawLine(point, tip)

    def _draw_opponent(self, painter: QPainter, arena: QRectF, pose: RobotPose,
                       state: WorldState) -> None:
        if not pose.valid or pose.x is None or pose.y is None:
            return
        point = self._map(pose.x, pose.y, arena, state)
        color = QColor("#e8b85b")
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point, 6, 6)
        painter.drawText(point + QPointF(8, -7), "OPP ○")
        # Velocity arrow if available
        if pose.vx is not None and pose.vy is not None:
            speed = math.hypot(pose.vx, pose.vy)
            if speed > 0.05:
                scale = 20.0 / max(speed, 1.0)
                tip = QPointF(point.x() + pose.vx * scale,
                              point.y() - pose.vy * scale)
                painter.drawLine(point, tip)
