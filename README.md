# AutoBots

An autonomous antweight combat robot project with a native Python/Qt operator control center.

## Desktop Control Center

The V1 control center is a local PySide6 application. It shows the Logitech C525 feed,
runs AprilTag detection off the UI thread, exposes operator request controls, and provides
honest placeholders for hardware that is not connected yet. The GUI is not the robot's final
command authority; the future onboard ESP32-C3 arbiter remains responsible for safety and
actuator control.

### Install

```powershell
python -m pip install -r requirements.txt
```

### Run

```powershell
python main_control_center.py
```

If the C525 is not camera index 0, either edit `config/control_center.yaml` or run:

```powershell
python main_control_center.py --camera-index 1
```

The C525 is configured to use DirectShow because measured first-frame startup is under one
second, versus roughly 7–9 seconds for MSMF on this machine. Only the configured backend is
tried initially; the default backend is a single fallback if that attempt genuinely fails.
After publishing the first default frame, the camera performs one controlled same-backend reopen
for the configured mode. For this C525, DSHOW requires width, height, and FPS to be requested
before MJPG; placing MJPG first silently falls back to 720p YUY2 at roughly 10 FPS. If validation
fails, the application restores the same-backend default mode instead of losing the feed.

For clearly labelled simulated UI data:

```powershell
python main_control_center.py --demo
```

Normal mode never invents telemetry. ESP-NOW, ELRS/CRSF, state fusion, and real robot command
acknowledgement remain future integrations behind the existing backend/state interfaces. TDOA
code is retained only as optional legacy code and is not part of the active UI or runtime state.
Logs are written to `logs/`.

### Arena vision workflow

1. Press **RECALIBRATE ARENA** and click the four arena corners in the order shown in the event
   log: near-left, near-right, far-right, far-left. The transform is validated and persisted.
2. With an empty arena, press **CAPTURE BACKGROUND**. Capture runs on the vision thread and the
   panel shows progress.
3. Place the AprilTagged robot and opponent in the arena. Press **AUTO ACQUIRE OPPONENT**, or
   press **SELECT OPPONENT** and drag a rectangle around it.
4. Use **DEBUG VIEW** to cycle through raw, rectified, foreground, candidate, and self-exclusion
   views. Press **CLEAR TRACK** to discard the current opponent track.

Pit and flipper coordinates remain `null`/empty in `config/control_center.yaml` until physically
measured. The automatic landmark detector currently reports candidates only and never replaces a
valid manual homography.
