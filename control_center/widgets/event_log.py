"""Bounded, timestamped operator event log."""

from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout

from control_center.widgets.common import Panel


class EventLog(Panel):
    def __init__(self) -> None:
        super().__init__("EVENT LOG")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        layout.addWidget(self.title)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(500)
        layout.addWidget(self.text)

    def add_event(self, message: str) -> None:
        self.text.appendPlainText(f"[{datetime.now():%H:%M:%S}] {message}")
