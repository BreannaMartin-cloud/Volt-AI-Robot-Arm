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
    quit                  - exit
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
        angle = max(0, min(180, angle))
        targets[joint] = angle
        changed = True
        print(f"{joint} -> {angle}")

    if changed:
        pose = tuple(targets[j] for j in config.JOINT_ORDER)
        arm.move_pose_smooth(pose)


def main():
    print("VOLT calibration - type 'home', 'pose', joint/angle pairs, or 'quit'")
    print("e.g.: shoulder 94    or    base 90 elbow 70 gripper 50\n")
    arm = Arm()
    arm.go_home()

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
