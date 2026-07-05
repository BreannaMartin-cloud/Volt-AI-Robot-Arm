"""VOLT robot - OLED face (0.96" SSD1306 over I2C).

Draws VOLT's eyes and status text. Expressions are the robot's primary
"body language": every :class:`utils.RobotState` maps to a face, so a
glance at the OLED always tells you what the robot believes it is doing.

If the display or its driver is unavailable, :func:`create_eyes` returns
a :class:`NullEyes` that logs instead of drawing - the robot stays fully
functional without a screen.
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import config
from utils import get_logger

try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
except ImportError:  # pragma: no cover
    i2c = canvas = ssd1306 = None

log = get_logger("oled")

# Face geometry, derived from display size (no magic numbers at call sites)
_EYE_WIDTH_FRAC = 0.16
_EYE_HEIGHT_FRAC = 0.42
_EYE_GAP_FRAC = 0.13


class Eyes:
    """Real SSD1306-backed face."""

    def __init__(self) -> None:
        if ssd1306 is None:
            raise RuntimeError("luma.oled is not installed. Run: pip3 install luma.oled")
        serial = i2c(port=config.OLED_I2C_PORT, address=config.OLED_I2C_ADDRESS)
        self._device = ssd1306(
            serial, width=config.OLED_WIDTH, height=config.OLED_HEIGHT
        )
        self._idle_stop = threading.Event()
        self._idle_thread: Optional[threading.Thread] = None
        log.info("OLED attached at 0x%02X", config.OLED_I2C_ADDRESS)

    # -- geometry helpers ------------------------------------------------

    def _eye_boxes(self) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        w, h = self._device.width, self._device.height
        eye_w, eye_h = int(w * _EYE_WIDTH_FRAC), int(h * _EYE_HEIGHT_FRAC)
        gap = int(w * _EYE_GAP_FRAC)
        cy = h // 2
        cx1 = w // 2 - gap // 2 - eye_w // 2
        cx2 = w // 2 + gap // 2 + eye_w // 2
        box = lambda cx: (cx - eye_w // 2, cy - eye_h // 2, cx + eye_w // 2, cy + eye_h // 2)
        return box(cx1), box(cx2)

    def _caption(self, draw, text: str) -> None:
        draw.text((4, self._device.height - 12), text, fill="white")

    # -- expressions -----------------------------------------------------

    def open_eyes(self) -> None:
        left, right = self._eye_boxes()
        with canvas(self._device) as draw:
            draw.ellipse(left, fill="white")
            draw.ellipse(right, fill="white")

    def boot_animation(self) -> None:
        """Eyes open slowly from closed - VOLT waking up."""
        left, right = self._eye_boxes()
        cy = (left[1] + left[3]) // 2
        full = (left[3] - left[1]) // 2
        for step in range(1, full + 1, 2):
            with canvas(self._device) as draw:
                for box in (left, right):
                    draw.ellipse((box[0], cy - step, box[2], cy + step), fill="white")
            time.sleep(0.04)
        self.open_eyes()

    def blink(self) -> None:
        left, right = self._eye_boxes()
        cy = (left[1] + left[3]) // 2
        with canvas(self._device) as draw:
            for box in (left, right):
                draw.line((box[0], cy, box[2], cy), fill="white", width=3)
        time.sleep(0.12)
        self.open_eyes()

    def happy(self) -> None:
        left, right = self._eye_boxes()
        with canvas(self._device) as draw:
            for box in (left, right):
                draw.arc(box, start=200, end=340, fill="white", width=3)

    def sad(self) -> None:
        left, right = self._eye_boxes()
        with canvas(self._device) as draw:
            for box in (left, right):
                draw.arc(box, start=20, end=160, fill="white", width=3)

    def sleeping(self) -> None:
        left, right = self._eye_boxes()
        cy = (left[1] + left[3]) // 2
        with canvas(self._device) as draw:
            for box in (left, right):
                draw.line((box[0], cy, box[2], cy), fill="white", width=3)
            draw.text((self._device.width - 30, 6), "z z", fill="white")

    def confused(self) -> None:
        left, right = self._eye_boxes()
        with canvas(self._device) as draw:
            draw.ellipse(left, fill="white")
            shrunk = (right[0], right[1] + 6, right[2], right[3] - 6)
            draw.ellipse(shrunk, fill="white")
            draw.line(
                (right[0] - 2, right[1] - 4, right[2] + 2, right[1] - 8),
                fill="white",
                width=2,
            )
            self._caption(draw, "?")

    def calibrating(self) -> None:
        self._eyes_with_caption("calibrating...")

    def tracking(self) -> None:
        self._eyes_with_caption("tracking...")

    def listening(self) -> None:
        self._eyes_with_caption("listening...")

    def thinking(self) -> None:
        with canvas(self._device) as draw:
            draw.text(
                (self._device.width // 2 - 24, self._device.height // 2 - 4),
                "thinking...",
                fill="white",
            )

    def shutdown_face(self) -> None:
        self.sleeping()

    def _eyes_with_caption(self, caption: str) -> None:
        left, right = self._eye_boxes()
        with canvas(self._device) as draw:
            draw.ellipse(left, fill="white")
            draw.ellipse(right, fill="white")
            self._caption(draw, caption)

    def text(self, line1: str, line2: str = "") -> None:
        with canvas(self._device) as draw:
            draw.text((4, self._device.height // 2 - 14), line1, fill="white")
            if line2:
                draw.text((4, self._device.height // 2 + 2), line2, fill="white")

    # -- idle blink loop ---------------------------------------------------

    def start_idle(self) -> None:
        self.stop_idle()
        self._idle_stop.clear()
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._idle_thread.start()

    def stop_idle(self) -> None:
        self._idle_stop.set()
        if self._idle_thread is not None:
            self._idle_thread.join(timeout=1.0)
            self._idle_thread = None

    def _idle_loop(self) -> None:
        self.open_eyes()
        while not self._idle_stop.wait(config.IDLE_BLINK_INTERVAL_S):
            self.blink()


class NullEyes:
    """Drop-in stand-in when no OLED is available; logs expressions."""

    def __getattr__(self, name: str):
        def _noop(*args: object, **kwargs: object) -> None:
            log.debug("OLED unavailable; skipped %s%s", name, args or "")

        return _noop


def create_eyes() -> "Eyes | NullEyes":
    """Return working :class:`Eyes`, or :class:`NullEyes` on any failure."""
    try:
        return Eyes()
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the robot
        log.warning("OLED unavailable (%s); continuing without display", exc)
        return NullEyes()


if __name__ == "__main__":
    eyes = create_eyes()
    for name in (
        "boot_animation", "happy", "sad", "confused",
        "calibrating", "tracking", "listening", "thinking", "sleeping",
    ):
        getattr(eyes, name)()
        time.sleep(0.8)
    eyes.text("Hi, I'm VOLT!")
