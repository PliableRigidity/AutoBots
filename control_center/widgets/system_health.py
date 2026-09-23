"""Subsystem health summary."""

from PySide6.QtWidgets import QVBoxLayout

from control_center.models.state import WorldState
from control_center.widgets.common import Panel, set_status, status_row


class SystemHealthPanel(Panel):
    def __init__(self) -> None:
        super().__init__("SYSTEM HEALTH")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(3)
        layout.addWidget(self.title)
        self.values = {}
        for key, label in [("camera", "Camera"), ("vision", "Vision"),
                           ("localization", "Localization"), ("estimator", "State estimator"),
                           ("espnow", "ESP-NOW"), ("elrs", "ELRS"),
                           ("logging", "Logging"), ("control", "Control loop")]:
            row, widget = status_row(label)
            self.values[key] = widget
            layout.addWidget(row)

    def update_state(self, state: WorldState) -> None:
        health = state.health
        for key, widget in self.values.items():
            set_status(widget, getattr(health, key).value)
