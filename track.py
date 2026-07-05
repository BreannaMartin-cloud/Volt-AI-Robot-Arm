"""VOLT robot - face tracking.

Closed-loop proportional tracking that keeps a detected face centered in
the camera frame by driving EXACTLY two joints:

- ``config.TRACK_PAN_JOINT``  (base - pans left/right)
- ``config.TRACK_TILT_JOINT`` (wrist_pitch - tilts the camera up/down)

No other joint is ever commanded from this module, and both joints are
double-clamped: to the tracking-specific limits AND (inside arm.py) to
the global soft limits. Per-tick steps are bounded by
``TRACK_MAX_STEP_DEG`` via ``MotionController.nudge_joint``.

Runs until stopped, or until no face has been seen for
``TRACK_FACE_LOST_TIMEOUT_S`` seconds.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import config
from motion import MotionController
from utils import clamp, get_logger
from vision import Vision

log = get_logger("track")


class FaceTracker:
    """Pan/tilt face tracking loop."""

    def __init__(self, motion: MotionController, vision: Vision) -> None:
        self._motion = motion
        self._vision = vision
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Ask a running :meth:`run` loop to exit at the next tick."""
        self._stop_event.set()

    def run(self, on_status=None) -> str:
        """Track until stopped or the face is lost too long.

        ``on_status`` is an optional callback ``(tracking: bool, fps: float)``
        for UI updates (debug line, OLED). Returns the reason the loop
        ended: ``"stopped"`` or ``"face_lost"``.
        """
        self._stop_event.clear()
        pan_lo, pan_hi = config.TRACK_PAN_LIMITS_DEG
        tilt_lo, tilt_hi = config.TRACK_TILT_LIMITS_DEG
        last_seen = time.monotonic()
        frame_times: list[float] = []

        log.info(
            "tracking with %s (pan) + %s (tilt) only",
            config.TRACK_PAN_JOINT, config.TRACK_TILT_JOINT,
        )
        while not self._stop_event.is_set():
            now = time.monotonic()
            frame_times = [t for t in frame_times if t > now - 1.0] + [now]

            face = self._vision.detect_face()
            if face is None:
                if now - last_seen > config.TRACK_FACE_LOST_TIMEOUT_S:
                    log.info("face lost for %.0fs; ending tracking",
                             config.TRACK_FACE_LOST_TIMEOUT_S)
                    return "face_lost"
                if on_status:
                    on_status(False, len(frame_times))
                time.sleep(config.TRACK_LOOP_INTERVAL_S)
                continue

            last_seen = now
            offset_x, offset_y = face.offset_from_center
            self._correct(config.TRACK_PAN_JOINT, offset_x, pan_lo, pan_hi)
            self._correct(config.TRACK_TILT_JOINT, offset_y, tilt_lo, tilt_hi)

            if on_status:
                on_status(True, len(frame_times))
            time.sleep(config.TRACK_LOOP_INTERVAL_S)

        return "stopped"

    def _correct(self, joint: str, offset_px: float, lo: float, hi: float) -> None:
        """One proportional correction on one joint, bounds enforced."""
        if abs(offset_px) < config.TRACK_DEADZONE_PX:
            return
        current: Optional[float] = self._motion.arm.get_angle(joint)
        if current is None:
            return  # joint not engaged; tracking cannot use it
        step = clamp(
            offset_px * config.TRACK_GAIN_DEG_PER_PX,
            -config.TRACK_MAX_STEP_DEG,
            config.TRACK_MAX_STEP_DEG,
        )
        target = clamp(current + step, lo, hi)
        self._motion.nudge_joint(joint, target - current)


if __name__ == "__main__":
    # Standalone test: engages nothing itself - requires a calibrated,
    # engaged arm, so run through main.py or engage via calibrate first.
    from arm import Arm
    from debug import StatusLine

    arm = Arm()
    motion = MotionController(arm)
    if not arm.all_engaged():
        raise SystemExit(
            "Arm is not engaged. Run main.py (or calibrate.py) first so the "
            "arm is powered at a known pose - track.py never engages servos."
        )
    vision = Vision()
    status = StatusLine()
    tracker = FaceTracker(motion, vision)
    try:
        reason = tracker.run(
            on_status=lambda tracking, fps: status.update(
                state="TRACKING" if tracking else "SEARCHING", fps=fps
            )
        )
        print(f"\nTracking ended: {reason}")
    except KeyboardInterrupt:
        print("\nTracking interrupted.")
    finally:
        vision.release()
