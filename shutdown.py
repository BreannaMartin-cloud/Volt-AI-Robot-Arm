"""VOLT robot - standalone safe shutdown.

    python3 shutdown.py

Folds the arm to ``SAFE_SHUTDOWN_POSE`` so the claw is already resting at
its natural support point before power is removed - gravity then has
nowhere to slam the arm. Ends with "Safe To Power Off" on the OLED.

Requires a known arm position to work from:
- If the previous run persisted a pose AND servo power has been
  maintained, you confirm that pose and the arm folds from there.
- Otherwise there is nothing trustworthy to move from; if the arm is
  already resting on the table (unpowered rest), it is ALREADY safe and
  this script simply says so without commanding anything.
"""

from __future__ import annotations

import sys
import time

import config
from arm import Arm
from buzzer import create_buzzer
from motion import MotionController
from oled import create_eyes
from utils import get_logger

log = get_logger("shutdown")


def main() -> None:
    eyes = create_eyes()
    buzzer = create_buzzer()
    arm = Arm()
    motion = MotionController(arm)

    last_known = arm.last_known_pose
    if last_known is None:
        print(
            "No trusted pose on record - servos were never engaged, so the\n"
            "arm is already resting unpowered. It is already safe to power off."
        )
        eyes.text("Safe To", "Power Off")
        return

    print("Last recorded pose (valid ONLY if servo power stayed on since):")
    for joint in config.JOINT_ORDER:
        print(f"  {joint:<12} {last_known[joint]:.0f}")
    answer = input(
        "\nHas the robot stayed powered since that pose was recorded?\n"
        "Type 'yes' to fold from there, anything else to abort: "
    )
    if answer.strip().lower() != "yes":
        print(
            "Aborted - if power was interrupted, the arm has already sagged\n"
            "to its rest position and is already safe to power off."
        )
        return

    eyes.shutdown_face()
    motion.engage_at_pose(last_known)  # re-holds at the pose it is already in
    motion.go_safe_shutdown()
    time.sleep(config.SHUTDOWN_SETTLE_S)

    buzzer.shutdown()
    buzzer.cleanup()
    eyes.text("Safe To", "Power Off")
    print("Safe To Power Off")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted - no shutdown motion performed.")
        sys.exit(1)
