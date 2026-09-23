"""Telemetry ingestion placeholder for the future ESP-NOW base-station link."""

from control_center.models.state import RobotTelemetry


def unavailable_telemetry() -> RobotTelemetry:
    return RobotTelemetry()
