"""VOLT robot - animated OLED face (0.96" SSD1306 over I2C).

VOLT's eyes, rebuilt around the animation engine from an open-source
robot-dog firmware whose face work was too charming not to borrow:

- **Frame-based faces.** Every expression is a list of frames played at
  its own FPS in one of three modes: LOOP (repeat forever), ONCE (play
  and hold the last frame), or BOOMERANG (ping-pong back and forth).
- **A living idle.** While idle, the eyes "breathe" (a slow boomerang
  squash), blink at a *random* 3-7 s interval, and 30% of blinks are
  followed by a quick second blink 120-220 ms later - the double-blink
  is what makes it read as alive instead of metronomic.

Instead of PROGMEM bitmaps, frames here are procedural PIL drawings of
big rounded-rectangle eyes (Cozmo-style), so they scale to any display
size and each expression is a few lines of geometry, not a hex table.

All drawing happens on a single animator thread; public methods only
swap which face is active, so they are safe to call from anywhere. The
public API is unchanged from the previous oled.py - main.py, calibrate.py,
shutdown.py and debug.py need no edits.

If the display or its driver is unavailable, :func:`create_eyes` returns
a :class:`NullEyes` that logs instead of drawing.
"""

from __future__ import annotations

import enum
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Tuple

import config
from utils import get_logger

try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
except ImportError:  # pragma: no cover
    i2c = canvas = ssd1306 = None

log = get_logger("oled")

# ---------------------------------------------------------------------------
# Face geometry (fractions of display size - no absolute pixels)
# ---------------------------------------------------------------------------

_EYE_WIDTH_FRAC = 0.20      # each eye's width as a fraction of screen width
_EYE_HEIGHT_FRAC = 0.52     # full-open eye height as a fraction of screen height
_EYE_GAP_FRAC = 0.14        # gap between the eyes
_EYE_RADIUS_FRAC = 0.38     # corner radius as a fraction of eye width
_CAPTION_MARGIN_PX = 12     # caption baseline offset from the bottom edge

# Animation feel
_BREATHE_OPENNESS = (1.0, 0.97, 0.93, 0.90)   # boomerang squash for idle
_BLINK_OPENNESS = (0.65, 0.30, 0.06, 0.30, 0.65)  # ONCE, then face restores
_BOOT_STEPS = 9             # frames in the wake-up eye-open
_BREATHE_FPS = 4
_BLINK_FPS = 18
_BOOT_FPS = 14
_DOTS_FPS = 3
_SLEEP_FPS = 1
_STATIC_FPS = 1
_ANIMATOR_TICK_S = 0.02     # animator thread wake interval

DrawFn = Callable[["object", int, int], None]  # (draw, width, height)


class FaceMode(enum.Enum):
    LOOP = "loop"
    ONCE = "once"
    BOOMERANG = "boomerang"


@dataclass
class Face:
    """A named expression: frames + playback speed + playback mode."""

    name: str
    frames: List[DrawFn]
    fps: float
    mode: FaceMode = FaceMode.LOOP
    caption: str = ""

    finished: bool = field(default=False, compare=False)


# ---------------------------------------------------------------------------
# Frame builders (each returns a DrawFn closure)
# ---------------------------------------------------------------------------

