"""
VOLT - calibration utility

Python port of the interactive command style from
6DOF_TESTING_AND_CALIBRATION.ino, but with readable joint names instead of
single letters, and using the simultaneous move_pose_smooth() under the hood.

Run:
    python3 calibrate.py

Commands:
    base 94              - move a single joint to an angle (0-180)
    shoulder 90 elbow 70  - move multiple joints in one line
    pose                  - print current angles of all joints
    home                  - go to config.HOME_POSE
    save <name>           - print a config.py-ready POSES entry for the
                             current position, so you can paste it in
    trim <joint> <delta>  - nudge a joint's hardware calibration offset by
                             delta degrees (use this to correct for a servo
                             horn that wasn't installed exactly at "90")
    limits <joint> <lo> <hi>
                          - set the soft angle range you've confirmed is
                            safe for a joint on your frame
    quit                  - exit

Start here if you don't know what angle a joint's horn was actually
installed at: run `pose` to see what the software currently thinks every
joint is at, then move that joint a few degrees at a time and watch the
real arm until it's where you expect "that angle" to put it. If it never
lines up no matter what angle you command, use `trim` to correct the
offset instead of taking the horn back off the spline.
"""

import shlex
import config
from arm import Arm

JOINT_ALIASES = {
    "base": "base",
    "shoulder": "shoulder",
    "elbow": "elbow",
    "wrist_pitch": "wrist_pitch",
    "pitch": "wrist_pitch",
    "wrist_roll": "wrist_roll",
    "roll": "wrist_roll",
    "gripper": "gripper",
}


def parse_and_apply(arm, line):
    tokens = shlex.split(line.strip().lower())
    if not tokens:
        return

    if tokens[0] == "quit" or tokens[0] == "exit":
        raise SystemExit

    if tokens[0] == "home":
        arm.go_home()
        print("-> home")
        return

    if tokens[0] == "pose":
        print(dict(zip(config.JOINT_ORDER, arm.get_pose())))
        return

    if tokens[0] == "save":
        name = tokens[1] if len(tokens) > 1 else "new_pose"
        pose = arm.get_pose()
        print(f'\n"{name}": {pose},')
        print("^ paste that into config.POSES\n")
        return

    if tokens[0] == "trim":
        handle_trim(arm, tokens)
        return

    if tokens[0] == "limits":
        handle_limits(tokens)
        return

    # otherwise expect pairs like: base 94 shoulder 70
    if len(tokens) % 2 != 0:
        print("Couldn't parse that - expected pairs like: base 94 shoulder 70")
        return

    targets = dict(zip(config.JOINT_ORDER, arm.get_pose()))
    changed = False
    for i in range(0, len(tokens), 2):
        joint_word, value_word = tokens[i], tokens[i + 1]
        joint = JOINT_ALIASES.get(joint_word)
        if joint is None:
            print(f"Unknown joint '{joint_word}'. Options: {sorted(set(JOINT_ALIASES))}")
            continue
        try:
            angle = int(value_word)
        except ValueError:
            print(f"'{value_word}' isn't a number, skipping.")
            continue
        lo, hi = config.SOFT_LIMITS[joint]
        angle = max(lo, min(hi, angle))
        targets[joint] = angle
        changed = True
        print(f"{joint} -> {angle}")

    if changed:
        pose = tuple(targets[j] for j in config.JOINT_ORDER)
        arm.move_pose_smooth(pose)


def handle_trim(arm, tokens):
    if len(tokens) != 3:
        print("Usage: trim <joint> <delta>   e.g. trim elbow 5")
        return
    joint = JOINT_ALIASES.get(tokens[1])
    if joint is None:
        print(f"Unknown joint '{tokens[1]}'. Options: {sorted(set(JOINT_ALIASES))}")
        return
    try:
        delta = int(tokens[2])
    except ValueError:
        print(f"'{tokens[2]}' isn't a number.")
        return

    config.SERVO_TRIM[joint] += delta
    # Re-write the joint at its current logical angle so the trim change is
    # visible immediately, without changing what "angle" means for it.
    arm._write(joint, arm.current[joint])
    print(f"{joint} trim is now {config.SERVO_TRIM[joint]} (nudged {delta:+d})")
    print(f'Paste into config.SERVO_TRIM: "{joint}": {config.SERVO_TRIM[joint]},\n')


def handle_limits(tokens):
    if len(tokens) != 4:
        print("Usage: limits <joint> <lo> <hi>   e.g. limits shoulder 25 155")
        return
    joint = JOINT_ALIASES.get(tokens[1])
    if joint is None:
        print(f"Unknown joint '{tokens[1]}'. Options: {sorted(set(JOINT_ALIASES))}")
        return
    try:
        lo, hi = int(tokens[2]), int(tokens[3])
    except ValueError:
        print("lo/hi must be numbers.")
        return
    if lo > hi:
        print("lo must be <= hi")
        return
    lo, hi = max(0, lo), min(180, hi)
    config.SOFT_LIMITS[joint] = (lo, hi)
    print(f"{joint} soft limits are now {lo}-{hi}")
    print(f'Paste into config.SOFT_LIMITS: "{joint}": ({lo}, {hi}),\n')


def main():
    print("VOLT calibration - type 'home', 'pose', joint/angle pairs, 'trim',")
    print("'limits', or 'quit'")
    print("e.g.: shoulder 94    or    base 90 elbow 70 gripper 50\n")
    arm = Arm()
    arm.confirm_and_home()

    while True:
        try:
            line = input("volt> ")
        except (EOFError, KeyboardInterrupt):
            break
        try:
            parse_and_apply(arm, line)
        except SystemExit:
            break

    print("\nDone calibrating.")


if __name__ == "__main__":
    main()
