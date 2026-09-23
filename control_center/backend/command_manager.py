"""Local command requests; this class never claims onboard acknowledgement."""

import logging

from PySide6.QtCore import QObject, Signal

from control_center.backend.state_store import StateStore
from control_center.models.state import ControlMode, Status


class CommandManager(QObject):
    event = Signal(str)

    def __init__(self, store: StateStore) -> None:
        super().__init__()
        self.store = store
        self.log = logging.getLogger(__name__)

    def request_arm(self, armed: bool) -> None:
        state = self.store.state.control
        state.requested_arm = armed
        state.robot_acknowledgement = Status.UNAVAILABLE
        self._record(f"{'ARM' if armed else 'DISARM'} requested; robot acknowledgement unavailable")
        self.store.publish()

    def request_auto(self, enabled: bool) -> None:
        state = self.store.state.control
        if enabled and not state.software_stop:
            state.requested_mode = ControlMode.AUTO
            self._record("AUTO requested locally; awaiting robot link")
        else:
            state.requested_mode = ControlMode.NONE if not enabled else state.requested_mode
            self._record("AUTO disabled")
        self.store.publish()

    def request_manual_takeover(self) -> None:
        self.store.state.control.requested_mode = ControlMode.MANUAL
        self._record("Manual takeover requested; autonomous output disabled locally")
        self.store.publish()

    def request_software_stop(self) -> None:
        control = self.store.state.control
        control.software_stop = True
        control.requested_arm = False
        control.requested_mode = ControlMode.NONE
        self._record("Software stop requested; local command output inhibited")
        self.store.publish()

    def clear_software_stop(self) -> None:
        self.store.state.control.software_stop = False
        self._record("Software stop reset locally")
        self.store.publish()

    def set_max_speed(self, percent: int) -> None:
        self.store.state.control.max_speed_percent = percent
        self.store.publish()

    def request_recalibrate_arena(self) -> None:
        self._record("Arena recalibration requested — detect landmarks and recompute homography")

    def request_capture_background(self) -> None:
        self._record("Arena background capture requested — ensure arena is empty")

    def request_auto_acquire_opponent(self) -> None:
        self._record("Auto opponent acquisition requested")

    def request_select_opponent(self) -> None:
        self._record("Manual opponent selection requested — click-drag ROI in camera view")

    def request_clear_track(self) -> None:
        self._record("Opponent track cleared — reacquisition required")

    def _record(self, message: str) -> None:
        self.log.info(message)
        self.event.emit(message)
