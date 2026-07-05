"""VOLT robot - camera and computer vision.

Owns the CSI camera and provides:

- **Face detection** (MediaPipe) - returns the face center for track.py.
- **Motion detection** - frame differencing, used as the trigger for the
  grab behavior.
- **Color detection** - dominant-color guess in the frame center.

Future upgrades (object detection / YOLO) belong here too; keep the same
pattern of small methods returning plain data so callers never depend on
OpenCV/MediaPipe types.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

import config
from utils import get_logger

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = np = None

try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None

log = get_logger("vision")

# Frame-differencing threshold (pixel intensity delta counted as motion)
_DIFF_THRESHOLD = 25
_GAUSSIAN_KERNEL = (21, 21)
# Fraction of frame width/height sampled for the color guess
_COLOR_SAMPLE_FRAC = 0.2
# HSV hue boundaries (OpenCV hue range is 0-179)
_HUE_RED_MAX, _HUE_YELLOW_MAX, _HUE_GREEN_MAX, _HUE_BLUE_MAX = 10, 35, 85, 130
_HUE_RED_WRAP = 170
_MIN_SATURATION = 40
_MIN_VALUE = 40


@dataclass
class FaceObservation:
    """A detected face's center in pixels, plus frame size for context."""

    center_x: float
    center_y: float
    frame_width: int
    frame_height: int

    @property
    def offset_from_center(self) -> Tuple[float, float]:
        return (
            self.center_x - self.frame_width / 2,
            self.center_y - self.frame_height / 2,
        )


class Vision:
    """Camera owner. Construct once; call :meth:`release` when done."""

    def __init__(self) -> None:
        if cv2 is None:
            raise RuntimeError("opencv-python is not installed")
        self._capture = cv2.VideoCapture(config.CAMERA_INDEX)
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        if not self._capture.isOpened():
            raise RuntimeError(f"camera index {config.CAMERA_INDEX} did not open")

        self._face_detector = None
        if mp is not None:
            self._face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=config.FACE_DETECTION_CONFIDENCE,
            )
        else:
            log.warning("mediapipe not installed; face detection disabled")
        log.info("camera %d open at %dx%d", config.CAMERA_INDEX,
                 config.FRAME_WIDTH, config.FRAME_HEIGHT)

    # ------------------------------------------------------------------

    def read_frame(self) -> Optional["np.ndarray"]:
        """One BGR frame, or None on a failed read."""
        ok, frame = self._capture.read()
        return frame if ok else None

    def detect_face(self) -> Optional[FaceObservation]:
        """Detect the most confident face in a fresh frame."""
        if self._face_detector is None:
            return None
        frame = self.read_frame()
        if frame is None:
            return None
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._face_detector.process(rgb)
        if not result.detections:
            return None
        box = result.detections[0].location_data.relative_bounding_box
        return FaceObservation(
            center_x=(box.xmin + box.width / 2) * width,
            center_y=(box.ymin + box.height / 2) * height,
            frame_width=width,
            frame_height=height,
        )

    def wait_for_motion(self, timeout_s: float) -> bool:
        """Block until sustained motion is seen or ``timeout_s`` elapses."""
        previous = self._read_gray()
        if previous is None:
            return False
        confirmations = 0
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            gray = self._read_gray()
            if gray is None:
                continue
            diff = cv2.absdiff(previous, gray)
            mask = cv2.threshold(diff, _DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
            score = int(np.sum(mask) / 255)
            confirmations = confirmations + 1 if score > config.MOTION_THRESHOLD else 0
            if confirmations >= config.MOTION_CONFIRM_FRAMES:
                return True
            previous = gray
            time.sleep(0.05)
        return False

    def guess_center_color(self) -> str:
        """Dominant color in the frame center: red/green/blue/yellow/unknown."""
        frame = self.read_frame()
        if frame is None:
            return "unknown"
        height, width = frame.shape[:2]
        dx, dy = int(width * _COLOR_SAMPLE_FRAC / 2), int(height * _COLOR_SAMPLE_FRAC / 2)
        center = frame[height // 2 - dy: height // 2 + dy,
                       width // 2 - dx: width // 2 + dx]
        hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
        hue = float(np.mean(hsv[:, :, 0]))
        if float(np.mean(hsv[:, :, 1])) < _MIN_SATURATION:
            return "unknown"
        if float(np.mean(hsv[:, :, 2])) < _MIN_VALUE:
            return "unknown"
        if hue < _HUE_RED_MAX or hue > _HUE_RED_WRAP:
            return "red"
        if hue < _HUE_YELLOW_MAX:
            return "yellow"
        if hue < _HUE_GREEN_MAX:
            return "green"
        if hue < _HUE_BLUE_MAX:
            return "blue"
        return "unknown"

    def measure_fps(self, sample_frames: int = 30) -> float:
        """Rough capture frame rate, used by debug.py."""
        start = time.monotonic()
        captured = 0
        for _ in range(sample_frames):
            if self.read_frame() is not None:
                captured += 1
        elapsed = time.monotonic() - start
        return captured / elapsed if elapsed > 0 else 0.0

    def _read_gray(self) -> Optional["np.ndarray"]:
        frame = self.read_frame()
        if frame is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, _GAUSSIAN_KERNEL, 0)

    def release(self) -> None:
        self._capture.release()


if __name__ == "__main__":
    vision = Vision()
    print(f"FPS: {vision.measure_fps():.1f}")
    print("Watching for motion (10s)...")
    print("Motion!" if vision.wait_for_motion(10) else "No motion.")
    print(f"Center color: {vision.guess_center_color()}")
    face = vision.detect_face()
    print(f"Face: {face}" if face else "No face detected.")
    vision.release()
