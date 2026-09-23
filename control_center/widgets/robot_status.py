"""Robot telemetry/status panel."""

from PySide6.QtWidgets import QVBoxLayout

from control_center.models.state import WorldState
from control_center.widgets.common import Panel, set_status, status_row


class RobotStatusPanel(Panel):
    def __init__(self) -> None:
        super().__init__("ROBOT STATUS")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(3)
        layout.addWidget(self.title)
        self.values = {}
        for key, label, value in [
            ("battery", "Battery", "UNAVAILABLE"), ("imu", "IMU", "DISCONNECTED"),
            ("espnow", "ESP-NOW", "DISCONNECTED"), ("elrs", "ELRS", "UNAVAILABLE"),
            ("robot", "Robot link", "DISCONNECTED"), ("firmware", "Firmware", "UNAVAILABLE"),
            ("loop", "Control loop", "UNAVAILABLE"), ("rssi", "RSSI / Link quality", "UNAVAILABLE"),
            ("command", "Command source", "NONE"), ("ack", "Robot acknowledgement", "UNAVAILABLE")]:
            row, widget = status_row(label, value)
            self.values[key] = widget
            layout.addWidget(row)

    def update_state(self, state: WorldState) -> None:
        t = state.telemetry
        set_status(self.values["battery"], f"{t.battery_voltage:.2f} V" if t.battery_voltage is not None else "UNAVAILABLE")
        set_status(self.values["imu"], t.imu_status.value)
        set_status(self.values["espnow"], t.espnow_status.value)
        set_status(self.values["elrs"], t.elrs_status.value)
        set_status(self.values["robot"], t.robot_link_status.value)
        set_status(self.values["firmware"], t.firmware or "UNAVAILABLE")
        set_status(self.values["loop"], f"{t.control_loop_hz:.1f} Hz" if t.control_loop_hz is not None else "UNAVAILABLE")
        if t.rssi_dbm is not None or t.link_quality is not None:
            set_status(self.values["rssi"], f"{t.rssi_dbm or '--'} dBm / {t.link_quality or '--'}")
        else:
            set_status(self.values["rssi"], "UNAVAILABLE")
        set_status(self.values["command"], state.control.requested_mode.value)
        set_status(self.values["ack"], state.control.robot_acknowledgement.value)
