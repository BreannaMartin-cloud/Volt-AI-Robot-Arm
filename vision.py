"""VOLT robot - camera and computer vision.

Owns the Raspberry Pi CSI camera and provides:

- **Face detection** - returns the face center for track.py.
- **Motion detection** - frame differencing, used as the trigger for grab.
- **Color detection** - dominant-color guess in the frame center.

Important Raspberry Pi note:
    The Pi Camera on Raspberry Pi OS Bookworm is captured with Picamera2,
    not ``cv2.VideoCapture(0)``. OpenCV is still used for processing after
    each frame is captured.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import config
from utils import get_logger

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = np = None

try:
    from picamera2 import Picamera2
except ImportError:  # pragma: no cover
    Picamera2 = None

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

# Frames sampled when measuring whether the camera sustains its target FPS.
_FPS_PROBE_FRAMES = 15

_HAAR_PATHS = [
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
    "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
]


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
    """Camera owner. Construct once; call :meth:`release` when done.

    Uses Picamera2 for the Raspberry Pi CSI camera and OpenCV for image
    processing. The rest of VOLT should call :meth:`read_frame` and should
    never open the camera directly.
    """

    backend = "Picamera2"

    def __init__(self) -> None:
        if cv2 is None or np is None:
            raise RuntimeError("opencv-python and numpy are required")
        if Picamera2 is None:
            raise RuntimeError(
                "Picamera2 is not installed. Run: sudo apt install -y python3-picamera2"
            )

        self._picam2 = Picamera2()
        self._started = False

        # cv2.rotate codes for the four supported orientations.
        self._rotate_code = {
            0: None,
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }[config.CAMERA_ROTATION]

        self.active_width, self.active_height, self.active_fps = self._start_best_mode()

        self._face_detector = None
        self._haar_face = None
        if mp is not None:
            self._face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=config.FACE_DETECTION_CONFIDENCE,
            )
            log.info("face detection backend: MediaPipe")
        else:
            self._haar_face = self._load_haar_detector()
            if self._haar_face is not None:
                log.warning("mediapipe not installed; using OpenCV Haar face detector")
            else:
                log.warning("mediapipe not installed and Haar cascade not found; face detection disabled")

        log.info(
            "camera backend %s active at %dx%d @ %.1f FPS "
            "(rotation %d deg, hflip=%s, vflip=%s)",
            self.backend,
            self.active_width,
            self.active_height,
            self.active_fps,
            config.CAMERA_ROTATION,
            config.CAMERA_FLIP_HORIZONTAL,
            config.CAMERA_FLIP_VERTICAL,
        )

    # ------------------------------------------------------------------
    # Capture mode negotiation
    # ------------------------------------------------------------------

    def _configure_and_start(self, width: int, height: int) -> None:
        """Configure Picamera2 for RGB frames and start streaming."""
        if self._started:
            self._picam2.stop()
            self._started = False

        camera_config = self._picam2.create_preview_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": float(config.CAMERA_FPS)},
        )
        self._picam2.configure(camera_config)
        self._picam2.start()
        self._started = True
        time.sleep(0.2)  # let auto-exposure/stream settle

    def _try_mode(self, width: int, height: int) -> tuple[int, int, float]:
        """Start a mode and measure actual frame shape and FPS from frames."""
        self._configure_and_start(width, height)

        # Drop a few warm-up frames.
        for _ in range(3):
            self._picam2.capture_array()

        start = time.monotonic()
        captured = 0
        actual_w, actual_h = 0, 0
        for _ in range(_FPS_PROBE_FRAMES):
            frame = self._picam2.capture_array()
            if frame is not None:
                captured += 1
                actual_h, actual_w = frame.shape[:2]
        elapsed = time.monotonic() - start
        fps = captured / elapsed if elapsed > 0 else 0.0
        return actual_w, actual_h, fps

    def _start_best_mode(self) -> tuple[int, int, float]:
        """Preferred mode first; fall back if size or FPS is not usable."""
        width, height, fps = self._try_mode(config.CAMERA_WIDTH, config.CAMERA_HEIGHT)

        reason = None
        if (width, height) != (config.CAMERA_WIDTH, config.CAMERA_HEIGHT):
            reason = (
                f"camera delivered {width}x{height} instead of "
                f"{config.CAMERA_WIDTH}x{config.CAMERA_HEIGHT}"
            )
        elif fps < config.CAMERA_MIN_SUSTAINED_FPS:
            reason = (
                f"only {fps:.1f} FPS sustained at "
                f"{config.CAMERA_WIDTH}x{config.CAMERA_HEIGHT} "
                f"(need >= {config.CAMERA_MIN_SUSTAINED_FPS:.0f})"
            )
        if reason is None:
            return width, height, fps

        log.warning(
            "falling back to %dx%d: %s",
            config.CAMERA_FALLBACK_WIDTH,
            config.CAMERA_FALLBACK_HEIGHT,
            reason,
        )
        return self._try_mode(config.CAMERA_FALLBACK_WIDTH, config.CAMERA_FALLBACK_HEIGHT)

    # ------------------------------------------------------------------
    # Frame acquisition - THE single orientation point
    # ------------------------------------------------------------------

    def _orient(self, frame: "np.ndarray") -> "np.ndarray":
        """Correct the raw frame for how the camera is physically mounted."""
        if self._rotate_code is not None:
            frame = cv2.rotate(frame, self._rotate_code)
        if config.CAMERA_FLIP_HORIZONTAL:
            frame = cv2.flip(frame, 1)
        if config.CAMERA_FLIP_VERTICAL:
            frame = cv2.flip(frame, 0)
        return frame

    def read_frame(self) -> Optional["np.ndarray"]:
        """One orientation-corrected BGR frame, or None on a failed read.

        Picamera2 returns RGB888 frames. VOLT keeps the public API as BGR so
        existing OpenCV code continues to work normally.
        """
        try:
            frame_rgb = self._picam2.capture_array()
        except Exception as exc:  # noqa: BLE001
            log.error("camera read failed: %s", exc)
            return None
        if frame_rgb is None:
            return None
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        return self._orient(frame_bgr)

    def is_open(self) -> bool:
        return self._started

    def resolution(self) -> tuple[int, int]:
        return self.active_width, self.active_height

    def fps(self) -> float:
        return self.active_fps

    # ------------------------------------------------------------------
    # Vision features
    # ------------------------------------------------------------------

    def _load_haar_detector(self):
        """Load OpenCV's Haar face detector as a MediaPipe fallback."""
        paths = list(_HAAR_PATHS)
        data_obj = getattr(cv2, "data", None)
        if data_obj is not None:
            haar_dir = getattr(data_obj, "haarcascades", "")
            if haar_dir:
                paths.insert(0, str(Path(haar_dir) / "haarcascade_frontalface_default.xml"))
        for path in paths:
            if Path(path).exists():
                detector = cv2.CascadeClassifier(path)
                if not detector.empty():
                    log.info("Haar face cascade loaded from %s", path)
                    return detector
        return None

    def detect_face(self) -> Optional[FaceObservation]:
        """Detect one face in a fresh frame.

        Prefer MediaPipe when installed; otherwise use OpenCV Haar cascade if
        available. Returns the largest/highest-confidence face center.
        """
        frame = self.read_frame()
        if frame is None:
            return None
        height, width = frame.shape[:2]

        if self._face_detector is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._face_detector.process(rgb)
            if not result.detections:
                return None
            # Pick highest-confidence detection.
            detection = max(
                result.detections,
                key=lambda det: det.score[0] if det.score else 0.0,
            )
            box = detection.location_data.relative_bounding_box
            return FaceObservation(
                center_x=(box.xmin + box.width / 2) * width,
                center_y=(box.ymin + box.height / 2) * height,
                frame_width=width,
                frame_height=height,
            )

        if self._haar_face is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._haar_face.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=7,
                minSize=(80, 80),
            )
            if len(faces) == 0:
                return None
            x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
            return FaceObservation(
                center_x=x + w / 2,
                center_y=y + h / 2,
                frame_width=width,
                frame_height=height,
            )
        return None

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
        dx = int(width * _COLOR_SAMPLE_FRAC / 2)
        dy = int(height * _COLOR_SAMPLE_FRAC / 2)
        center = frame[
            height // 2 - dy: height // 2 + dy,
            width // 2 - dx: width // 2 + dx,
        ]
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
        if self._face_detector is not None:
            self._face_detector.close()
        if self._started:
            self._picam2.stop()
            self._started = False
        self._picam2.close()


if __name__ == "__main__":
    vision = Vision()
    print(f"Backend: {vision.backend}")
    print(f"Active mode: {vision.active_width}x{vision.active_height} "
          f"@ {vision.active_fps:.1f} FPS")
    print(f"Pipeline FPS (with orientation): {vision.measure_fps():.1f}")
    frame = vision.read_frame()
    if frame is not None:
        cv2.imwrite("vision_test.jpg", frame)
        print("Saved orientation-corrected frame to vision_test.jpg")
    print("Watching for motion (10s)...")
    print("Motion!" if vision.wait_for_motion(10) else "No motion.")
    print(f"Center color: {vision.guess_center_color()}")
    face = vision.detect_face()
    print(f"Face: {face}" if face else "No face detected.")
    vision.release()
