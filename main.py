"""VOLT robot - main program.

    python3 main.py

Startup sequence (no servo receives a pulse until you explicitly allow it):

1. BOOTING - verify config, PCA9685, OLED, camera, microphone; print a
   status report.
2. If ``config.CALIBRATED`` is False: display "Robot Ready /
   Calibration Required" and wait indefinitely. Motion is refused until
   calibration is completed and the flag is set.
3. If calibrated: wait for the operator to confirm servo engagement
   (the one open-loop move), then enter the voice-command loop:

       IDLE -> (wake word) -> LISTENING -> THINKING -> <behavior> -> IDLE

The :class:`utils.StateMachine` arbitrates the servos: voice, tracking,
gestures, and the idle breathing animation never run simultaneously.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

import config
from arm import Arm
from buzzer import create_buzzer
from motion import MotionController
from oled import create_eyes
from track import FaceTracker
from utils import RobotState, StateMachine, get_logger
from voice import Command, VoiceController

log = get_logger("main")


class VoltRobot:
    """Owns every subsystem and runs the top-level state machine."""

    def __init__(self) -> None:
        self.states = StateMachine(RobotState.BOOTING)
        self.eyes = create_eyes()
        self.buzzer = create_buzzer()
        self.arm: Optional[Arm] = None
        self.motion: Optional[MotionController] = None
        self.voice: Optional[VoiceController] = None
        self._vision = None  # created lazily; camera is exclusive
        self._breathing_stop = threading.Event()
        self._breathing_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Boot & verification
    # ------------------------------------------------------------------

    def boot(self) -> bool:
        """Verify every subsystem. Returns True if the robot can operate."""
        print("VOLT booting - no servo will move during verification.\n")
        ok = True

        problems = config.validate()
        if problems:
            ok = False
            for problem in problems:
                print(f"  FAIL  config: {problem}")
        else:
            print("  ok    config")

        try:
            self.arm = Arm()
            self.motion = MotionController(self.arm)
            print("  ok    PCA9685 (attached, no pulse)")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  FAIL  PCA9685: {exc}")

        from oled import NullEyes

        print(f"  {'ok  ' if not isinstance(self.eyes, NullEyes) else 'warn'}  OLED")

        try:
            from vision import Vision

            probe = Vision()
            probe.release()
            print("  ok    camera")
        except Exception as exc:  # noqa: BLE001
            print(f"  warn  camera: {exc}")

        try:
            self.voice = VoiceController()
            print("  ok    microphone / Vosk")
        except Exception as exc:  # noqa: BLE001
            print(f"  warn  voice: {exc}")

        print()
        return ok

    def require_calibration_or_wait(self) -> None:
        """Hold at READY forever if the robot has never been calibrated."""
        if config.CALIBRATED:
            return
        self.states.transition(RobotState.READY)
        self.eyes.text("Robot Ready", "Calibration Required")
        print(
            "Robot Ready - Calibration Required\n\n"
            "This robot has not been calibrated (config.CALIBRATED is False),\n"
            "so main.py will not move it. Run:  python3 calibrate.py\n"
            "then set CALIBRATED = True in config.py once trims, limits and\n"
            "poses are verified. Waiting (Ctrl+C to exit)..."
        )
        while True:  # wait indefinitely, commanding nothing
            time.sleep(3600)

    def engage_with_consent(self) -> None:
        """The one open-loop move, gated behind an explicit human 'yes'."""
        assert self.arm is not None and self.motion is not None
        last_known = self.arm.last_known_pose
        if last_known is not None:
            print(
                "A previous pose is on record. If servo power has stayed on\n"
                "since, engaging there will NOT move the arm at all."
            )
            start_pose, from_where = last_known, "last recorded pose"
        else:
            print(
                "No previous pose is recorded, so the arm is presumed to be\n"
                "resting unpowered (folded, claw on table). Engaging at\n"
                "SAFE_SHUTDOWN_POSE - the closest match to that rest posture."
            )
            start_pose = {j: float(a) for j, a in config.SAFE_SHUTDOWN_POSE.items()}
            from_where = "SAFE_SHUTDOWN_POSE"

        answer = input(
            f"\nEngage all servos at {from_where}? Clear the area first.\n"
            "Type 'yes' to power the arm: "
        )
        if answer.strip().lower() != "yes":
            print("Not engaging. Exiting with servos unpowered.")
            sys.exit(0)

        self.motion.engage_at_pose(start_pose)
        self.motion.go_idle(cautious=True)
        log.info("arm engaged and settled at IDLE_POSE")

    # ------------------------------------------------------------------
    # Idle personality
    # ------------------------------------------------------------------

    def _start_breathing(self) -> None:
        if not config.IDLE_BREATHING_ENABLED or self.motion is None:
            return
        self._breathing_stop.clear()
        self._breathing_thread = threading.Thread(
            target=self._breathing_loop, daemon=True
        )
        self._breathing_thread.start()

    def _stop_breathing(self) -> None:
        self._breathing_stop.set()
        if self._breathing_thread is not None:
            self._breathing_thread.join(timeout=1.0)
            self._breathing_thread = None

    def _breathing_loop(self) -> None:
        started = time.monotonic()
        interval = 1.0 / config.CONTROL_LOOP_HZ * 5
        while not self._breathing_stop.wait(interval):
            if self.states.state is not RobotState.IDLE:
                continue
            assert self.motion is not None
            self.motion.breathe_once(time.monotonic() - started)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def execute(self, command: Command) -> bool:
        """Run one voice command. Returns False when the robot should exit."""
        assert self.motion is not None
        handlers = {
            Command.GREET: self._do_greet,
            Command.HOME: lambda: self.motion.go_home(),
            Command.CALIBRATE: self._do_calibrate_hint,
            Command.STOP: self.motion.stop,
            Command.DANCE: self._do_dance,
            Command.SHIMMY: self._do_shimmy,
            Command.TRACK: self._do_track,
            Command.OPEN_CLAW: self.motion.open_gripper,
            Command.CLOSE_CLAW: self.motion.close_gripper,
            Command.GRAB: self._do_grab,
            Command.RELEASE: self.motion.release,
            Command.IDLE: lambda: self.motion.go_idle(),
            Command.SLEEP: self._do_sleep,
        }
        if command is Command.SHUTDOWN:
            self._do_shutdown()
            return False

        state_for = {
            Command.DANCE: RobotState.DANCING,
            Command.SHIMMY: RobotState.DANCING,
            Command.TRACK: RobotState.TRACKING_FACE,
            Command.GRAB: RobotState.GRABBING,
        }
        self.states.transition(state_for.get(command, RobotState.THINKING))
        try:
            handlers[command]()
        except Exception as exc:  # noqa: BLE001 - one bad command never kills the loop
            log.error("command %s failed: %s", command.name, exc)
            self.eyes.confused()
            self.buzzer.error()
            time.sleep(1.0)
        finally:
            if self.states.state is not RobotState.SHUTTING_DOWN:
                self._return_to_idle()
        return True

    def _return_to_idle(self) -> None:
        """Power-management policy: every command ends back at IDLE_POSE."""
        assert self.motion is not None
        self.motion.go_idle()
        self.states.transition(RobotState.IDLE)
        self.eyes.open_eyes()

    # -- individual behaviors ----------------------------------------------

    def _do_greet(self) -> None:
        assert self.motion is not None
        self.eyes.happy()
        self.buzzer.confirm()
        self.motion.wave()

    def _do_dance(self) -> None:
        assert self.motion is not None
        self.eyes.happy()
        threading.Thread(target=self.buzzer.dance_song, daemon=True).start()
        self.motion.dance()

    def _do_shimmy(self) -> None:
        assert self.motion is not None
        self.eyes.happy()
        threading.Thread(target=self.buzzer.shimmy_song, daemon=True).start()
        self.motion.shimmy()

    def _do_track(self) -> None:
        assert self.motion is not None
        from vision import Vision

        self.eyes.tracking()
        vision = Vision()
        try:
            tracker = FaceTracker(self.motion, vision)
            reason = tracker.run()
            if reason == "face_lost":
                self.states.transition(RobotState.SEARCHING)
                self.eyes.confused()
                time.sleep(1.0)
        finally:
            vision.release()

    def _do_grab(self) -> None:
        assert self.motion is not None
        from vision import Vision

        self.eyes.thinking()
        vision = Vision()
        try:
            self.states.transition(RobotState.SEARCHING)
            if vision.wait_for_motion(timeout_s=8.0):
                self.states.transition(RobotState.GRABBING)
                self.motion.grab()
                self.eyes.happy()
            else:
                self.eyes.confused()
                self.buzzer.error()
                time.sleep(1.0)
        finally:
            vision.release()

    def _do_sleep(self) -> None:
        assert self.motion is not None
        self.eyes.sleeping()
        self.motion.go_idle()
        time.sleep(2.0)

    def _do_calibrate_hint(self) -> None:
        self.eyes.calibrating()
        print("Calibration is a dedicated mode - exit and run: python3 calibrate.py")
        time.sleep(2.0)

    def _do_shutdown(self) -> None:
        assert self.motion is not None
        self.states.transition(RobotState.SHUTTING_DOWN)
        self._stop_breathing()
        self.eyes.shutdown_face()
        self.motion.go_safe_shutdown()
        time.sleep(config.SHUTDOWN_SETTLE_S)
        self.buzzer.shutdown()
        self.eyes.text("Safe To", "Power Off")
        print("Safe To Power Off")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        if not self.boot():
            self.states.transition(RobotState.ERROR)
            self.eyes.sad()
            print("Boot verification failed - fix the FAIL items above and rerun.")
            sys.exit(1)

        self.require_calibration_or_wait()  # returns only if CALIBRATED

        self.eyes.boot_animation()
        self.buzzer.startup()
        self.eyes.text("Robot Ready")
        self.states.transition(RobotState.READY)

        self.engage_with_consent()

        if self.voice is None:
            print(
                "Voice is unavailable, so there is nothing to drive the robot\n"
                "with in this build. Fix the microphone/Vosk warning above, or\n"
                "use calibrate.py for manual control."
            )
            sys.exit(1)

        self.states.transition(RobotState.IDLE)
        self.eyes.start_idle()
        self._start_breathing()
        print(f"\nSay '{config.WAKE_WORD}' - then one of: "
              f"{sorted(set(config.VOICE_COMMANDS.keys()))}\nCtrl+C to exit.")

        try:
            while True:
                self.voice.wait_for_wake_word()
                self.eyes.stop_idle()
                self.states.transition(RobotState.LISTENING)
                self.eyes.listening()
                self.buzzer.confirm()

                event = self.voice.listen_for_command()
                if event.command is None:
                    self.eyes.confused()
                    self.buzzer.error()
                    time.sleep(1.0)
                    self._return_to_idle()
                    self.eyes.start_idle()
                    continue

                self.states.transition(RobotState.THINKING)
                self.eyes.thinking()
                if not self.execute(event.command):
                    break  # shutdown
                self.eyes.start_idle()
        except KeyboardInterrupt:
            print(
                "\nInterrupted. Servos keep holding position - use the "
                "'shutdown' voice command or python3 shutdown.py before "
                "powering off."
            )
        finally:
            self._stop_breathing()
            self.eyes.stop_idle()


if __name__ == "__main__":
    VoltRobot().run()
