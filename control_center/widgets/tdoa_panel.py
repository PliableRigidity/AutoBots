"""TDOA diagnostics placeholder panel."""

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout

from control_center.models.state import WorldState
from control_center.widgets.common import Panel, set_status


class TdoaPanel(Panel):
    def __init__(self) -> None:
        super().__init__("TDOA / SENSOR STATUS")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        header = QGridLayout()
        header.addWidget(self.title, 0, 0)
        self.overall = QLabel("UNAVAILABLE")
        header.addWidget(self.overall, 0, 4)
        set_status(self.overall, "UNAVAILABLE")
        for column, text in enumerate(("Receiver", "Status", "Arrival", "Δt", "Quality")):
            header.addWidget(QLabel(text), 1, column)
        self.rows = []
        for i in range(4):
            cells = [QLabel(f"RX{i}"), QLabel("NO DATA"), QLabel("--"), QLabel("--"), QLabel("--")]
            for column, cell in enumerate(cells):
                header.addWidget(cell, i + 2, column)
            self.rows.append(cells)
        layout.addLayout(header)
        self.summary = QLabel("Rate: --   Residual: --   Solved X/Y: -- / --   Confidence: --   Rejected: --")
        layout.addWidget(self.summary)

    def update_state(self, state: WorldState) -> None:
        tdoa = state.tdoa
        set_status(self.overall, "OK" if tdoa.available else "UNAVAILABLE")
        for cells, channel in zip(self.rows, tdoa.channels):
            set_status(cells[1], channel.status.value)
            cells[2].setText(f"{channel.arrival_timestamp_us:.1f} µs" if channel.arrival_timestamp_us is not None else "--")
            cells[3].setText(f"{channel.relative_delay_us:.1f} µs" if channel.relative_delay_us is not None else "--")
            cells[4].setText(f"{channel.signal_quality:.0%}" if channel.signal_quality is not None else "--")
        self.summary.setText(
            f"Rate: {tdoa.update_rate_hz if tdoa.update_rate_hz is not None else '--'}   "
            f"Residual: {tdoa.solver_residual if tdoa.solver_residual is not None else '--'}   "
            f"Solved X/Y: {tdoa.x if tdoa.x is not None else '--'} / {tdoa.y if tdoa.y is not None else '--'}   "
            f"Confidence: {tdoa.confidence if tdoa.confidence is not None else '--'}   "
            f"Rejected: {','.join(map(str, tdoa.rejected_channels)) or '--'}")
