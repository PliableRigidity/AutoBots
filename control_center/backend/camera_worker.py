"""Independent camera acquisition and latest-frame AprilTag processing workers."""

from __future__ import annotations

import logging
import platform
from pathlib import Path
import threading
import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from control_center.backend.vision import AprilTagTracker, TagDetection
from control_center.backend.arena_vision import ArenaVisionProcessor, ArenaVisionResult
from control_center.models.state import VisionState


class LatestFrameBuffer:
    """Thread-safe single frame slot; slow consumers skip old frames."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._sequence = 0
        self._frame: np.ndarray | None = None
        self._timestamp = 0.0
        self._closed = False

    def publish(self, frame: np.ndarray, timestamp: float) -> None:
        with self._condition:
            self._sequence += 1
            # Vision owns this snapshot while capture immediately reuses its frame.
            self._frame = frame.copy()
            self._timestamp = timestamp
            self._condition.notify()

    def wait_for_new(self, after_sequence: int) -> tuple[int, np.ndarray | None, float]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > after_sequence or self._closed, timeout=0.25)
            if self._closed:
                return after_sequence, None, 0.0
            return self._sequence, self._frame, self._timestamp

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class DetectionBuffer:
    """Thread-safe latest detector result, never an accumulating queue."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detections: list[TagDetection] = []
        self._own: TagDetection | None = None
        self._timestamp = 0.0
        self._processing_ms = 0.0
        self._fps = 0.0
        self._available = False
        self._arena = ArenaVisionResult()

    def publish(self, detections: list[TagDetection], own: TagDetection | None,
                timestamp: float, processing_ms: float, fps: float, available: bool = True,
                arena: ArenaVisionResult | None = None) -> None:
        with self._lock:
            self._detections = detections
            self._own = own
            self._timestamp = timestamp
            self._processing_ms = processing_ms
            self._fps = fps
            self._available = available
            if arena is not None:
                self._arena = arena

    def snapshot(self) -> tuple[list[TagDetection], TagDetection | None, float, float, float, bool, ArenaVisionResult]:
        with self._lock:
            return (self._detections, self._own, self._timestamp,
                    self._processing_ms, self._fps, self._available, self._arena)


