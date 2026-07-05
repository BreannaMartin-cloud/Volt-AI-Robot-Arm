"""VOLT robot - interactive servo calibration.

    python3 calibrate.py

This is the ONLY entry point allowed to move servos while
``config.CALIBRATED`` is False, and the tool you use to make it True.

Startup behavior (per the safety policy):
- Attaches the PCA9685. Commands NO motion. Applies NO pulse.
- Prints "Robot Ready / Calibration Required" and waits indefinitely.

Servos stay individually disengaged until you move them: the first
command to a joint powers ONLY that joint, at exactly the angle you
typed, after a per-joint confirmation. No other servo receives a pulse.

Commands
--------
    <joint> <angle>     move one joint (engages it first if needed)
                        e.g.  base 92   elbow 64   wrist_pitch 104
    +N / -N             nudge the last-moved joint by N degrees (e.g. +2)
    trim <joint> <dN>   adjust a joint's trim by dN degrees and re-apply
    limits <joint> <lo> <hi>   set that joint's soft limits
    save [name]         print a config.py-ready pose entry for the
                        current position
    home                move all engaged joints to HOME_POSE (slow)
    idle                move all engaged joints to IDLE_POSE (slow)
    status              show angles / trims / limits / engagement
    shutdown            fold to SAFE_SHUTDOWN_POSE, wait, exit
    help                this text
    quit                exit WITHOUT moving (servos keep holding)
"""

from __future__ import annotations

import shlex
from typing import Dict, List, Optional

import config
from arm import Arm
from motion import MotionController
from oled import create_eyes
from utils import get_logger

log = get_logger("calibrate")

#: Accepted spellings for each joint.
JOINT_ALIASES: Dict[str, str] = {
    "base": "base",
    "shoulder": "shoulder",
    "elbow": "elbow",
    "wrist_pitch": "wrist_pitch",
    "pitch": "wrist_pitch",
    "wrist_roll": "wrist_roll",
    "roll": "wrist_roll",
    "gripper": "gripper",
    "claw": "gripper",
}

_BANNER = """
============================================================
VOLT calibration

Servos are attached but NOT powered - no pulse, no movement.
With power off/idle the arm rests folded at the elbow with
the claw on the table. That is normal.

The first command you give a joint POWERS that one servo and
drives it (open-loop, from an unknown position) to the angle
you type. Keep hands clear and be ready to support the arm -
especially before the first elbow or shoulder move, since
those carry the arm's weight.

Type 'help' for commands. Nothing moves until you say so.
============================================================
"""


