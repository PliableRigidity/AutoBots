"""Disconnected robot transport boundary. No ports are probed automatically."""

from control_center.models.state import LinkState


class DisconnectedRobotLink:
    def __init__(self) -> None:
        self.state = LinkState()

    def connect(self) -> bool:
        return False

    def disconnect(self) -> None:
        self.state.connected = False

    def send_command(self, _command: object) -> bool:
        return False

    def receive_telemetry(self) -> None:
        return None

    def is_connected(self) -> bool:
        return False
