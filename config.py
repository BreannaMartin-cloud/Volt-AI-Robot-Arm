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
#: the MEASURED values from physically calibrating this robot (July 2026)
#: - calibration.json still overrides them if it disagrees.
SOFT_LIMITS_DEG: Dict[str, Tuple[int, int]] = {
    "base": (10, 170),
    "shoulder": (25, 175),
    "elbow": (25, 155),
    "wrist_pitch": (5, 170),
    "wrist_roll": (10, 170),
    "gripper": (35, 75),
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
# These defaults are the MEASURED poses from physically calibrating this
# robot (July 2026). calibration.json (written by calibrate.py's ``save
# home`` / ``save idle`` / ``save shutdown``) still overrides them at
# runtime, so re-calibrating never requires editing this file.

#: Ready-for-operation pose: claw raised well clear of the table.
HOME_POSE: Dict[str, int] = {
    "base": 90,
    "shoulder": 155,
    "elbow": 100,
    "wrist_pitch": 20,
    "wrist_roll": 20,
    "gripper": 50,
}

#: Waiting pose: compact posture that minimises gravity torque on the
#: shoulder/elbow so the servos hold easily. Servos REMAIN POWERED in
#: idle - holding torque is never dropped automatically.
IDLE_POSE: Dict[str, int] = {
    "base": 90,
    "shoulder": 140,
    "elbow": 110,
    "wrist_pitch": 20,
    "wrist_roll": 20,
    "gripper": 50,
}

#: Shutdown pose: folds the arm so the claw is already resting at (or a
#: few degrees above) its natural unpowered rest on the table. When power
#: is later removed, gravity has nowhere to slam the arm - it is already
#: down. Match this to YOUR robot's true rest posture during calibration.
SAFE_SHUTDOWN_POSE: Dict[str, int] = {
    "base": 90,
    "shoulder": 125,
    "elbow": 125,
    "wrist_pitch": 20,
    "wrist_roll": 20,
    "gripper": 50,
}

GRIPPER_OPEN_DEG: int = 35
GRIPPER_CLOSED_DEG: int = 75

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

WAVE_SEQUENCE = [
    {"base": 90, "shoulder": 150, "elbow": 100, "wrist_pitch": 30, "wrist_roll": 10, "gripper": 50},
    {"base": 90, "shoulder": 150, "elbow": 100, "wrist_pitch": 30, "wrist_roll": 35, "gripper": 50},
    {"base": 90, "shoulder": 150, "elbow": 100, "wrist_pitch": 30, "wrist_roll": 10, "gripper": 50},
    {"base": 90, "shoulder": 150, "elbow": 100, "wrist_pitch": 30, "wrist_roll": 35, "gripper": 50},
]

# Safe emotes based on Bre's calibrated VOLT geometry:
# - shoulder stays >= 125 so the arm never folds backward into the table
# - elbow stays >= 45
# - wrist_pitch stays in the 20-60 working range
# - gripper stays in the measured 35-75 range
DANCE_SEQUENCE = [
    {"base": 85, "shoulder": 145, "elbow": 105, "wrist_pitch": 30, "wrist_roll": 10, "gripper": 50},
    {"base": 95, "shoulder": 150, "elbow": 95, "wrist_pitch": 45, "wrist_roll": 35, "gripper": 60},
    {"base": 85, "shoulder": 145, "elbow": 110, "wrist_pitch": 30, "wrist_roll": 10, "gripper": 50},
    {"base": 95, "shoulder": 150, "elbow": 100, "wrist_pitch": 45, "wrist_roll": 35, "gripper": 60},
]

SHIMMY_SEQUENCE = [
    {"base": 85, "shoulder": 145, "elbow": 105, "wrist_pitch": 25, "wrist_roll": 10, "gripper": 50},
    {"base": 95, "shoulder": 145, "elbow": 105, "wrist_pitch": 35, "wrist_roll": 35, "gripper": 50},
    {"base": 85, "shoulder": 150, "elbow": 100, "wrist_pitch": 25, "wrist_roll": 10, "gripper": 50},
    {"base": 95, "shoulder": 150, "elbow": 100, "wrist_pitch": 35, "wrist_roll": 35, "gripper": 50},
]

# Grab/release are deliberately gripper-only for now (no arm motion, no
# vision) - the goal is to verify the mechanics before layering vision-
# guided pick-and-place on top. See motion.grab()/motion.release().
#: Seconds the gripper stays open during a grab, giving time to place an
#: object between the jaws before they close.
GRAB_OPEN_PAUSE_S: float = 1.5

# =============================================================================
# Idle personality
# =============================================================================

#: Enables the subtle "breathing" wrist-roll oscillation while idle.
#: Runs only in the IDLE state and yields instantly to any real command.
IDLE_BREATHING_ENABLED: bool = True
IDLE_BREATHING_JOINT: str = "wrist_roll"
IDLE_BREATHING_AMPLITUDE_DEG: int = 3
IDLE_BREATHING_PERIOD_S: float = 4.0

#: OLED idle personality (values borrowed from a very cute robot-dog
#: firmware): blinks land at a random interval in this range...
OLED_IDLE_BLINK_MIN_S: float = 3.0
OLED_IDLE_BLINK_MAX_S: float = 7.0
#: ...and this fraction of blinks are followed by a quick second blink,
#: which is what makes the idle read as alive instead of metronomic.
OLED_DOUBLE_BLINK_CHANCE: float = 0.3
OLED_DOUBLE_BLINK_GAP_MIN_S: float = 0.12
OLED_DOUBLE_BLINK_GAP_MAX_S: float = 0.22
#: Chance an idle event is a sideways glance instead of a blink.
OLED_IDLE_GLANCE_CHANCE: float = 0.2

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

#: Preferred capture mode. If the camera cannot sustain CAMERA_FPS at
#: this resolution (or refuses the resolution outright), vision.py
#: automatically falls back to CAMERA_FALLBACK_* and logs why.
CAMERA_WIDTH: int = 1280
CAMERA_HEIGHT: int = 720
CAMERA_FPS: int = 30
CAMERA_FALLBACK_WIDTH: int = 640
CAMERA_FALLBACK_HEIGHT: int = 480
#: Measured FPS below this triggers the fallback (a little slack under
#: CAMERA_FPS so normal jitter doesn't demote a healthy camera).
CAMERA_MIN_SUSTAINED_FPS: float = 24.0

#: Physical mounting correction. The CSI camera on this robot is mounted
#: UPSIDE DOWN above the wrist (the ribbon cable has to exit toward the
#: arm to reach the Pi), so every raw frame arrives rotated 180 degrees.
#: vision.py applies this correction at its single frame-read point -
#: change ONLY these values if the camera is ever remounted; no code
#: edits are needed anywhere else. Valid rotations: 0, 90, 180, 270.
CAMERA_ROTATION: int = 180
CAMERA_FLIP_HORIZONTAL: bool = False
CAMERA_FLIP_VERTICAL: bool = False

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
TRACK_TILT_LIMITS_DEG: Tuple[int, int] = (10, 70)

# =============================================================================
# Voice (Vosk offline recognition + grammar lock)
# =============================================================================

VOSK_MODEL_PATH: str = "/home/bre/vosk-model-small-en-us-0.15"
#: Preferred capture rate. 48000 Hz is what this robot's USB microphone
#: supports natively (it refuses Vosk's preferred 16000). wake.py probes
#: this rate first, then the device's own default, then the fallbacks
#: below, and declares the rate actually in use to Vosk (which resamples
#: internally, so recognition works at any of these).
AUDIO_SAMPLE_RATE: int = 48000
AUDIO_FALLBACK_SAMPLE_RATES: Tuple[int, ...] = (44100, 32000, 22050, 16000, 8000)
#: Block size at AUDIO_SAMPLE_RATE (~0.5 s at 48 kHz); scaled
#: proportionally when a fallback rate is used so latency stays constant.
AUDIO_BLOCK_SIZE: int = 24000
AUDIO_CHANNELS: int = 1  # mono microphone
AUDIO_DEVICE: int | None = None  # None = system default input

WAKE_WORD: str = "hi volt"

#: Seconds to wait for a command after the wake word before giving up.
COMMAND_TIMEOUT_S: float = 6.0

#: Spoken phrase -> canonical command name. wake.py builds its
#: recognition grammar from these keys plus WAKE_WORD, which is what makes
#: short-phrase recognition reliable on a Pi.
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

    if CAMERA_ROTATION not in (0, 90, 180, 270):
        problems.append(
            f"CAMERA_ROTATION is {CAMERA_ROTATION}; must be 0, 90, 180 or 270"
        )

    return problems