class CalibrationSession:
    """State for one interactive calibration run."""

    def __init__(self) -> None:
        self.arm = Arm()
        self.motion = MotionController(self.arm)
        self.eyes = create_eyes()
        self.last_joint: Optional[str] = None

    # -- command handlers --------------------------------------------------

    def handle(self, line: str) -> bool:
        """Process one input line. Returns False when the session ends."""
        tokens = shlex.split(line.strip().lower())
        if not tokens:
            return True

        head = tokens[0]
        if head in ("quit", "exit"):
            print("Exiting. Engaged servos keep holding their position.")
            return False
        if head == "help":
            print(__doc__)
        elif head == "status":
            self._status()
        elif head == "save":
            self._save(tokens[1] if len(tokens) > 1 else "new_pose")
        elif head == "home":
            self._named_pose_move(config.HOME_POSE, "home")
        elif head == "idle":
            self._named_pose_move(config.IDLE_POSE, "idle")
        elif head == "shutdown":
            return self._shutdown()
        elif head == "trim":
            self._trim(tokens[1:])
        elif head == "limits":
            self._limits(tokens[1:])
        elif head.startswith(("+", "-")) and len(tokens) == 1:
            self._nudge(head)
        elif len(tokens) == 2:
            self._move(tokens[0], tokens[1])
        else:
            print("Didn't understand that - type 'help' for commands.")
        return True

    # -- single-joint movement ----------------------------------------------

    def _move(self, joint_word: str, angle_word: str) -> None:
        joint = JOINT_ALIASES.get(joint_word)
        if joint is None:
            print(f"Unknown joint '{joint_word}'. Joints: {sorted(set(JOINT_ALIASES.values()))}")
            return
        try:
            angle = float(angle_word)
        except ValueError:
            print(f"'{angle_word}' is not a number.")
            return

        lo, hi = config.SOFT_LIMITS_DEG[joint]
        if not lo <= angle <= hi:
            print(f"{joint} is limited to {lo}-{hi}; clamping.")

        if not self.arm.is_engaged(joint):
            if not self._confirm_engage(joint, angle):
                return
            self.arm.engage_joint(joint, angle)
        else:
            self.motion.move_joint(joint, angle, cautious=True)
        self.last_joint = joint
        print(f"{joint} -> {self.arm.get_angle(joint):.0f}")

    def _confirm_engage(self, joint: str, angle: float) -> bool:
        print(
            f"\n'{joint}' is NOT powered yet. Powering it will snap it from\n"
            f"its unknown physical position to {angle:.0f} degrees at full\n"
            f"servo speed. Support the arm and keep clear."
        )
        answer = input(f"Power {joint} at {angle:.0f}? Type 'yes' to proceed: ")
        if answer.strip().lower() != "yes":
            print("Skipped - nothing was powered.")
            return False
        return True

    def _nudge(self, token: str) -> None:
        if self.last_joint is None:
            print("Move a joint first, then use +N / -N to fine-tune it.")
            return
        try:
            delta = float(token)
        except ValueError:
            print(f"'{token}' is not a number.")
            return
        current = self.arm.get_angle(self.last_joint)
        assert current is not None  # last_joint is always engaged
        self.motion.move_joint(self.last_joint, current + delta, cautious=True)
        print(f"{self.last_joint} -> {self.arm.get_angle(self.last_joint):.0f}")

    # -- trim / limits -------------------------------------------------------

    def _trim(self, args: List[str]) -> None:
        if len(args) != 2:
            print("Usage: trim <joint> <delta>    e.g. trim elbow 5")
            return
        joint = JOINT_ALIASES.get(args[0])
        if joint is None:
            print(f"Unknown joint '{args[0]}'.")
            return
        try:
            delta = int(args[1])
        except ValueError:
            print(f"'{args[1]}' is not a whole number.")
            return

        new_trim = config.SERVO_TRIM_DEG[joint] + delta
        if abs(new_trim) > config.MAX_SAFE_TRIM_DEG:
            print(
                f"REFUSED: trim would be {new_trim} deg, beyond the "
                f"{config.MAX_SAFE_TRIM_DEG} deg safe limit. The horn is "
                "more than a spline tooth off - re-seat it mechanically."
            )
            return
        config.SERVO_TRIM_DEG[joint] = new_trim
        current = self.arm.get_angle(joint)
        if current is not None:
            self.arm.set_angle(joint, current)  # re-apply so change is visible
        print(f"{joint} trim = {new_trim:+d} deg")
        print(f'Paste into config.SERVO_TRIM_DEG:   "{joint}": {new_trim},')

    def _limits(self, args: List[str]) -> None:
        if len(args) != 3:
            print("Usage: limits <joint> <lo> <hi>    e.g. limits shoulder 30 150")
            return
        joint = JOINT_ALIASES.get(args[0])
        if joint is None:
            print(f"Unknown joint '{args[0]}'.")
            return
        try:
            lo, hi = int(args[1]), int(args[2])
        except ValueError:
            print("lo and hi must be whole numbers.")
            return
        if not config.SERVO_HW_MIN_DEG <= lo < hi <= config.SERVO_HW_MAX_DEG:
            print(f"Need {config.SERVO_HW_MIN_DEG} <= lo < hi <= {config.SERVO_HW_MAX_DEG}.")
            return
        config.SOFT_LIMITS_DEG[joint] = (lo, hi)
        print(f"{joint} limits = ({lo}, {hi})")
        print(f'Paste into config.SOFT_LIMITS_DEG:   "{joint}": ({lo}, {hi}),')

    # -- pose helpers ----------------------------------------------------------

    def _named_pose_move(self, pose: Dict[str, int], name: str) -> None:
        disengaged = [j for j in config.JOINT_ORDER if not self.arm.is_engaged(j)]
        if disengaged:
            print(
                f"Can't move to {name}: these joints are not powered yet: "
                f"{disengaged}. Engage each one individually first."
            )
            return
        self.motion.move_to_pose(pose, cautious=True)
        print(f"-> {name}")

    def _save(self, name: str) -> None:
        pose = self.arm.get_pose()
        unknown = [j for j, a in pose.items() if a is None]
        if unknown:
            print(f"Pose incomplete - never-engaged joints: {unknown}")
            return
        entries = ", ".join(f'"{j}": {int(pose[j])}' for j in config.JOINT_ORDER)
        print(f'\n"{name}": {{{entries}}},')
        print("^ paste into config.NAMED_POSES (or use as a *_POSE constant)\n")

    def _status(self) -> None:
        print(f"\n{'joint':<12} {'angle':>6} {'engaged':>8} {'trim':>6} {'limits':>12}")
        for joint in config.JOINT_ORDER:
            angle = self.arm.get_angle(joint)
            print(
                f"{joint:<12} "
                f"{('-' if angle is None else f'{angle:.0f}'):>6} "
                f"{str(self.arm.is_engaged(joint)):>8} "
                f"{config.SERVO_TRIM_DEG[joint]:>+6d} "
                f"{str(config.SOFT_LIMITS_DEG[joint]):>12}"
            )
        print(f"\nconfig.CALIBRATED = {config.CALIBRATED}")
        print("When trims/limits/poses are all verified, set CALIBRATED = True "
              "in config.py to unlock main.py.\n")

    def _shutdown(self) -> bool:
        disengaged = [j for j in config.JOINT_ORDER if not self.arm.is_engaged(j)]
        if disengaged:
            print(
                "Some joints were never powered this session, so the arm is "
                f"already partly at rest ({disengaged}). Exiting without motion."
            )
            return False
        import time

        print("Folding to SAFE_SHUTDOWN_POSE...")
        self.eyes.shutdown_face()
        self.motion.go_safe_shutdown()
        time.sleep(config.SHUTDOWN_SETTLE_S)
        self.eyes.text("Safe To", "Power Off")
        print("Safe To Power Off")
        return False


def main() -> None:
    session = CalibrationSession()
    session.eyes.calibrating()
    session.eyes.text("Robot Ready", "Calibration Required")
    print(_BANNER)

    while True:
        try:
            line = input("volt> ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting. Engaged servos keep holding their position.")
            break
        try:
            if not session.handle(line):
                break
        except Exception as exc:  # noqa: BLE001 - REPL must survive bad input
            log.error("command failed: %s", exc)
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
