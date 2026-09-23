"""Local request controls. Critical buttons remain explicit and text-labelled."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QLabel, QPushButton, QSizePolicy,
                               QSlider, QVBoxLayout)

from control_center.backend.command_manager import CommandManager
from control_center.models.state import WorldState
from control_center.widgets.common import Panel


class ControlPanel(Panel):
    def __init__(self, commands: CommandManager) -> None:
        super().__init__("CONTROL")
        self.commands = commands
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(7)
        layout.addWidget(self.title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        self.arm = QPushButton("ARM REQUEST")
        self.disarm = QPushButton("DISARM")
        self.auto = QPushButton("AUTO ENABLE")
        self.manual = QPushButton("MANUAL TAKEOVER")
        self.stop = QPushButton("SOFTWARE STOP")
        self.stop.setObjectName("criticalButton")
        self.disarm.setObjectName("warningButton")
        self.manual.setObjectName("warningButton")
        for button in (self.arm, self.disarm, self.auto, self.manual, self.stop):
            button.setMinimumHeight(38)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(self.arm, 0, 0)
        grid.addWidget(self.disarm, 0, 1)
        grid.addWidget(self.auto, 1, 0, 1, 2)
        grid.addWidget(self.manual, 2, 0, 1, 2)
        grid.addWidget(self.stop, 3, 0, 1, 2)
        layout.addLayout(grid)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(3)
        self.request_values = {}
        for row, (key, text, value) in enumerate((
            ("mode", "Requested mode", "NONE"),
            ("arm", "Requested arm", "DISARMED"),
            ("ack", "Robot acknowledgement", "UNAVAILABLE"),
            ("speed", "Max speed request", "50%"),
        )):
            form.addWidget(QLabel(text), row, 0)
            value_label = QLabel(value)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            form.addWidget(value_label, row, 1)
            self.request_values[key] = value_label
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, 100)
        self.speed.setValue(50)
        layout.addWidget(self.speed)
        self.reset_stop = QPushButton("RESET LOCAL STOP")
        self.reset_stop.setMinimumHeight(36)
        self.reset_stop.setEnabled(False)
        layout.addWidget(self.reset_stop)
        self.arm.clicked.connect(lambda: commands.request_arm(True))
        self.disarm.clicked.connect(lambda: commands.request_arm(False))
        self.auto.clicked.connect(lambda: commands.request_auto(True))
        self.manual.clicked.connect(commands.request_manual_takeover)
        self.stop.clicked.connect(commands.request_software_stop)
        self.reset_stop.clicked.connect(commands.clear_software_stop)
        self.speed.valueChanged.connect(self._speed_changed)

    def _speed_changed(self, value: int) -> None:
        self.request_values["speed"].setText(f"{value}%")
        self.commands.set_max_speed(value)

    def update_state(self, state: WorldState) -> None:
        control = state.control
        self.request_values["mode"].setText(control.requested_mode.value)
        self.request_values["arm"].setText("ARMED" if control.requested_arm else "DISARMED")
        self.request_values["ack"].setText(control.robot_acknowledgement.value)
        self.reset_stop.setEnabled(control.software_stop)
        self.arm.setEnabled(not control.software_stop)
        self.auto.setEnabled(not control.software_stop)
