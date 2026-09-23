"""Application startup, configuration, and styling."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

import yaml
from PySide6.QtWidgets import QApplication

from control_center.backend.logging_manager import configure_logging
from control_center.main_window import MainWindow


ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoBot native desktop control center")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "control_center.yaml")
    parser.add_argument("--demo", action="store_true", help="Show clearly labelled simulated telemetry")
    parser.add_argument("--camera-index", type=int, help="Override the configured OpenCV camera index")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_path = configure_logging(ROOT / "logs")
    try:
        config = load_config(args.config)
    except Exception as exc:
        logging.getLogger(__name__).exception("Could not load configuration")
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.camera_index is not None:
        config["camera_index"] = args.camera_index
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AutoBot Control Center")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(config, demo=args.demo)
    window.show()
    logging.getLogger(__name__).info("Control Center started; log=%s", log_path)
    code = app.exec()
    logging.getLogger(__name__).info("Control Center stopped")
    return code


STYLESHEET = """
QWidget { background: #11161d; color: #d9dee5; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow { background: #0b0f14; }
QFrame#panel { background: #171e27; border: 1px solid #2b3542; border-radius: 5px; }
QLabel#appTitle { font-size: 18pt; font-weight: 700; letter-spacing: 1px; }
QLabel#panelTitle { color: #9eabb8; font-size: 10pt; font-weight: 700; letter-spacing: 1px; }
QLabel#modeBadge { color: #6fa8dc; font-weight: 700; padding: 5px 10px; border: 1px solid #3c6f9c; }
QLabel#demoBadge { color: #11161d; background: #e8b85b; font-weight: 800; padding: 5px 10px; }
QPushButton { background: #263241; border: 1px solid #3b4a5d; border-radius: 4px; padding: 7px 10px; font-size: 10pt; font-weight: 650; }
QPushButton:hover { background: #324256; }
QPushButton:disabled { color: #66717f; background: #1b232d; }
QPushButton#warningButton { background: #694b20; border-color: #a9782e; }
QPushButton#criticalButton { background: #8c2931; border-color: #d34e59; font-size: 11pt; padding: 12px; }
QPlainTextEdit { background: #0d1218; border: 1px solid #2b3542; color: #b8c2cc; font-family: Consolas; }
QSplitter::handle { background: #0b0f14; width: 5px; height: 5px; }
QScrollArea#sidebarScroll { background: transparent; border: none; }
QWidget#sidebarContent { background: transparent; }
QSlider::groove:horizontal { height: 5px; background: #2b3542; }
QSlider::handle:horizontal { background: #6fa8dc; width: 15px; margin: -5px 0; border-radius: 7px; }
"""
