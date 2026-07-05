"""
VOLT - main loop

Ties together:
    wake.py   - listens for "Hi Volt / Grab Volt / Dance Volt / Do a shimmy
                Volt / What's this Volt" via mic
    arm.py    - moves the 6DOF arm through the matching sequence
    oled.py   - eyes + status text
    buzzer.py - dance/shimmy tunes
    vision.py - motion detection for grab, color guess for "what's this"

Run:
    python3 main.py
"""

import sys
import time

import config
from arm import Arm
from oled import Eyes
from buzzer import Buzzer
from vision import Vision
from wake import WakeListener


def handle_greet(arm, eyes):
    eyes.stop_idle()
    eyes.draw_happy_eyes()
    arm.wave()
    eyes.start_idle()


def handle_grab(arm, eyes, vision):
    eyes.stop_idle()
    eyes.draw_text_screen("Looking for", "something to grab...")
    triggered = vision.wait_for_wave_or_object(timeout=8)
    if triggered:
        eyes.draw_thinking()
        arm.grab_and_place()
        eyes.draw_happy_eyes()
    else:
        eyes.draw_confused()
        time.sleep(1.5)
    eyes.start_idle()


def handle_dance(arm, eyes, buzzer):
    eyes.stop_idle()
    eyes.draw_happy_eyes()
    buzzer.play_dance_song()
    arm.dance()
    eyes.start_idle()


def handle_shimmy(arm, eyes, buzzer):
    eyes.stop_idle()
    eyes.draw_happy_eyes()
    buzzer.play_shimmy_song()
    arm.shimmy()
    eyes.start_idle()


def handle_identify(arm, eyes, vision):
    eyes.stop_idle()
    eyes.draw_thinking()
    arm.look_at_object()
    time.sleep(0.3)
    label, confidence = vision.identify_object()
    if label == "unknown":
        eyes.draw_text_screen("Hmm, not sure", "what that is!")
    elif confidence is not None:
        eyes.draw_text_screen("I think that's", f"a {label}!")
    else:
        # color-guess fallback (no SSD model loaded)
        eyes.draw_text_screen("I think that's", f"a {label} thing!")
    time.sleep(2)
    arm.go_home()
    eyes.start_idle()


def main():
    print("VOLT starting up...")

    arm = Arm()
    eyes = Eyes()
    buzzer = Buzzer()
    vision = Vision()

    arm.confirm_and_home()
    eyes.draw_open_eyes()
    eyes.start_idle()

    try:
        listener = WakeListener()
    except RuntimeError as e:
        print(f"Voice commands unavailable: {e}")
        print("Set up Vosk + sounddevice and a model per wake.py's docstring, then rerun.")
        sys.exit(1)

    print("Listening for: Hi Volt / Grab Volt / Dance Volt / Do a shimmy Volt / What's this Volt")

    actions = {
        "greet": lambda: handle_greet(arm, eyes),
        "grab": lambda: handle_grab(arm, eyes, vision),
        "dance": lambda: handle_dance(arm, eyes, buzzer),
        "shimmy": lambda: handle_shimmy(arm, eyes, buzzer),
        "identify": lambda: handle_identify(arm, eyes, vision),
    }

    try:
        while True:
            action = listener.listen_for_command()
            if action in actions:
                print(f"-> {action}")
                actions[action]()
    except KeyboardInterrupt:
        print("\nShutting down VOLT...")
    finally:
        eyes.stop_idle()
        arm.go_home()
        buzzer.cleanup()
        vision.release()


if __name__ == "__main__":
    main()
