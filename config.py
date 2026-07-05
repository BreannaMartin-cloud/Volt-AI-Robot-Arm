"""VOLT robot - central configuration.

Every tunable value in the project lives here. No other module may define
a servo channel, an angle constant, a pin number, or a threshold. If you
find a magic number anywhere else in the codebase, that is a bug.

Angle conventions
-----------------
All angles in this file (and everywhere in the project) are *logical*
degrees in the range 0-180. The per-joint ``SERVO_TRIM_DEG`` correction is
applied at the single hardware write point in ``arm.py`` - poses and
commands always deal in logical angles, so calibrating a trim never
requires editing a pose.

Joint order everywhere in the project is ``JOINT_ORDER``:
    base, shoulder, elbow, wrist_pitch, wrist_roll, gripper
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

# =============================================================================
# PCA9685 / servo hardware
# =============================================================================

PCA9685_I2C_ADDRESS: int = 0x40
PCA9685_CHANNEL_COUNT: int = 16

#: The ONLY servo channel map in the project. Everything imports this.
SERVO_CHANNELS: Dict[str, int] = {
    "base": 0,
    "shoulder": 1,
    "elbow": 2,
    "wrist_pitch": 3,
    "wrist_roll": 4,
    "gripper": 7,
}

#: Channels 5 and 6 are intentionally unused on this build. Nothing may
#: drive them; config validation enforces this.
UNUSED_CHANNELS: Tuple[int, ...] = (5, 6)

JOINT_ORDER: List[str] = [
    "base",
    "shoulder",
    "elbow",
    "wrist_pitch",
    "wrist_roll",
    "gripper",
]

#: Servo pulse range in microseconds. Standard for the MG996R/SG90-class
#: servos in the Yahboom 6DOF kit. Narrow this if a servo buzzes or stalls
#: at the extremes of travel.
SERVO_MIN_PULSE_US: int = 500
SERVO_MAX_PULSE_US: int = 2500

#: Hardware angle bounds after trim is applied (the servo's own range).
SERVO_HW_MIN_DEG: int = 0
SERVO_HW_MAX_DEG: int = 180

# =============================================================================
# Calibration state
# =============================================================================

#: Where measured calibration is persisted (JSON, written by calibrate.py
#: via calibration.py - never edited by hand). Everything in it overrides
#: the factory defaults below at runtime; see calibration.apply().
CALIBRATION_FILE_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "calibration.json"
)
#: The previous calibration is copied here before every overwrite.
CALIBRATION_BACKUP_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "calibration_backup.json"
)

#: Factory default only - DO NOT edit by hand. The real value is managed
#: by calibration.py: it flips to True in calibration.json automatically
#: once HOME_POSE, IDLE_POSE and SAFE_SHUTDOWN_POSE have all been saved
#: with calibrate.py's ``save`` command, and calibration.apply() loads it
#: at runtime. While False, main.py refuses to run any motion behavior
#: and displays "Calibration Required".
CALIBRATED: bool = False

#: Per-joint trim in degrees, added to every commanded angle at the
#: hardware write point. This corrects for servo horns that were installed
#: off-spline (horns index in ~15-17 degree steps, so every joint is
#: expected to need SOME trim). Found with calibrate.py's ``trim`` command.
SERVO_TRIM_DEG: Dict[str, int] = {
    "base": 0,
    "shoulder": 0,
    "elbow": 0,
    "wrist_pitch": 0,
    "wrist_roll": 0,
    "gripper": 0,
}

#: If a measured trim exceeds this magnitude, the horn is more than one
#: spline tooth off - re-seat it mechanically instead of trimming further.
MAX_SAFE_TRIM_DEG: int = 20

#: Per-joint (min, max) logical angle limits. Every commanded angle is
#: clamped to this range before the trim is applied. These defaults are
#: CONSERVATIVE PLACEHOLDERS - verify and tighten them on the real frame
#: with calibrate.py's ``limits`` command before trusting any sequence.
SOFT_LIMITS_DEG: Dict[str, Tuple[int, int]] = {
    "base": (10, 170),
    "shoulder": (25, 155),
    "elbow": (25, 155),
    "wrist_pitch": (20, 160),
    "wrist_roll": (10, 170),
    "gripper": (35, 145),
}

#: Where the last commanded pose is persisted between runs. Valid only
#: while servo power has been maintained; a power cycle invalidates it
#: (the arm sags to its mechanical rest when unpowered).
STATE_FILE_PATH: str = "/home/bre/.volt_arm_state.json"

# =============================================================================
# Motion profile (used by motion.py for every move)
# =============================================================================

#: Control loop rate for interpolated moves.
CONTROL_LOOP_HZ: int = 50

#: Peak joint velocity in degrees/second for normal moves.
MAX_VELOCITY_DEG_S: float = 60.0

#: Acceleration limit in degrees/second^2. Motion ramps up and down at
#: this rate (trapezoidal profile) so the arm never jerks.
MAX_ACCEL_DEG_S2: float = 120.0

#: Slower profile used for the first engaged move after startup and for
#: all calibration moves, when confidence in the arm's true position is
#: lowest.
CAUTIOUS_VELOCITY_DEG_S: float = 25.0
CAUTIOUS_ACCEL_DEG_S2: float = 50.0

# =============================================================================
# Poses - logical angles, keyed by joint name (never positional tuples)
# =============================================================================
# These are FACTORY-DEFAULT STARTING GUESSES. The measured versions live
# in calibration.json (written by calibrate.py's ``save home`` / ``save
# idle`` / ``save shutdown``) and override these at runtime.

#: Ready-for-operation pose: claw raised well clear of the table.
HOME_POSE: Dict[str, int] = {
    "base": 90,
    "shoulder": 90,
    "elbow": 65,
    "wrist_pitch": 90,
    "wrist_roll": 90,
    "gripper": 50,
}

#: Waiting pose: compact posture that minimises gravity torque on the
#: shoulder/elbow so the servos hold easily. Servos REMAIN POWERED in
#: idle - holding torque is never dropped automatically.
IDLE_POSE: Dict[str, int] = {
    "base": 90,
    "shoulder": 75,
    "elbow": 50,
    "wrist_pitch": 70,
    "wrist_roll": 90,
    "gripper": 50,
}

#: Shutdown pose: folds the arm so the claw is already resting at (or a
#: few degrees above) its natural unpowered rest on the table. When power
#: is later removed, gravity has nowhere to slam the arm - it is already
#: down. Match this to YOUR robot's true rest posture during calibration.
SAFE_SHUTDOWN_POSE: Dict[str, int] = {
    "base": 90,
    "shoulder": 45,
    "elbow": 30,
    "wrist_pitch": 45,
    "wrist_roll": 90,
    "gripper": 60,
}

GRIPPER_OPEN_DEG: int = 50
GRIPPER_CLOSED_DEG: int = 120

#: Seconds to hold SAFE_SHUTDOWN_POSE before declaring it safe to power off.
SHUTDOWN_SETTLE_S: float = 3.0

NAMED_POSES: Dict[str, Dict[str, int]] = {
    "home": HOME_POSE,
    "idle": IDLE_POSE,
    "shutdown": SAFE_SHUTDOWN_POSE,
}

# =============================================================================
# Gesture sequences - lists of poses played through motion.py's profiler
# =============================================================================

WAVE_SEQUENCE: List[Dict[str, int]] = [
    {"base": 90, "shoulder": 70, "elbow": 60, "wrist_pitch": 90, "wrist_roll": 60, "gripper": 50},
    {"base": 90, "shoulder": 70, "elbow": 60, "wrist_pitch": 90, "wrist_roll": 130, "gripper": 50},
    {"base": 90, "shoulder": 70, "elbow": 60, "wrist_pitch": 90, "wrist_roll": 60, "gripper": 50},
    {"base": 90, "shoulder": 70, "elbow": 60, "wrist_pitch": 90, "wrist_roll": 130, "gripper": 50},
]

DANCE_SEQUENCE: List[Dict[str, int]] = [
    {"base": 60, "shoulder": 100, "elbow": 80, "wrist_pitch": 70, "wrist_roll": 60, "gripper": 50},
    {"base": 120, "shoulder": 80, "elbow": 50, "wrist_pitch": 110, "wrist_roll": 130, "gripper": 90},
    {"base": 60, "shoulder": 100, "elbow": 80, "wrist_pitch": 70, "wrist_roll": 60, "gripper": 50},
    {"base": 120, "shoulder": 80, "elbow": 50, "wrist_pitch": 110, "wrist_roll": 130, "gripper": 90},
]

SHIMMY_SEQUENCE: List[Dict[str, int]] = [
    {"base": 80, "shoulder": 90, "elbow": 65, "wrist_pitch": 80, "wrist_roll": 70, "gripper": 50},
    {"base": 100, "shoulder": 90, "elbow": 65, "wrist_pitch": 100, "wrist_roll": 110, "gripper": 50},
    {"base": 80, "shoulder": 90, "elbow": 65, "wrist_pitch": 80, "wrist_roll": 70, "gripper": 50},
    {"base": 100, "shoulder": 90, "elbow": 65, "wrist_pitch": 100, "wrist_roll": 110, "gripper": 50},
]

GRAB_SEQUENCE: List[Dict[str, int]] = [
    {"base": 94, "shoulder": 90, "elbow": 70, "wrist_pitch": 100, "wrist_roll": 100, "gripper": GRIPPER_OPEN_DEG},
    {"base": 94, "shoulder": 95, "elbow": 70, "wrist_pitch": 55, "wrist_roll": 100, "gripper": GRIPPER_OPEN_DEG},
    {"base": 94, "shoulder": 95, "elbow": 70, "wrist_pitch": 55, "wrist_roll": 100, "gripper": GRIPPER_CLOSED_DEG},
    {"base": 94, "shoulder": 85, "elbow": 60, "wrist_pitch": 80, "wrist_roll": 100, "gripper": GRIPPER_CLOSED_DEG},
]

RELEASE_SEQUENCE: List[Dict[str, int]] = [
    {"base": 94, "shoulder": 95, "elbow": 70, "wrist_pitch": 55, "wrist_roll": 100, "gripper": GRIPPER_CLOSED_DEG},
    {"base": 94, "shoulder": 95, "elbow": 70, "wrist_pitch": 55, "wrist_roll": 100, "gripper": GRIPPER_OPEN_DEG},
]

# =============================================================================
# Idle personality
# =============================================================================

#: Enables the subtle "breathing" wrist-roll oscillation while idle.
#: Runs only in the IDLE state and yields instantly to any real command.
IDLE_BREATHING_ENABLED: bool = True
IDLE_BREATHING_JOINT: str = "wrist_roll"
IDLE_BREATHING_AMPLITUDE_DEG: int = 3
IDLE_BREATHING_PERIOD_S: float = 4.0

#: Seconds between idle blinks on the OLED.
IDLE_BLINK_INTERVAL_S: float = 4.0

# =============================================================================
# OLED (0.96" SSD1306, I2C)
# =============================================================================

OLED_I2C_ADDRESS: int = 0x3C
OLED_I2C_PORT: int = 1
OLED_WIDTH: int = 128
OLED_HEIGHT: int = 64

# =============================================================================
# Buzzer (passive, software PWM)
# =============================================================================

BUZZER_GPIO_PIN: int = 18  # BCM numbering, PWM-capable

# =============================================================================
# Camera / vision
# =============================================================================

CAMERA_INDEX: int = 0
FRAME_WIDTH: int = 640
FRAME_HEIGHT: int = 480
FACE_DETECTION_CONFIDENCE: float = 0.6

#: Motion-detection trigger used by "grab object".
MOTION_THRESHOLD: int = 25000
MOTION_CONFIRM_FRAMES: int = 3

# =============================================================================
# Face tracking
# =============================================================================
# Tracking drives ONLY these two joints. No other joint may move while
# tracking; track.py enforces this.

TRACK_PAN_JOINT: str = "base"
TRACK_TILT_JOINT: str = "wrist_pitch"

TRACK_DEADZONE_PX: int = 30
TRACK_GAIN_DEG_PER_PX: float = 0.03
TRACK_MAX_STEP_DEG: float = 3.0
TRACK_LOOP_INTERVAL_S: float = 0.03
#: Tracking gives up and returns to idle after this long without a face.
TRACK_FACE_LOST_TIMEOUT_S: float = 10.0

#: Tighter-than-soft-limit bounds tracking is allowed to command.
TRACK_PAN_LIMITS_DEG: Tuple[int, int] = (30, 150)
TRACK_TILT_LIMITS_DEG: Tuple[int, int] = (50, 130)

# =============================================================================
# Voice (Vosk offline recognition + grammar lock)
# =============================================================================

VOSK_MODEL_PATH: str = "/home/bre/vosk-model-small-en-us-0.15"
AUDIO_SAMPLE_RATE: int = 16000
AUDIO_BLOCK_SIZE: int = 8000
AUDIO_CHANNELS: int = 1  # mono microphone
AUDIO_DEVICE: int | None = None  # None = system default input

WAKE_WORD: str = "hi volt"

#: Seconds to wait for a command after the wake word before giving up.
COMMAND_TIMEOUT_S: float = 6.0

#: Spoken phrase -> canonical command name. wake.py builds its
#: recognition grammar from these keys plus WAKE_WORD, which is what makes
#: short-phrase recognition reliable on a Pi 4.
VOICE_COMMANDS: Dict[str, str] = {
    "hi volt": "greet",
    "home": "home",
    "calibrate": "calibrate",
    "stop": "stop",
    "shutdown": "shutdown",
    "dance volt": "dance",
    "shimmy volt": "shimmy",
    "track me": "track",
    "follow face": "track",
    "open claw": "open_claw",
    "close claw": "close_claw",
    "grab object": "grab",
    "release object": "release",
    "go idle": "idle",
    "sleep": "sleep",
}

# =============================================================================
# Logging
# =============================================================================

LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


# =============================================================================
# Validation
# =============================================================================

def validate() -> List[str]:
    """Sanity-check this configuration; returns a list of problems.

    Called by main.py and debug.py at startup. An empty list means the
    configuration is internally consistent (it does NOT mean the robot is
    calibrated - that is what ``CALIBRATED`` asserts).
    """
    problems: List[str] = []

    channels = list(SERVO_CHANNELS.values())
    if len(set(channels)) != len(channels):
        problems.append("SERVO_CHANNELS assigns the same channel twice")
    for joint, channel in SERVO_CHANNELS.items():
        if channel in UNUSED_CHANNELS:
            problems.append(f"joint '{joint}' uses reserved channel {channel}")
        if not 0 <= channel < PCA9685_CHANNEL_COUNT:
            problems.append(f"joint '{joint}' channel {channel} out of range")

    if set(JOINT_ORDER) != set(SERVO_CHANNELS):
        problems.append("JOINT_ORDER and SERVO_CHANNELS disagree on joints")

    for table_name, table in (
        ("SERVO_TRIM_DEG", SERVO_TRIM_DEG),
        ("SOFT_LIMITS_DEG", SOFT_LIMITS_DEG),
    ):
        missing = set(JOINT_ORDER) - set(table)
        if missing:
            problems.append(f"{table_name} missing joints: {sorted(missing)}")

    for joint, trim in SERVO_TRIM_DEG.items():
        if abs(trim) > MAX_SAFE_TRIM_DEG:
            problems.append(
                f"trim for '{joint}' is {trim} deg (> {MAX_SAFE_TRIM_DEG}); "
                "re-seat the horn mechanically instead"
            )

    for joint, (lo, hi) in SOFT_LIMITS_DEG.items():
        if not (SERVO_HW_MIN_DEG <= lo < hi <= SERVO_HW_MAX_DEG):
            problems.append(f"soft limits for '{joint}' invalid: ({lo}, {hi})")

    for pose_name, pose in NAMED_POSES.items():
        missing = set(JOINT_ORDER) - set(pose)
        if missing:
            problems.append(f"pose '{pose_name}' missing joints: {sorted(missing)}")
        for joint, angle in pose.items():
            lo, hi = SOFT_LIMITS_DEG.get(joint, (SERVO_HW_MIN_DEG, SERVO_HW_MAX_DEG))
            if not lo <= angle <= hi:
                problems.append(
                    f"pose '{pose_name}' sets {joint}={angle}, outside limits ({lo}, {hi})"
                )

    for track_joint in (TRACK_PAN_JOINT, TRACK_TILT_JOINT):
        if track_joint not in SERVO_CHANNELS:
            problems.append(f"tracking joint '{track_joint}' is not a known joint")

    return problems
