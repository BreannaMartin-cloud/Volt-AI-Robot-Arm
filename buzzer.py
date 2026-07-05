"""VOLT robot - passive buzzer tones.

Short original jingles and UI feedback tones, played over software PWM.
Like the OLED, the buzzer degrades gracefully: :func:`create_buzzer`
returns a :class:`NullBuzzer` when GPIO is unavailable so the robot never
crashes over a missing beep.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

import config
from utils import get_logger

try:
    import RPi.GPIO as GPIO
except ImportError:  # pragma: no cover
    GPIO = None

log = get_logger("buzzer")

#: Note name -> frequency in Hz. 0 means rest.
NOTE_HZ: Dict[str, int] = {
    "C4": 262, "D4": 294, "E4": 330, "F4": 349, "G4": 392, "A4": 440, "B4": 494,
    "C5": 523, "D5": 587, "E5": 659, "F5": 698, "G5": 784, "A5": 880,
    "REST": 0,
}

Song = List[Tuple[str, float]]  # (note name, duration seconds)

STARTUP_CHIME: Song = [("C4", 0.12), ("E4", 0.12), ("G4", 0.12), ("C5", 0.24)]
CONFIRM_TONE: Song = [("G4", 0.08), ("C5", 0.12)]
ERROR_TONE: Song = [("E4", 0.15), ("C4", 0.25)]
SHUTDOWN_TONE: Song = [("C5", 0.12), ("G4", 0.12), ("E4", 0.12), ("C4", 0.24)]

DANCE_SONG: Song = [
    ("C4", 0.15), ("E4", 0.15), ("G4", 0.15), ("C5", 0.25), ("REST", 0.05),
    ("G4", 0.15), ("E4", 0.15), ("C4", 0.15), ("G4", 0.25), ("REST", 0.05),
    ("A4", 0.15), ("C5", 0.15), ("A4", 0.15), ("F4", 0.3),
]

SHIMMY_SONG: Song = [
    ("E4", 0.1), ("G4", 0.1), ("E4", 0.1), ("G4", 0.1),
    ("A4", 0.1), ("G4", 0.1), ("A4", 0.1), ("G4", 0.1),
    ("F4", 0.1), ("A4", 0.1), ("F4", 0.1), ("A4", 0.1), ("E4", 0.25),
]

_PWM_DUTY_CYCLE = 50  # square wave for a passive buzzer
_PWM_INITIAL_HZ = 440


class Buzzer:
    """Passive buzzer on ``config.BUZZER_GPIO_PIN`` via software PWM."""

    def __init__(self) -> None:
        if GPIO is None:
            raise RuntimeError("RPi.GPIO is not installed. Run: pip3 install RPi.GPIO")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.BUZZER_GPIO_PIN, GPIO.OUT)
        self._pwm = GPIO.PWM(config.BUZZER_GPIO_PIN, _PWM_INITIAL_HZ)
        self._active = False
        log.info("buzzer attached on GPIO %d", config.BUZZER_GPIO_PIN)

    def play_song(self, song: Song) -> None:
        try:
            for note, duration in song:
                self._play_note(note, duration)
        finally:
            self._silence()

    def _play_note(self, note: str, duration: float) -> None:
        freq = NOTE_HZ.get(note, 0)
        if freq == 0:
            self._silence()
            time.sleep(duration)
            return
        if not self._active:
            self._pwm.start(_PWM_DUTY_CYCLE)
            self._active = True
        self._pwm.ChangeFrequency(freq)
        time.sleep(duration)

    def _silence(self) -> None:
        if self._active:
            self._pwm.stop()
            self._active = False

    # -- named cues --------------------------------------------------------

    def startup(self) -> None:
        self.play_song(STARTUP_CHIME)

    def confirm(self) -> None:
        self.play_song(CONFIRM_TONE)

    def error(self) -> None:
        self.play_song(ERROR_TONE)

    def shutdown(self) -> None:
        self.play_song(SHUTDOWN_TONE)

    def dance_song(self) -> None:
        self.play_song(DANCE_SONG)

    def shimmy_song(self) -> None:
        self.play_song(SHIMMY_SONG)

    def cleanup(self) -> None:
        self._silence()
        GPIO.cleanup(config.BUZZER_GPIO_PIN)


class NullBuzzer:
    """Silent stand-in when GPIO is unavailable."""

    def __getattr__(self, name: str):
        def _noop(*args: object, **kwargs: object) -> None:
            log.debug("buzzer unavailable; skipped %s", name)

        return _noop


def create_buzzer() -> "Buzzer | NullBuzzer":
    """Return a working :class:`Buzzer`, or :class:`NullBuzzer` on failure."""
    try:
        return Buzzer()
    except Exception as exc:  # noqa: BLE001
        log.warning("buzzer unavailable (%s); continuing silently", exc)
        return NullBuzzer()


if __name__ == "__main__":
    b = create_buzzer()
    b.startup()
    time.sleep(0.3)
    b.dance_song()
    time.sleep(0.3)
    b.shimmy_song()
    b.cleanup()
