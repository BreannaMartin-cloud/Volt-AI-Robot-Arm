"""
VOLT - arm control

Python port of the smooth-movement pattern from your Arduino sketches
(moveSmooth / smoothServoMove / moveArmSmooth), but driving a PCA9685 over
I2C via adafruit-circuitpython-servokit instead of native Arduino Servo pins.

Install:
    pip3 install adafruit-circuitpython-servokit

IMPORTANT - read before running anything that moves the arm:

Hobby servos have no position feedback. The instant a channel is written,
the servo drives at full speed toward whatever angle it's told - it does
not know, and this code cannot know, where the arm physically is. Software
here tracks each joint's angle as a number (self.current), but that number
is only trustworthy if it's been true since the last confirmed move. On a
fresh run, after a crash, or after any power loss, that number is a guess.

That's what confirm_and_home() below is for: it will not move anything
silently. The first time a given joint's position is unknown, it prints a
warning and (unless explicitly told to skip the prompt) waits for you to
type "arm" - use that pause to clear the area and be ready to support the
arm, especially the elbow, which is what the forearm/wrist/gripper hang
from when the arm is folded at rest.
"""

import json
import os
import time
import config

try:
    from adafruit_servokit import ServoKit
except ImportError:
    ServoKit = None  # allows this module to be imported for testing without hardware