def _eye_boxes(
    width: int,
    height: int,
    openness: float = 1.0,
    dx: int = 0,
    dy: int = 0,
    right_scale: float = 1.0,
) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """Bounding boxes for the two eyes, squashed vertically by ``openness``."""
    eye_w = int(width * _EYE_WIDTH_FRAC)
    eye_h = max(2, int(height * _EYE_HEIGHT_FRAC * openness))
    gap = int(width * _EYE_GAP_FRAC)
    cy = height // 2 + dy
    cx_left = width // 2 - gap // 2 - eye_w // 2 + dx
    cx_right = width // 2 + gap // 2 + eye_w // 2 + dx
    right_h = max(2, int(eye_h * right_scale))
    left = (cx_left - eye_w // 2, cy - eye_h // 2, cx_left + eye_w // 2, cy + eye_h // 2)
    right = (cx_right - eye_w // 2, cy - right_h // 2, cx_right + eye_w // 2, cy + right_h // 2)
    return left, right


def _rounded_eye(draw: object, box: Tuple[int, int, int, int]) -> None:
    radius = max(1, int((box[2] - box[0]) * _EYE_RADIUS_FRAC))
    radius = min(radius, (box[3] - box[1]) // 2)  # never exceed half height
    try:
        draw.rounded_rectangle(box, radius=radius, fill="white")
    except AttributeError:  # Pillow < 8.2: fall back to plain ovals
        draw.ellipse(box, fill="white")


def _neutral(openness: float = 1.0, dx: int = 0, dy: int = 0) -> DrawFn:
    """Both eyes open (or squashed), optionally glancing (dx) or bobbing (dy)."""

    def frame(draw: object, width: int, height: int) -> None:
        left, right = _eye_boxes(width, height, openness, dx=dx, dy=dy)
        _rounded_eye(draw, left)
        _rounded_eye(draw, right)

    return frame


def _crescent(up: bool) -> DrawFn:
    """Happy (crescents opening down = ∩) or sad (opening up = ∪) eyes,
    carved by overdrawing a black ellipse on a full eye."""

    def frame(draw: object, width: int, height: int) -> None:
        left, right = _eye_boxes(width, height)
        for box in (left, right):
            draw.ellipse(box, fill="white")
            eye_h = box[3] - box[1]
            shift = int(eye_h * 0.45) * (1 if up else -1)
            draw.ellipse(
                (box[0] - 2, box[1] + shift, box[2] + 2, box[3] + shift),
                fill="black",
            )

    return frame


def _confused_frame(draw: object, width: int, height: int) -> None:
    """One eye normal, one squinting, raised brow, floating '?'."""
    left, right = _eye_boxes(width, height, right_scale=0.55)
    _rounded_eye(draw, left)
    _rounded_eye(draw, right)
    draw.line(
        (right[0] - 2, right[1] - 6, right[2] + 2, right[1] - 10),
        fill="white",
        width=2,
    )
    draw.text((right[2] + 4, max(0, right[1] - 14)), "?", fill="white")


def _sleeping(z_step: int) -> DrawFn:
    """Closed-line eyes plus drifting z z z."""

    def frame(draw: object, width: int, height: int) -> None:
        left, right = _eye_boxes(width, height, openness=0.06)
        for box in (left, right):
            cy = (box[1] + box[3]) // 2
            draw.line((box[0], cy, box[2], cy), fill="white", width=3)
        for i in range(3):
            phase = (i + z_step) % 3
            x = width - 26 + i * 8
            y = 18 - phase * 5
            draw.text((x, y), "z", fill="white")

    return frame


def _with_dots(base: DrawFn, active_dot: int, caption: str = "") -> DrawFn:
    """Base face plus a pulsing three-dot progress row (listening/thinking)."""

    def frame(draw: object, width: int, height: int) -> None:
        base(draw, width, height)
        cy = height - _CAPTION_MARGIN_PX + 4
        for i in range(3):
            x = width // 2 - 12 + i * 12
            if i == active_dot:
                draw.ellipse((x - 3, cy - 3, x + 3, cy + 3), fill="white")
            else:
                draw.ellipse((x - 2, cy - 2, x + 2, cy + 2), outline="white")

    return frame


def _with_caption(base: DrawFn, caption: str) -> DrawFn:
    def frame(draw: object, width: int, height: int) -> None:
        base(draw, width, height)
        draw.text((4, height - _CAPTION_MARGIN_PX), caption, fill="white")

    return frame


def _with_viewfinder(base: DrawFn) -> DrawFn:
    """Base face plus camera-style corner brackets (tracking)."""

    def frame(draw: object, width: int, height: int) -> None:
        base(draw, width, height)
        arm = 7
        for x, y, sx, sy in (
            (1, 1, 1, 1),
            (width - 2, 1, -1, 1),
            (1, height - 2, 1, -1),
            (width - 2, height - 2, -1, -1),
        ):
            draw.line((x, y, x + arm * sx, y), fill="white")
            draw.line((x, y, x, y + arm * sy), fill="white")

    return frame


def _text_frame(line1: str, line2: str) -> DrawFn:
    def frame(draw: object, width: int, height: int) -> None:
        draw.text((4, height // 2 - 14), line1, fill="white")
        if line2:
            draw.text((4, height // 2 + 2), line2, fill="white")

    return frame


def _build_faces() -> dict:
    """The face library - VOLT's whole emotional range in one place."""
    breathe = [_neutral(openness) for openness in _BREATHE_OPENNESS]
    blink = [_neutral(openness) for openness in _BLINK_OPENNESS]
    boot = [
        _neutral(openness=max(0.05, i / (_BOOT_STEPS - 1)))
        for i in range(_BOOT_STEPS)
    ]
    glance = [_neutral(dx=d) for d in (0, 4, 7, 7, 4, 0, -4, -7, -7, -4)]
    return {
        "neutral": Face("neutral", [_neutral()], _STATIC_FPS),
        "idle_breathe": Face(
            "idle_breathe", breathe, _BREATHE_FPS, FaceMode.BOOMERANG
        ),
        "idle_blink": Face("idle_blink", blink, _BLINK_FPS, FaceMode.ONCE),
        "idle_glance": Face("idle_glance", glance, 8, FaceMode.ONCE),
        "boot": Face("boot", boot, _BOOT_FPS, FaceMode.ONCE),
        "happy": Face(
            "happy",
            [_crescent(up=False), _neutral(openness=0.9), _crescent(up=False)],
            2,
            FaceMode.BOOMERANG,
        ),
        "sad": Face("sad", [_crescent(up=True)], _STATIC_FPS),
        "confused": Face("confused", [_confused_frame], _STATIC_FPS),
        "sleeping": Face(
            "sleeping", [_sleeping(step) for step in range(3)], _SLEEP_FPS
        ),
        "listening": Face(
            "listening",
            [_with_dots(_neutral(dy=-3), dot) for dot in range(3)],
            _DOTS_FPS,
        ),
        "thinking": Face(
            "thinking",
            [_with_dots(_neutral(dx=6, dy=-4, openness=0.85), dot) for dot in range(3)],
            _DOTS_FPS,
        ),
        "tracking": Face(
            "tracking",
            [_with_viewfinder(_neutral(openness=o)) for o in (1.0, 0.94)],
            2,
            FaceMode.BOOMERANG,
        ),
        "calibrating": Face(
            "calibrating",
            [_with_caption(_neutral(openness=o), "calibrating...") for o in (1.0, 0.93)],
            2,
            FaceMode.BOOMERANG,
        ),
    }


# ---------------------------------------------------------------------------
# The animated display
# ---------------------------------------------------------------------------

class Eyes:
    """SSD1306-backed animated face with a living idle mode."""

    def __init__(self) -> None:
        if ssd1306 is None:
            raise RuntimeError("luma.oled is not installed. Run: pip3 install luma.oled")
        serial = i2c(port=config.OLED_I2C_PORT, address=config.OLED_I2C_ADDRESS)
        self._device = ssd1306(
            serial, width=config.OLED_WIDTH, height=config.OLED_HEIGHT
        )
        self._faces = _build_faces()
        self._lock = threading.Lock()
        self._current: Face = self._faces["neutral"]
        self._frame_index = 0
        self._direction = 1
        self._last_frame_at = 0.0

        # Idle personality state (mirrors the dog firmware's idle scheduler)
        self._idle_active = False
        self._idle_interlude = False   # a blink/glance is interrupting breathing
        self._next_idle_event_at = 0.0
        self._double_blink_pending = False

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        log.info("OLED attached at 0x%02X; animator running", config.OLED_I2C_ADDRESS)

    # -- face switching ----------------------------------------------------

    def _set_face(self, name: str) -> None:
        with self._lock:
            face = self._faces[name]
            if face is self._current and face.mode is not FaceMode.ONCE:
                return
            self._current = face
            self._frame_index = 0
            self._direction = 1
            self._last_frame_at = 0.0
            face.finished = False

    def _set_text_face(self, line1: str, line2: str) -> None:
        with self._lock:
            self._current = Face(
                "text", [_text_frame(line1, line2)], _STATIC_FPS
            )
            self._frame_index = 0
            self._last_frame_at = 0.0

    # -- public API (unchanged names) ---------------------------------------

    def open_eyes(self) -> None:
        self._set_face("neutral")

    def happy(self) -> None:
        self._set_face("happy")

    def sad(self) -> None:
        self._set_face("sad")

    def confused(self) -> None:
        self._set_face("confused")

    def sleeping(self) -> None:
        self._set_face("sleeping")

    def listening(self) -> None:
        self._set_face("listening")

    def thinking(self) -> None:
        self._set_face("thinking")

    def tracking(self) -> None:
        self._set_face("tracking")

    def calibrating(self) -> None:
        self._set_face("calibrating")

    def shutdown_face(self) -> None:
        self._set_face("sleeping")

    def blink(self) -> None:
        self._set_face("idle_blink")

    def text(self, line1: str, line2: str = "") -> None:
        self._set_text_face(line1, line2)

    def boot_animation(self) -> None:
        """Eyes open slowly - VOLT waking up. Blocks until the animation
        completes so the startup chime lands right as the eyes finish."""
        self._set_face("boot")
        deadline = time.monotonic() + (_BOOT_STEPS / _BOOT_FPS) + 1.0
        while time.monotonic() < deadline:
            with self._lock:
                if self._current.name != "boot" or self._current.finished:
                    break
            time.sleep(_ANIMATOR_TICK_S)
        self.open_eyes()

    # -- idle personality ---------------------------------------------------

    def start_idle(self) -> None:
        """Enter living-idle: breathing eyes + randomly scheduled blinks."""
        self._idle_active = True
        self._idle_interlude = False
        self._double_blink_pending = False
        self._schedule_idle_event(
            config.OLED_IDLE_BLINK_MIN_S, config.OLED_IDLE_BLINK_MAX_S
        )
        self._set_face("idle_breathe")

    def stop_idle(self) -> None:
        self._idle_active = False
        self._idle_interlude = False

    def _schedule_idle_event(self, min_s: float, max_s: float) -> None:
        self._next_idle_event_at = time.monotonic() + random.uniform(min_s, max_s)

    def _update_idle(self) -> None:
        """The dog firmware's idle scheduler: breathe, blink at random,
        sometimes double-blink, occasionally glance aside."""
        if not self._idle_active:
            return
        now = time.monotonic()

        if not self._idle_interlude:
            if now < self._next_idle_event_at:
                return
            self._idle_interlude = True
            if self._double_blink_pending:
                self._double_blink_pending = False
                self._set_face("idle_blink")
            elif random.random() < config.OLED_IDLE_GLANCE_CHANCE:
                self._set_face("idle_glance")
            else:
                if random.random() < config.OLED_DOUBLE_BLINK_CHANCE:
                    self._double_blink_pending = True
                self._set_face("idle_blink")
            return

        with self._lock:
            interlude_done = (
                self._current.mode is FaceMode.ONCE and self._current.finished
            )
        if interlude_done:
            self._idle_interlude = False
            self._set_face("idle_breathe")
            if self._double_blink_pending:
                self._schedule_idle_event(
                    config.OLED_DOUBLE_BLINK_GAP_MIN_S,
                    config.OLED_DOUBLE_BLINK_GAP_MAX_S,
                )
            else:
                self._schedule_idle_event(
                    config.OLED_IDLE_BLINK_MIN_S, config.OLED_IDLE_BLINK_MAX_S
                )

    # -- animator thread ------------------------------------------------------

    def _animate(self) -> None:
        while not self._stop.wait(_ANIMATOR_TICK_S):
            try:
                self._update_idle()
                self._tick()
            except Exception as exc:  # noqa: BLE001 - display must never crash VOLT
                log.debug("animator error: %s", exc)

    def _tick(self) -> None:
        with self._lock:
            face = self._current
            now = time.monotonic()
            if self._last_frame_at and now - self._last_frame_at < 1.0 / face.fps:
                return
            if face.mode is FaceMode.ONCE and face.finished and self._last_frame_at:
                return
            self._last_frame_at = now
            frame = face.frames[self._frame_index]
            self._advance(face)
        self._render(frame)

    def _advance(self, face: Face) -> None:
        count = len(face.frames)
        if count <= 1:
            face.finished = True
            return
        if face.mode is FaceMode.LOOP:
            self._frame_index = (self._frame_index + 1) % count
        elif face.mode is FaceMode.ONCE:
            if self._frame_index + 1 >= count:
                face.finished = True
            else:
                self._frame_index += 1
        else:  # BOOMERANG
            nxt = self._frame_index + self._direction
            if nxt >= count or nxt < 0:
                self._direction *= -1
                nxt = self._frame_index + self._direction
            self._frame_index = max(0, min(count - 1, nxt))

    def _render(self, frame: DrawFn) -> None:
        with canvas(self._device) as draw:
            frame(draw, self._device.width, self._device.height)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)


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
    eyes.boot_animation()
    print("Idle personality for 15s (watch for breathing + random blinks)...")
    eyes.start_idle()
    time.sleep(15)
    eyes.stop_idle()
    for name in ("happy", "sad", "confused", "listening", "thinking",
                 "tracking", "calibrating", "sleeping"):
        print(f"-> {name}")
        getattr(eyes, name)()
        time.sleep(2.5)
    eyes.text("Hi, I'm VOLT!")
    time.sleep(2)
