"""VOLT robot - high-level motion control.

Everything that *moves* the arm goes through this module. It wraps the
low-level :class:`arm.Arm` with:

- **Trapezoidal velocity profiles** - every move accelerates at no more
  than ``MAX_ACCEL_DEG_S2`` up to at most ``MAX_VELOCITY_DEG_S``, then
  decelerates symmetrically. No servo is ever stepped instantaneously to
  a distant angle.
- **Coordinated multi-joint moves** - all joints follow the same profile
  scaled to their own displacement, so they arrive together.
- **A motion lock** - only one behavior (voice command, tracking,
  breathing animation) may drive the arm at a time.
- **Pose/sequence helpers** - home, idle, safe-shutdown, gestures.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Dict, Iterable

import config
from arm import Arm
from utils import clamp, get_logger

log = get_logger("motion")


class MotionController:
    """Profiled, coordinated movement on top of :class:`arm.Arm`."""

    def __init__(self, arm: Arm) -> None:
        self.arm = arm
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Engagement (startup)
    # ------------------------------------------------------------------

    def engage_at_pose(self, pose: Dict[str, float]) -> None:
        """Power every joint at the angles in ``pose``.

        The one unavoidable open-loop jump happens here: each servo snaps
        from its unknown physical position to ``pose``. Callers must have
        warned the user and chosen ``pose`` to be as close as possible to
        where the arm truly is (last persisted pose if power was held,
        SAFE_SHUTDOWN_POSE if it was resting on the table).
        """
        with self._lock:
            for joint in config.JOINT_ORDER:
                self.arm.engage_joint(joint, pose[joint])
            self.arm.save_state()

    # ------------------------------------------------------------------
    # Profiled moves
    # ------------------------------------------------------------------

    def move_to_pose(
        self,
        pose: Dict[str, float],
        cautious: bool = False,
    ) -> None:
        """Move all engaged joints to ``pose`` along one shared profile.

        ``cautious=True`` uses the slower calibration-grade velocity and
        acceleration limits; use it for the first move after engagement
        and any move commanded while confidence in position is low.
        """
        with self._lock:
            self._stop_event.clear()
            targets = self._clamped_targets(pose)
            starts = {j: self.arm.get_angle(j) for j in targets}
            missing = [j for j, a in starts.items() if a is None]
            if missing:
                raise RuntimeError(f"cannot move disengaged joints: {missing}")

            distance = max(abs(targets[j] - starts[j]) for j in targets)
            if distance < 0.5:
                return

            v_max = config.CAUTIOUS_VELOCITY_DEG_S if cautious else config.MAX_VELOCITY_DEG_S
            a_max = config.CAUTIOUS_ACCEL_DEG_S2 if cautious else config.MAX_ACCEL_DEG_S2
            self._run_profile(starts, targets, distance, v_max, a_max)
            self.arm.save_state()

    def move_joint(self, joint: str, angle: float, cautious: bool = False) -> None:
        """Profiled move of a single joint; no other joint is written."""
        current = self.arm.get_angle(joint)
        if current is None:
            raise RuntimeError(f"joint '{joint}' is not engaged")
        self.move_to_pose({joint: angle}, cautious=cautious)

    def nudge_joint(self, joint: str, delta: float) -> float:
        """Small direct step, used by tracking and breathing.

        Bounded to ``TRACK_MAX_STEP_DEG`` per call so even a misbehaving
        caller cannot command a large instantaneous jump. Returns the
        commanded angle.
        """
        current = self.arm.get_angle(joint)
        if current is None:
            raise RuntimeError(f"joint '{joint}' is not engaged")
        delta = clamp(delta, -config.TRACK_MAX_STEP_DEG, config.TRACK_MAX_STEP_DEG)
        with self._lock:
            return self.arm.set_angle(joint, current + delta)

    def stop(self) -> None:
        """Abort the profile loop at the next control tick.

        The arm holds wherever it is - holding torque is never dropped.
        """
        self._stop_event.set()

    def _run_profile(
        self,
        starts: Dict[str, float],
        targets: Dict[str, float],
        distance: float,
        v_max: float,
        a_max: float,
    ) -> None:
        """Trapezoidal (or triangular) profile over the largest displacement."""
        t_ramp = v_max / a_max
        d_ramp = 0.5 * a_max * t_ramp**2

        if 2 * d_ramp >= distance:  # never reaches v_max: triangular profile
            t_ramp = math.sqrt(distance / a_max)
            total_time = 2 * t_ramp
            v_peak = a_max * t_ramp
        else:
            t_cruise = (distance - 2 * d_ramp) / v_max
            total_time = 2 * t_ramp + t_cruise
            v_peak = v_max

        dt = 1.0 / config.CONTROL_LOOP_HZ
        start_time = time.monotonic()
        while True:
            if self._stop_event.is_set():
                log.warning("motion stopped mid-profile; holding position")
                return
            t = time.monotonic() - start_time
            if t >= total_time:
                break
            travelled = self._profile_distance(t, total_time, t_ramp, v_peak, a_max)
            fraction = travelled / distance
            for joint, target in targets.items():
                self.arm.set_angle(joint, starts[joint] + (target - starts[joint]) * fraction)
            time.sleep(dt)

        for joint, target in targets.items():  # land exactly on target
            self.arm.set_angle(joint, target)

    @staticmethod
    def _profile_distance(
        t: float, total_time: float, t_ramp: float, v_peak: float, a_max: float
    ) -> float:
        """Distance travelled at time ``t`` along the trapezoid."""
        if t < t_ramp:  # accelerating
            return 0.5 * a_max * t**2
        if t < total_time - t_ramp:  # cruising
            return 0.5 * a_max * t_ramp**2 + v_peak * (t - t_ramp)
        remaining = total_time - t  # decelerating
        return (
            0.5 * a_max * t_ramp**2
            + v_peak * (total_time - 2 * t_ramp)
            + (0.5 * a_max * t_ramp**2 - 0.5 * a_max * remaining**2)
        )

    @staticmethod
    def _clamped_targets(pose: Dict[str, float]) -> Dict[str, float]:
        targets: Dict[str, float] = {}
        for joint, angle in pose.items():
            lo, hi = config.SOFT_LIMITS_DEG[joint]
            targets[joint] = clamp(float(angle), lo, hi)
        return targets

    # ------------------------------------------------------------------
    # Named poses and gestures
    # ------------------------------------------------------------------

    @staticmethod
    def _arm_only(pose: Dict[str, float]) -> Dict[str, float]:
        """A pose with the gripper left out.

        Home/idle returns must never change the grip: the post-command
        return-to-idle used to command the gripper back to its pose value,
        prying the jaws half-open around a just-grabbed object. Gripper
        state changes ONLY via open/close/grab/release.
        """
        return {j: a for j, a in pose.items() if j != "gripper"}

    def go_home(self, cautious: bool = False) -> None:
        self.move_to_pose(self._arm_only(config.HOME_POSE), cautious=cautious)

    def go_idle(self, cautious: bool = False) -> None:
        self.move_to_pose(self._arm_only(config.IDLE_POSE), cautious=cautious)

    def go_safe_shutdown(self) -> None:
        """Fold to the shutdown pose, always cautiously (gripper untouched,
        in case it is holding something when shutdown is called)."""
        self.move_to_pose(self._arm_only(config.SAFE_SHUTDOWN_POSE), cautious=True)

    def open_gripper(self) -> None:
        self.move_joint("gripper", config.GRIPPER_OPEN_DEG)

    def close_gripper(self) -> None:
        self.move_joint("gripper", config.GRIPPER_CLOSED_DEG)

    def run_sequence(
        self,
        sequence: Iterable[Dict[str, float]],
        pause_between_s: float = 0.2,
    ) -> None:
        """Play a list of poses through the profiler, stoppable between steps.

        Gripper values in sequence poses are ignored (same policy as
        go_home/go_idle): an emote must never loosen a held object.
        """
        for pose in sequence:
            if self._stop_event.is_set():
                return
            self.move_to_pose(self._arm_only(pose), cautious=True)
            time.sleep(pause_between_s)

    def wave(self) -> None:
        self.run_sequence(config.WAVE_SEQUENCE)
        self.go_idle()

    def dance(self) -> None:
        self.run_sequence(config.DANCE_SEQUENCE)
        self.go_idle()

    def shimmy(self) -> None:
        self.run_sequence(config.SHIMMY_SEQUENCE, pause_between_s=0.1)
        self.go_idle()

    def grab(self) -> None:
        """Gripper-only grab: open, pause, close. Done.

        Deliberately NO arm motion and NO vision - the arm holds whatever
        pose it is in and only the jaws move, so the mechanics can be
        verified in isolation. Vision-guided pick-and-place (find object,
        move above, lower, close, lift) comes later, on top of this.
        """
        self.open_gripper()
        time.sleep(config.GRAB_OPEN_PAUSE_S)
        self.close_gripper()

    def release(self) -> None:
        """Gripper-only release: open. Done. (See grab() for why.)"""
        self.open_gripper()

    # ------------------------------------------------------------------
    # Idle breathing animation
    # ------------------------------------------------------------------

    def breathe_once(self, phase: float) -> None:
        """One breathing tick: tiny sinusoidal offset on the configured joint.

        Called repeatedly from the idle loop with an advancing ``phase``
        (seconds). Skips silently if the arm is busy - personality never
        preempts a real command.
        """
        if not config.IDLE_BREATHING_ENABLED:
            return
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return
        try:
            joint = config.IDLE_BREATHING_JOINT
            center = config.IDLE_POSE[joint]
            offset = config.IDLE_BREATHING_AMPLITUDE_DEG * math.sin(
                2 * math.pi * phase / config.IDLE_BREATHING_PERIOD_S
            )
            self.arm.set_angle(joint, center + offset)
        finally:
            self._lock.release()
