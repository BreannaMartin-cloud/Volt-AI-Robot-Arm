"""VOLT robot - low-level servo control.

This module is the ONLY place in the project that talks to the PCA9685.
It does exactly three things:

1. Initialise the driver **without commanding any motion**. Until an
   angle is written to a channel, the PCA9685 outputs no pulse and the
   servo stays limp - so constructing :class:`Arm` is always safe, even
   with the arm folded on the table.
2. Apply per-joint soft limits and trim at a single write point.
3. Track and persist the last commanded logical pose.

There is deliberately no interpolation, velocity limiting, or sequencing
here - that lives in ``motion.py``. Nothing outside this module may write
a servo angle directly.

Safety model
------------
Hobby servos are open-loop: they report nothing, and the moment a pulse
is applied they drive at full speed toward the commanded angle. The only
way to avoid a startup jump is to never command an angle the physical arm
isn't already at. :class:`Arm` therefore keeps every joint *disengaged*
(no pulse) until :meth:`engage_joint` is explicitly called with a starting
angle chosen by a human or by trusted persisted state.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

import config
from utils import clamp, get_logger

try:
    from adafruit_servokit import ServoKit
except ImportError:  # pragma: no cover - allows import on dev machines
    ServoKit = None

log = get_logger("arm")


class Arm:
    """Low-level interface to the six arm servos.

    Construction attaches the PCA9685 but commands **no motion** and
    applies **no pulse** to any channel.
    """

    def __init__(self) -> None:
        if ServoKit is None:
            raise RuntimeError(
                "adafruit_servokit is not installed. "
                "Run: pip3 install adafruit-circuitpython-servokit"
            )

        problems = config.validate()
        if problems:
            raise RuntimeError("config.py is invalid: " + "; ".join(problems))

        self._kit = ServoKit(
            channels=config.PCA9685_CHANNEL_COUNT,
            address=config.PCA9685_I2C_ADDRESS,
        )
        for joint, channel in config.SERVO_CHANNELS.items():
            self._kit.servo[channel].set_pulse_width_range(
                config.SERVO_MIN_PULSE_US, config.SERVO_MAX_PULSE_US
            )

        #: Logical angle of each joint, or None while the true position is
        #: unknown. Only ever a number after the joint has been engaged.
        self._angles: Dict[str, Optional[float]] = {j: None for j in config.JOINT_ORDER}
        #: Joints currently receiving a hold pulse.
        self._engaged: Dict[str, bool] = {j: False for j in config.JOINT_ORDER}

        self._last_known = self._load_state()
        log.info(
            "PCA9685 attached at 0x%02X; all joints disengaged (no pulse)",
            config.PCA9685_I2C_ADDRESS,
        )

    # ------------------------------------------------------------------
    # Engagement
    # ------------------------------------------------------------------

    def engage_joint(self, joint: str, angle: float) -> None:
        """Apply power to one servo at ``angle`` (logical degrees).

        This is the moment the servo starts moving toward ``angle`` from
        wherever it physically is - the one motion this module cannot make
        smooth, because the true starting position is unknowable. Callers
        (calibrate.py, main.py) are responsible for warning the user and
        choosing a sensible ``angle`` first.
        """
        self._require_joint(joint)
        self._write(joint, angle)
        if not self._engaged[joint]:
            self._engaged[joint] = True
            log.info("engaged %s at %.0f deg", joint, self._angles[joint])

    def is_engaged(self, joint: str) -> bool:
        self._require_joint(joint)
        return self._engaged[joint]

    def all_engaged(self) -> bool:
        return all(self._engaged.values())

    def release_all(self) -> None:
        """Drop the hold pulse on every joint, letting the arm go limp.

        MANUAL USE ONLY. Power management policy for this robot is that
        holding torque is never dropped automatically - the arm must
        already be in ``SAFE_SHUTDOWN_POSE`` (resting on the table) when
        this is called, otherwise gravity takes the arm down hard.
        """
        for joint, channel in config.SERVO_CHANNELS.items():
            self._kit.servo[channel].angle = None
            self._engaged[joint] = False
        log.warning("all joints released - arm is limp")

    # ------------------------------------------------------------------
    # Angle I/O
    # ------------------------------------------------------------------

    def set_angle(self, joint: str, angle: float) -> float:
        """Command one engaged joint to a logical angle, immediately.

        Returns the angle actually commanded after soft-limit clamping.
        Raises if the joint has not been engaged - a disengaged joint has
        an unknown position and must go through :meth:`engage_joint`.

        This is a raw, unprofiled write; anything user-facing should go
        through motion.py so velocity/acceleration limits apply.
        """
        self._require_joint(joint)
        if not self._engaged[joint]:
            raise RuntimeError(
                f"joint '{joint}' is not engaged; call engage_joint() first"
            )
        return self._write(joint, angle)

    def get_angle(self, joint: str) -> Optional[float]:
        """Last commanded logical angle, or None if never engaged."""
        self._require_joint(joint)
        return self._angles[joint]

    def get_pose(self) -> Dict[str, Optional[float]]:
        """Last commanded logical angle for every joint."""
        return dict(self._angles)

    @property
    def last_known_pose(self) -> Optional[Dict[str, float]]:
        """Pose persisted by a previous run, if one was recorded.

        Trustworthy only if servo power has been maintained since that
        run; after a power cycle the arm has sagged to its mechanical
        rest and this pose is stale.
        """
        return dict(self._last_known) if self._last_known else None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _require_joint(joint: str) -> None:
        if joint not in config.SERVO_CHANNELS:
            raise KeyError(
                f"unknown joint '{joint}'; valid joints: {config.JOINT_ORDER}"
            )

    def _write(self, joint: str, angle: float) -> float:
        """Single hardware write point: clamp, trim, command, record."""
        lo, hi = config.SOFT_LIMITS_DEG[joint]
        logical = clamp(float(angle), lo, hi)
        hw_angle = clamp(
            logical + config.SERVO_TRIM_DEG[joint],
            config.SERVO_HW_MIN_DEG,
            config.SERVO_HW_MAX_DEG,
        )
        self._kit.servo[config.SERVO_CHANNELS[joint]].angle = hw_angle
        self._angles[joint] = logical
        return logical

    # ------------------------------------------------------------------
    # Pose persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> Optional[Dict[str, float]]:
        try:
            with open(config.STATE_FILE_PATH, encoding="utf-8") as fh:
                saved = json.load(fh)
        except (FileNotFoundError, ValueError):
            return None
        if not all(joint in saved for joint in config.JOINT_ORDER):
            log.warning("state file %s is incomplete; ignoring", config.STATE_FILE_PATH)
            return None
        return {joint: float(saved[joint]) for joint in config.JOINT_ORDER}

    def save_state(self) -> None:
        """Persist the current pose (called by motion.py after moves)."""
        if not self.all_engaged():
            return  # a partial pose is not worth trusting later
        tmp_path = config.STATE_FILE_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(self._angles, fh)
            os.replace(tmp_path, config.STATE_FILE_PATH)
        except OSError as exc:  # persistence is best-effort
            log.debug("could not save state: %s", exc)