class LatestDisplayFrame:
    """Single rendered-frame slot read by the GUI at its own refresh rate."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._frame: np.ndarray | None = None

    def publish(self, frame: np.ndarray) -> None:
        with self._lock:
            self._sequence += 1
            self._frame = frame

    def snapshot(self, after_sequence: int) -> tuple[int, np.ndarray | None]:
        with self._lock:
            if self._sequence == after_sequence:
                return after_sequence, None
            return self._sequence, self._frame


class VisionWorker(QThread):
    """Processes only the newest camera frame and never blocks acquisition."""

    worker_error = Signal(str)
    event = Signal(str)
    background_progress = Signal(int, int)
    calibration_result = Signal(bool, str)

    def __init__(self, config: dict, frames: LatestFrameBuffer,
                 results: DetectionBuffer, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.frames = frames
        self.results = results
        self._running = False
        self._log = logging.getLogger(__name__ + ".vision")
        self._request_lock = threading.Lock()
        self._calibration_points: list[tuple[float, float]] | None = None
        self._background_requested = False
        self._auto_requested = False
        self._manual_roi: tuple[int, int, int, int] | None = None
        self._clear_requested = False
        self._debug_requested = False
        self.processor: ArenaVisionProcessor | None = None

    def request_calibration(self, points: list[tuple[float, float]]) -> None:
        with self._request_lock:
            self._calibration_points = list(points)

    def request_background_capture(self) -> None:
        with self._request_lock:
            self._background_requested = True

    def request_auto_acquire(self) -> None:
        with self._request_lock:
            self._auto_requested = True

    def request_manual_roi(self, roi: tuple[int, int, int, int]) -> None:
        with self._request_lock:
            self._manual_roi = roi

    def request_clear_track(self) -> None:
        with self._request_lock:
            self._clear_requested = True

    def request_debug_cycle(self) -> None:
        with self._request_lock:
            self._debug_requested = True

    def stop(self) -> None:
        self._running = False
        self.requestInterruption()
        self.frames.close()

    def run(self) -> None:
        try:
            april = self.config.get("april_tag", {})
            tracker = AprilTagTracker(
                str(april.get("family", self.config.get("april_tag_family", "DICT_APRILTAG_36h11"))),
                int(self.config.get("self_tag_id", 0)), tag_size_m=april.get("tag_size_m"),
                camera_matrix=april.get("camera_matrix"),
                distortion_coefficients=april.get("distortion_coefficients"))
        except Exception as exc:
            self.worker_error.emit(f"AprilTag detector unavailable: {exc}")
            return
        try:
            self.processor = ArenaVisionProcessor(self.config, Path(__file__).resolve().parents[2])
        except Exception as exc:
            self._log.exception("Arena vision initialization failed")
            self.worker_error.emit(f"Arena vision unavailable: {exc}")
            self.processor = None
        self.results.publish([], None, 0.0, 0.0, 0.0, available=True)
        self._running = True
        sequence = 0
        smoothed_fps = 0.0
        last_completed = 0.0
        last_log = time.perf_counter()
        while self._running and not self.isInterruptionRequested():
            sequence, frame, captured_at = self.frames.wait_for_new(sequence)
            if frame is None:
                continue
            started = time.perf_counter()
            detections, own = tracker.detect(frame)
            arena = ArenaVisionResult()
            if self.processor is not None:
                self._apply_requests()
                arena = self.processor.process(frame, own, captured_at)
                if arena.background_progress:
                    self.background_progress.emit(*arena.background_progress)
                for message in arena.events:
                    self.event.emit(message)
            finished = time.perf_counter()
            processing_ms = (finished - started) * 1000.0
            instant_fps = (1.0 / max(finished - last_completed, 1e-6)
                           if last_completed else 0.0)
            last_completed = finished
            smoothed_fps = instant_fps if not smoothed_fps else 0.9 * smoothed_fps + 0.1 * instant_fps
            self.results.publish(detections, own, captured_at, processing_ms, smoothed_fps,
                                 arena=arena)
            if finished - last_log >= 5.0:
                self._log.info("Vision %.1f FPS, AprilTag %.1f ms", smoothed_fps, processing_ms)
                last_log = finished
        self._running = False

    def _apply_requests(self) -> None:
        if self.processor is None:
            return
        with self._request_lock:
            points, self._calibration_points = self._calibration_points, None
            background, self._background_requested = self._background_requested, False
            auto, self._auto_requested = self._auto_requested, False
            roi, self._manual_roi = self._manual_roi, None
            clear, self._clear_requested = self._clear_requested, False
            debug, self._debug_requested = self._debug_requested, False
        if points is not None:
            ok, message = self.processor.calibrate(points)
            self.calibration_result.emit(ok, message)
            self.event.emit(message)
        if background:
            ok, message = self.processor.request_background()
            self.event.emit(message)
            if not ok:
                self.worker_error.emit(message)
        if auto:
            self.processor.request_auto_acquire()
            self.event.emit("Auto acquire requested")
        if roi is not None:
            self.processor.request_manual_roi(roi)
            self.event.emit("Manual opponent selection submitted")
        if clear:
            self.processor.clear_track()
            self.event.emit("Opponent track cleared")
        if debug:
            mode = self.processor.cycle_debug_mode()
            self.event.emit(f"Vision debug view: {mode}")


class CameraWorker(QThread):
    vision_ready = Signal(object)
    camera_status = Signal(bool, str)
    camera_connecting = Signal(str)
    worker_error = Signal(str)

    def __init__(self, config: dict, frames: LatestFrameBuffer,
                 detections: DetectionBuffer, display: LatestDisplayFrame, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.frames = frames
        self.detections = detections
        self.display = display
        self._running = False
        self._log = logging.getLogger(__name__)

    def stop(self) -> None:
        self._running = False
        self.requestInterruption()

    def run(self) -> None:
        try:
            self._run_capture()
        except Exception as exc:
            self._log.exception("Unhandled camera worker failure")
            message = f"Camera error: {type(exc).__name__}: {exc}"
            self.worker_error.emit(message)
            self.camera_status.emit(False, message)

    def _run_capture(self) -> None:
        self._startup_started = time.perf_counter()
        index = int(self.config.get("camera_index", 0))
        self._startup_log("worker started")
        self._startup_log("configured index %d", index)
        self.camera_connecting.emit(f"Opening camera index {index}")
        cap, backend_name, first_frame, backend_id = self._open_camera(index)
        if not cap.isOpened() or first_frame is None:
            self.camera_status.emit(False, f"Camera error: index {index} did not return a valid frame")
            cap.release()
            return
        # Publish the validated frame before metrics, readback, or any optional tuning.
        self.display.publish(first_frame)
        self._startup_log("first frame published to GUI")
        self.camera_status.emit(True, f"Camera live: index {index} ({backend_name})")
        if bool(self.config.get("camera_apply_requested_settings", False)):
            cap, configured_frame, configured = self._configure_preferred_mode(
                cap, index, backend_id)
            if configured_frame is None:
                self.camera_status.emit(False, "Camera error: preferred mode and default recovery failed")
                cap.release()
                return
            first_frame = configured_frame
            self.display.publish(configured_frame)
            backend_name += "+preferred" if configured else "+default-fallback"
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        reported_fps = cap.get(cv2.CAP_PROP_FPS)
        fourcc_value = int(cap.get(cv2.CAP_PROP_FOURCC))
        raw_fourcc = bytes((fourcc_value >> (8 * i)) & 0xFF for i in range(4))
        actual_fourcc = (raw_fourcc.decode("ascii") if all(32 <= byte < 127 for byte in raw_fourcc)
                         else f"0x{fourcc_value:08x}")
        self._log.info("Camera settings: backend=%s index=%d actual=%dx%d reported_fps=%.2f fourcc=%s",
                       backend_name, index, width, height, reported_fps, actual_fourcc or "unknown")
        self._running = True
        self._startup_log("camera ready: %dx%d @ %.1f FPS (%s, %s)",
                          width, height, reported_fps, backend_name,
                          actual_fourcc or "format unknown")
        last = 0.0
        capture_fps = 0.0
        capture_ms = 0.0
        overlay_ms = 0.0
        last_log = time.perf_counter()
        last_state_emit = 0.0
        state_interval = 1.0 / max(1.0, float(self.config.get("state_refresh_hz", 10)))
        failures = 0
        pending_frame: np.ndarray | None = first_frame
        capture_count = 0
        display_publish_count = 0
        while self._running and not self.isInterruptionRequested():
            read_started = time.perf_counter()
            used_pending = pending_frame is not None
            if pending_frame is not None:
                frame = pending_frame
                pending_frame = None
                ok = True
            else:
                ok, frame = cap.read()
            read_finished = time.perf_counter()
            if not ok:
                failures += 1
                if failures >= 10:
                    self.camera_status.emit(False, "Camera stopped returning frames")
                    break
                self.msleep(20)
                continue
            failures = 0
            capture_count += 1
            now = read_finished
            instant_fps = 1.0 / max(now - last, 1e-6) if last else 0.0
            last = now
            if instant_fps:
                capture_fps = instant_fps if capture_fps == 0 else 0.9 * capture_fps + 0.1 * instant_fps
            read_ms = (read_finished - read_started) * 1000.0
            if not used_pending:
                capture_ms = read_ms if capture_ms == 0 else 0.9 * capture_ms + 0.1 * read_ms
            self.frames.publish(frame, now)
            (detections, own, detected_at, detection_ms, vision_fps,
             detector_available, arena) = self.detections.snapshot()
            detection_age_ms = (now - detected_at) * 1000.0 if detected_at else 0.0
            detection_fresh = detected_at > 0 and detection_age_ms <= float(
                self.config.get("vision_result_max_age_ms", 250))
            overlay_started = time.perf_counter()
            if detector_available and detection_fresh:
                AprilTagTracker.draw(frame, detections, own)
                self._draw_arena_overlays(frame, arena)
            overlay_sample_ms = (time.perf_counter() - overlay_started) * 1000.0
            overlay_ms = overlay_sample_ms if overlay_ms == 0 else 0.9 * overlay_ms + 0.1 * overlay_sample_ms
            height, width = frame.shape[:2]
            vision = VisionState(
                self_detected=detection_fresh and own is not None,
                tag_id=own.tag_id if detection_fresh and own else None,
                image_center=own.center if detection_fresh and own else None,
                image_heading_rad=own.image_heading_rad if detection_fresh and own else None,
                fps=capture_fps,
                capture_fps=capture_fps,
                vision_fps=vision_fps,
                capture_read_ms=capture_ms,
                detection_ms=detection_ms,
                overlay_ms=overlay_ms,
                frame_timestamp=now,
                detection_timestamp=detected_at,
                detection_age_ms=detection_age_ms,
                resolution=(width, height),
                detector_available=detector_available,
                camera_state="LIVE",
                frame_age_ms=max(0.0, (time.perf_counter() - now) * 1000.0),
                arena_calibrated=arena.homography_valid,
                homography_valid=arena.homography_valid,
                background_loaded=arena.background_loaded,
                calibration_error=arena.calibration_error,
                calibration_timestamp=arena.calibration_timestamp,
                landmark_status=arena.landmark_status,
                background_progress=arena.background_progress,
                opponent=arena.opponent,
                opponent_detected=arena.opponent.detected,
                opponent_tracking_state=arena.opponent.tracking_state,
                opponent_confidence=arena.opponent.confidence,
                opponent_auto_acquired=arena.opponent.acquisition_source.value == "AUTO",
                self_pose=arena.self_pose,
                self_camera_xyz=(tuple(float(v) for v in own.camera_tvec)
                                 if detection_fresh and own is not None and own.camera_tvec is not None
                                 else None),
            )
            if now - last_state_emit >= state_interval:
                self.vision_ready.emit(vision)
                last_state_emit = now
            self.display.publish(arena.debug_frame if arena.debug_frame is not None else frame)
            display_publish_count += 1
            if now - last_log >= 5.0:
                self._log.info("Capture %.1f FPS (read %.1f ms), overlay %.2f ms, vision %.1f FPS "
                               "(%.1f ms), captured=%d display_published=%d",
                               capture_fps, capture_ms, overlay_ms, vision_fps, detection_ms,
                               capture_count, display_publish_count)
                last_log = now
        cap.release()
        self._log.info("Camera released")
        self._running = False

    @staticmethod
    def _draw_arena_overlays(frame: np.ndarray, arena: ArenaVisionResult) -> None:
        opponent = arena.opponent
        if opponent.bbox:
            x, y, width, height = opponent.bbox
            color = (40, 170, 255) if opponent.detected else (80, 130, 180)
            cv2.rectangle(frame, (x, y), (x + width, y + height), color, 2)
            cv2.putText(frame, f"OPPONENT {opponent.tracking_state.value} {opponent.confidence:.0%}",
                        (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        if opponent.floor_point:
            point = tuple(int(value) for value in opponent.floor_point)
            cv2.circle(frame, point, 6, (40, 170, 255), 2)
            if opponent.vx is not None and opponent.vy is not None and arena.homography_valid:
                # Velocity remains available in arena units; a precise raw-image arrow
                # requires the calibration transform and is drawn by the minimap instead.
                cv2.circle(frame, point, 2, (40, 170, 255), -1)

    def _open_camera(
            self, index: int
    ) -> tuple[cv2.VideoCapture, str, np.ndarray | None, int | None]:
        requested = str(self.config.get("camera_backend", "auto")).lower()
        backend_map = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "auto": cv2.CAP_ANY}
        self._startup_log("backend requested: %s", requested)
        if requested in ("msmf", "dshow"):
            candidates: list[tuple[str, int | None]] = [(requested, backend_map[requested])]
            if bool(self.config.get("camera_enable_backend_fallbacks", True)):
                candidates.append(("default", None))
        else:
            candidates = [("default", None)]
            if bool(self.config.get("camera_enable_backend_fallbacks", True)) and platform.system() == "Windows":
                candidates.append(("dshow", cv2.CAP_DSHOW))
        for name, backend in candidates:
            self._startup_log("opening index %d using %s", index, name)
            cap = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
            self._startup_log("VideoCapture returned (%s)", name)
            opened = cap.isOpened()
            self._startup_log("isOpened=%s (%s)", opened, name)
            if not opened:
                cap.release()
                continue
            self._startup_log("reading first frame (%s)", name)
            try:
                ok, first_frame = cap.read()
            except Exception:
                self._log.exception("First frame read raised an exception (%s)", name)
                ok, first_frame = False, None
            self._startup_log("first read ret=%s; shape=%s", ok,
                              None if first_frame is None else first_frame.shape)
            if not ok or first_frame is None:
                cap.release()
                continue
            try:
                runtime_backend = cap.getBackendName()
                name = f"{name}/{runtime_backend}"
            except cv2.error:
                pass
            self._startup_log("capture validated using %s", name)
            return cap, name, first_frame, backend
        self._log.error("All camera open attempts failed for configured index %d", index)
        return cv2.VideoCapture(), requested, None, None

    def _startup_log(self, message: str, *args: object) -> None:
        elapsed = time.perf_counter() - self._startup_started
        self._log.info("[CAM] %-36s +%.2fs", message % args if args else message, elapsed)

    def _configure_preferred_mode(
            self, cap: cv2.VideoCapture, index: int,
            backend: int | None) -> tuple[cv2.VideoCapture, np.ndarray | None, bool]:
        """Reopen once on the same backend and request the preferred capture mode."""
        width = float(self.config.get("camera_width", 1280))
        height = float(self.config.get("camera_height", 720))
        fps = float(self.config.get("camera_fps", 30))
        fourcc = str(self.config.get("camera_fourcc", "")).strip()
        settings: list[tuple[str, int, float]] = [
            ("width", cv2.CAP_PROP_FRAME_WIDTH, width),
            ("height", cv2.CAP_PROP_FRAME_HEIGHT, height),
            ("FPS", cv2.CAP_PROP_FPS, fps),
        ]
        # C525/DSHOW requires MJPG last. MJPG-first silently yields 720p YUY2 at 10 FPS.
        if len(fourcc) == 4:
            settings.append(("FOURCC", cv2.CAP_PROP_FOURCC,
                             float(cv2.VideoWriter_fourcc(*fourcc))))
        self._startup_log("releasing validated default mode for one preferred-mode reopen")
        cap.release()
        tuned = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
        self._startup_log("preferred-mode VideoCapture returned; opened=%s", tuned.isOpened())
        accepted_all = tuned.isOpened()
        for label, prop, value in settings:
            if not tuned.isOpened():
                break
            accepted = tuned.set(prop, value)
            self._startup_log("requested %s=%s; accepted=%s", label, value, accepted)
            accepted_all = accepted_all and accepted
        if accepted_all:
            try:
                ok, configured_frame = tuned.read()
                self._startup_log("preferred first read ret=%s; shape=%s", ok,
                                  None if configured_frame is None else configured_frame.shape)
                actual_width = int(tuned.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(tuned.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if (ok and configured_frame is not None and
                        actual_width == int(width) and actual_height == int(height)):
                    return tuned, configured_frame, True
            except Exception:
                self._log.exception("Preferred-mode validation read failed")
        self._log.warning("Preferred mode unavailable; restoring same-backend default mode")
        tuned.release()
        restored = (cv2.VideoCapture(index) if backend is None
                    else cv2.VideoCapture(index, backend))
        if not restored.isOpened():
            return restored, None, False
        ok, restored_frame = restored.read()
        return restored, restored_frame if ok else None, False
