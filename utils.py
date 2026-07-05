"""VOLT robot - shared utilities.

Logging setup, the robot state machine enum, and small pure helpers used
across modules. Nothing in here touches hardware.
"""

from __future__ import annotations

import enum
import logging
import threading
from typing import Optional

import config


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with the project-wide format/level."""
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, config.LOG_LEVEL, logging.INFO),
            format=config.LOG_FORMAT,
        )
    return logger


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into the inclusive range [lo, hi]."""
    return max(lo, min(hi, value))


class RobotState(enum.Enum):
    """Top-level robot state machine.

    Exactly one state is active at a time. Subsystems (voice, tracking,
    motion, personality animations) may only act when the state machine
    grants them the floor - this is what stops face tracking, dancing,
    and voice commands from fighting over the servos.
    """

    BOOTING = "booting"
    READY = "ready"
    CALIBRATING = "calibrating"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    TRACKING_FACE = "tracking_face"
    SEARCHING = "searching"
    GRABBING = "grabbing"
    DANCING = "dancing"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"


class StateMachine:
    """Thread-safe holder for the current :class:`RobotState`.

    Transitions are logged so a session transcript reads as a timeline of
    what the robot believed it was doing.
    """

    def __init__(self, initial: RobotState = RobotState.BOOTING) -> None:
        self._state = initial
        self._lock = threading.Lock()
        self._log = get_logger("state")

    @property
    def state(self) -> RobotState:
        with self._lock:
            return self._state

    def transition(self, new_state: RobotState) -> RobotState:
        """Move to ``new_state``, returning the previous state."""
        with self._lock:
            previous, self._state = self._state, new_state
        if previous is not new_state:
            self._log.info("%s -> %s", previous.value, new_state.value)
        return previous

    def is_in(self, *states: RobotState) -> bool:
        return self.state in states


class HardwareUnavailableError(RuntimeError):
    """Raised when a required hardware dependency is missing or failed."""

    def __init__(self, subsystem: str, detail: Optional[str] = None) -> None:
        message = f"{subsystem} unavailable"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)
        self.subsystem = subsystem
