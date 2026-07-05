"""
VOLT - arm control

Python port of the smooth-movement pattern from your Arduino sketches
(moveSmooth / smoothServoMove / moveArmSmooth), but driving a PCA9685 over
I2C via adafruit-circuitpython-servokit instead of native Arduino Servo pins.

Install:
    pip3 install adafruit-circuitpython-servokit
"""

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

        # Track current angle of each joint, same purpose as posWAIST/posSHOULDER/
        # etc in your Arduino code, so smooth moves know where to step from.
        self.current = {joint: 90 for joint in config.JOINT_ORDER}

        for joint, channel in config.SERVO_CHANNELS.items():
            servo = self.kit.servo[channel]
            servo.set_pulse_width_range(config.SERVO_MIN_PULSE, config.SERVO_MAX_PULSE)

    def _write(self, joint, angle):
        angle = max(0, min(180, int(angle)))
        channel = config.SERVO_CHANNELS[joint]
        self.kit.servo[channel].angle = angle
        self.current[joint] = angle

    def move_joint_smooth(self, joint, target_angle):
        """Direct port of moveSmooth() - steps one degree at a time."""
        target_angle = max(0, min(180, int(target_angle)))
        current_angle = self.current[joint]
        step = 1 if current_angle < target_angle else -1
        angle = current_angle
        while angle != target_angle:
            angle += step
            self._write(joint, angle)
            time.sleep(config.MOVE_STEP_DELAY)
        self._write(joint, target_angle)

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
        targets = {
            joint: max(0, min(180, int(target)))
            for joint, target in zip(config.JOINT_ORDER, pose)
        }
        starts = {joint: self.current[joint] for joint in config.JOINT_ORDER}

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
            time.sleep(config.MOVE_STEP_DELAY)

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
    arm.go_home()
    print("Waving...")
    arm.wave()
    print("Done.")