class Arm:
    def __init__(self):
        if ServoKit is None:
            raise RuntimeError(
                "adafruit_servokit not installed. Run: "
                "pip3 install adafruit-circuitpython-servokit"
            )

        self.kit = ServoKit(channels=16, address=config.PCA9685_I2C_ADDRESS)

        for joint, channel in config.SERVO_CHANNELS.items():
            servo = self.kit.servo[channel]
            servo.set_pulse_width_range(config.SERVO_MIN_PULSE, config.SERVO_MAX_PULSE)

        # Track current angle of each joint, same purpose as posWAIST/posSHOULDER/
        # etc in your Arduino code, so smooth moves know where to step from.
        # Loaded from disk if a previous run recorded a pose; otherwise every
        # joint starts "unknown" (None) until confirm_and_home() has run.
        self.current = {joint: None for joint in config.JOINT_ORDER}
        self.pose_known = self._load_state()

    # ---- persisted state (survives script restarts, not power loss) ----

    def _load_state(self):
        try:
            with open(config.STATE_FILE_PATH) as f:
                saved = json.load(f)
        except (FileNotFoundError, ValueError):
            return False

        if not all(joint in saved for joint in config.JOINT_ORDER):
            return False

        self.current = {joint: saved[joint] for joint in config.JOINT_ORDER}
        return True

    def _save_state(self):
        tmp_path = config.STATE_FILE_PATH + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(self.current, f)
            os.replace(tmp_path, config.STATE_FILE_PATH)
        except OSError:
            pass  # persistence is a nice-to-have, not load-bearing

    # ---- low-level write ----

    def _write(self, joint, angle):
        # self.current tracks the LOGICAL angle (trim-independent) - this is
        # what get_pose(), calibrate.py, and config.py's poses all deal in.
        # SERVO_TRIM is applied only to the physical pulse sent to hardware,
        # never fed back into self.current - otherwise repeated moves would
        # stack the trim correction on top of itself every time.
        lo, hi = config.SOFT_LIMITS[joint]
        angle = max(lo, min(hi, int(angle)))
        hw_angle = max(0, min(180, angle + config.SERVO_TRIM[joint]))
        channel = config.SERVO_CHANNELS[joint]
        self.kit.servo[channel].angle = hw_angle
        self.current[joint] = angle

    def confirm_and_home(self, auto_confirm=False):
        """
        Safe first move after startup. If every joint's position is already
        known (loaded from the state file, i.e. this process has moved the
        arm before), just goes home normally. Otherwise this is a genuinely
        unknown physical pose - warns loudly and waits for confirmation
        before attaching/moving anything, then homes slowly instead of at
        the normal speed.

        Call this once at startup instead of go_home() directly.
        """
        if self.pose_known:
            self.go_home()
            return

        print("=" * 60)
        print("VOLT arm - position unknown.")
        print("This is the first move since the arm was last homed, so the")
        print("real physical pose of each joint isn't known - if the arm is")
        print("folded at the elbow with the claw resting on the table, that's")
        print("expected while unpowered, but the elbow is what the whole")
        print("forearm/wrist/gripper hang from. The first move could be a")
        print("bigger, faster motion than you expect.")
        print("Clear the area and be ready to support the arm.")
        print("=" * 60)

        if not auto_confirm:
            while input("Type 'arm' and press Enter to continue: ").strip().lower() != "arm":
                pass

        # Unknown joints start the ramp from HOME_POSE itself (i.e. no ramp,
        # straight commanded write) since there's no better guess available -
        # this is exactly why the slow step delay and the warning above
        # matter here specifically.
        for joint in config.JOINT_ORDER:
            if self.current[joint] is None:
                self.current[joint] = dict(zip(config.JOINT_ORDER, config.HOME_POSE))[joint]

        self._move_pose(config.HOME_POSE, step_delay=config.FIRST_MOVE_STEP_DELAY)
        self.pose_known = True
        self._save_state()
        print("Homed.")

    def move_joint_smooth(self, joint, target_angle):
        """Direct port of moveSmooth() - steps one degree at a time."""
        lo, hi = config.SOFT_LIMITS[joint]
        target_angle = max(lo, min(hi, int(target_angle)))
        current_angle = self.current[joint]
        if current_angle is None:
            current_angle = target_angle  # unknown - see confirm_and_home()
        step = 1 if current_angle < target_angle else -1
        angle = current_angle
        while angle != target_angle:
            angle += step
            self._write(joint, angle)
            time.sleep(config.MOVE_STEP_DELAY)
        self._write(joint, target_angle)
        self._save_state()

    def move_pose_smooth(self, pose):
        """
        Moves all six joints to `pose` at the same time, each ramping
        smoothly over the same duration - unlike the Arduino version (and
        the old version of this function), which moved one joint fully
        before starting the next. This is what makes the arm's motion look
        like one continuous gesture instead of a stepped, robotic sequence.

        pose is a 6-tuple in
        (base, shoulder, elbow, wrist_pitch, wrist_roll, gripper) order.
        """
        self._move_pose(pose, step_delay=config.MOVE_STEP_DELAY)
        self._save_state()

    def _move_pose(self, pose, step_delay):
        targets = {}
        for joint, target in zip(config.JOINT_ORDER, pose):
            lo, hi = config.SOFT_LIMITS[joint]
            targets[joint] = max(lo, min(hi, int(target)))

        starts = {}
        for joint in config.JOINT_ORDER:
            starts[joint] = self.current[joint] if self.current[joint] is not None else targets[joint]

        # However many degrees the biggest single move is, that's how many
        # steps everyone takes - smaller moves just get slower per-step,
        # so every joint arrives together.
        steps = max(abs(targets[j] - starts[j]) for j in config.JOINT_ORDER)
        steps = max(steps, 1)

        for i in range(1, steps + 1):
            frac = i / steps
            for joint in config.JOINT_ORDER:
                angle = starts[joint] + (targets[joint] - starts[joint]) * frac
                self._write(joint, round(angle))
            time.sleep(step_delay)

        # snap exactly to target to kill any rounding drift
        for joint in config.JOINT_ORDER:
            self._write(joint, targets[joint])

    def get_pose(self):
        """Current angle of every joint, in JOINT_ORDER - used by debug.py."""
        return tuple(self.current[j] for j in config.JOINT_ORDER)

    def run_sequence(self, sequence, pause_between=0.3):
        for pose in sequence:
            self.move_pose_smooth(pose)
            time.sleep(pause_between)

    def go_home(self):
        self.move_pose_smooth(config.HOME_POSE)

    def open_gripper(self):
        self.move_joint_smooth("gripper", config.GRIPPER_OPEN)

    def close_gripper(self):
        self.move_joint_smooth("gripper", config.GRIPPER_CLOSED)

    # ---- named behaviors, built from config.py sequences ----

    def wave(self):
        self.run_sequence(config.WAVE_SEQUENCE, pause_between=0.4)

    def grab_and_place(self):
        self.run_sequence(config.GRAB_SEQUENCE, pause_between=0.4)
        self.go_home()

    def dance(self):
        self.run_sequence(config.DANCE_SEQUENCE, pause_between=0.25)

    def shimmy(self):
        self.run_sequence(config.SHIMMY_SEQUENCE, pause_between=0.15)

    def look_at_object(self):
        self.move_pose_smooth(config.INSPECT_POSE)

    def move_named(self, pose_name):
        """Move to a pose by name from config.POSES, e.g. arm.move_named('home')."""
        if pose_name not in config.POSES:
            raise KeyError(f"Unknown pose '{pose_name}'. Options: {list(config.POSES)}")
        self.move_pose_smooth(config.POSES[pose_name])


if __name__ == "__main__":
    # Quick manual test: python3 arm.py
    arm = Arm()
    print("Homing...")
    arm.confirm_and_home()
    print("Waving...")
    arm.wave()
    print("Done.")
