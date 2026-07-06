"""VOLT robot - diagnostics.

    python3 debug.py

Read-only health report: verifies configuration, probes every hardware
subsystem, and prints servo angles / trims / limits / engagement, the
persisted pose, and camera frame rate. Commands NO motion and applies
NO servo pulse - safe to run at any time, in any arm position.

Also provides :class:`StatusLine`, the single-line live console readout
used by track.py.
"""

from __future__ import annotations

import time
from typing import Dict, List

import config
from utils import get_logger

log = get_logger("debug")


class StatusLine:
    """Throttled, overwriting one-line console status (FPS, state, etc.)."""

    def __init__(self, print_interval_s: float = 0.2) -> None:
        self._interval = print_interval_s
        self._last_print = 0.0

    def update(self, **fields: object) -> None:
        now = time.monotonic()
        if now - self._last_print < self._interval:
            return
        self._last_print = now
        line = " | ".join(f"{key}: {value}" for key, value in fields.items())
        print("\r" + line + " " * 10, end="", flush=True)

    def newline(self) -> None:
        print()


def _section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 50 - len(title)))


def check_config() -> List[str]:
    _section("Configuration")
    import calibration

    applied = calibration.apply()
    problems = config.validate()
    if problems:
        for problem in problems:
            print(f"  FAIL  {problem}")
    else:
        print("  ok    config.validate() passed")
    print(f"  info  calibration.json {'loaded' if applied else 'not found (factory defaults)'}")
    print(f"  info  CALIBRATED = {config.CALIBRATED}")
    print(f"  info  channels   = {config.SERVO_CHANNELS}")
    print(f"  info  unused     = {config.UNUSED_CHANNELS}")
    return problems


def check_servos() -> None:
    _section("Servos (PCA9685)")
    try:
        from arm import Arm

        arm = Arm()
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  PCA9685: {exc}")
        return
    print(f"  ok    PCA9685 attached at 0x{config.PCA9685_I2C_ADDRESS:02X} "
          "(no pulse commanded)")

    print(f"\n  {'joint':<12} {'channel':>7} {'trim':>6} {'limits':>12} {'last known':>11}")
    last_known: Dict[str, float] = arm.last_known_pose or {}
    for joint in config.JOINT_ORDER:
        known = last_known.get(joint)
        print(
            f"  {joint:<12} {config.SERVO_CHANNELS[joint]:>7} "
            f"{config.SERVO_TRIM_DEG[joint]:>+6d} "
            f"{str(config.SOFT_LIMITS_DEG[joint]):>12} "
            f"{('-' if known is None else f'{known:.0f}'):>11}"
        )
    if last_known:
        print("\n  note  'last known' is from the state file and is only valid\n"
              "        if servo power has been maintained since that run.")


def check_oled() -> None:
    _section("OLED")
    from oled import NullEyes, create_eyes

    eyes = create_eyes()
    if isinstance(eyes, NullEyes):
        print("  FAIL  OLED not reachable (see log above)")
        return
    eyes.text("VOLT debug", "display ok")
    print(f"  ok    SSD1306 at 0x{config.OLED_I2C_ADDRESS:02X}")


def check_buzzer() -> None:
    _section("Buzzer")
    from buzzer import NullBuzzer, create_buzzer

    buzzer = create_buzzer()
    if isinstance(buzzer, NullBuzzer):
        print("  FAIL  buzzer not reachable (see log above)")
        return
    buzzer.confirm()
    buzzer.cleanup()
    print(f"  ok    tone played on GPIO {config.BUZZER_GPIO_PIN}")


def check_camera() -> None:
    _section("Camera")
    try:
        from vision import Vision

        vision = Vision()
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  camera: {exc}")
        return
    fallback = (vision.active_width, vision.active_height) != (
        config.CAMERA_WIDTH, config.CAMERA_HEIGHT
    )
    print(f"  Device: {config.CAMERA_INDEX}")
    print(f"  Resolution: {vision.active_width}x{vision.active_height}"
          + (f"  (fell back from {config.CAMERA_WIDTH}x{config.CAMERA_HEIGHT})"
             if fallback else ""))
    print(f"  FPS: {vision.active_fps:.1f}  (target {config.CAMERA_FPS})")
    print(f"  Rotation: {config.CAMERA_ROTATION}\N{DEGREE SIGN}")
    print(f"  Horizontal Flip: {config.CAMERA_FLIP_HORIZONTAL}")
    print(f"  Vertical Flip: {config.CAMERA_FLIP_VERTICAL}")
    face = vision.detect_face()
    print(f"  info  face detection: {'face seen' if face else 'no face in view'}")
    vision.release()


def check_voice() -> None:
    _section("Voice")
    try:
        from wake import PhraseRecognizer, build_grammar

        PhraseRecognizer()
        print(f"  ok    Vosk model at {config.VOSK_MODEL_PATH}")
        print(f"  info  grammar: {build_grammar()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  voice: {exc}")


def main() -> None:
    print("VOLT diagnostics - read-only, no servo will move.")
    check_config()
    check_servos()
    check_oled()
    check_buzzer()
    check_camera()
    check_voice()
    print("\nDone.")


if __name__ == "__main__":
    main()
