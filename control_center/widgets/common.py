"""Shared widget helpers."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


STATUS_COLORS = {
    "OK": "#55c889", "CONNECTED": "#55c889", "LIVE": "#55c889",
    "VALID": "#55c889", "LOADED": "#55c889", "TRACKED": "#55c889",
    "READY": "#55c889", "DEGRADED": "#e8b85b", "PREDICTED": "#e8b85b",
    "DISCONNECTED": "#ef6b73", "UNAVAILABLE": "#7f8996", "FAILSAFE": "#ef6b73",
    "ERROR": "#ef6b73", "LOST": "#ef6b73", "INVALID": "#ef6b73",
    "CONNECTING": "#e8b85b", "OPENING": "#e8b85b", "WIP": "#6fa8dc",
    "LOCAL ONLY": "#6fa8dc", "NO DATA": "#7f8996",
    "TRACKED": "#55c889", "PREDICTED": "#e8b85b", "LOST": "#7f8996",
    "VALID": "#55c889", "INVALID": "#ef6b73",
    "LOADED": "#55c889", "NOT LOADED": "#7f8996",
    "DETECTED": "#55c889", "CALIBRATED": "#55c889",
}


class Panel(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.title = QLabel(title)
        self.title.setObjectName("panelTitle")


def status_row(label: str, value: str = "UNAVAILABLE") -> tuple[QWidget, QLabel]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 1, 0, 1)
    layout.setSpacing(8)
    name = QLabel(label)
    value_label = QLabel(value)
    value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
    name.setMinimumWidth(0)
    value_label.setMinimumWidth(0)
    layout.addWidget(name, 1)
    layout.addWidget(value_label, 1)
    set_status(value_label, value)
    return row, value_label


def set_status(label: QLabel, text: str) -> None:
    label.setText(text)
    color = STATUS_COLORS.get(text, "#c7cdd4")
    label.setStyleSheet(f"color: {color}; font-weight: 700;")
