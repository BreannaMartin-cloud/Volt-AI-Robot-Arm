"""
VOLT - central config
Ported from: 6DOF_TESTING_AND_CALIBRATION.ino, 6DOF_ROBOTIC_ARM_COLOR_SORTING.ino,
6DOF-stacking.ino

Angle order everywhere in this project is always:
    (base, shoulder, elbow, wrist_pitch, wrist_roll, gripper)
This matches the order used in your Arduino sketches.
"""

# ---------------------------------------------------------------------------
# PCA9685 / servo setup
# ---------------------------------------------------------------------------
PCA9685_I2C_ADDRESS = 0x40

# TODO: confirm these against how you actually wired the PCA9685 channels.
# Arduino pins were: base=3, shoulder=5, elbow=6, wristPitch=9, wristRoll=10, gripper=11
# I'm assuming you wired them in the same order onto PCA9685 channels 0-5.
SERVO_CHANNELS = {
    "base": 0,
    "shoulder": 1,
    "elbow": 2,
    "wrist_pitch": 3,
    "wrist_roll": 4,
    "gripper": 5,
}

JOINT_ORDER = ["base", "shoulder", "elbow", "wrist_pitch", "wrist_roll", "gripper"]

# Servo pulse range - standard for SG90/MG996R/DS3225 clones. Tweak if your
# servos buzz at the extremes or don't reach a full 0-180 sweep.
SERVO_MIN_PULSE = 500
SERVO_MAX_PULSE = 2500

# Smooth-move step delay (seconds). Arduino used delay(10) i.e. 10ms/degree.
MOVE_STEP_DELAY = 0.01

# The very first move after the Pi (re)starts is slower than that, on
# purpose - see arm.py's confirm_and_home(). This matters because the servo
# horns are open-loop: nothing in software actually knows the true physical
# angle of a joint until it's been moved and tracked at least once. If the
# arm loses power (script restart, reboot, unplug) while sitting anywhere
# other than exactly HOME_POSE, the first move after power returns is a
# jump from an assumed position to a commanded one, not a small correction.
FIRST_MOVE_STEP_DELAY = 0.03

# ---------------------------------------------------------------------------
# Per-joint calibration - THIS IS THE PART YOU NEED TO SET UP BY HAND
# ---------------------------------------------------------------------------
# Hobby servo horns only index onto the spline in fixed increments (usually
# ~15-17 degrees apart, since most horns have 21-25 teeth). That means when
# you physically screwed a horn/arm segment onto a servo, there's basically
# no chance "90" in software landed exactly on the physical angle you wanted
# for that joint's home/rest position - it's very likely off by anywhere
# from a couple degrees to over ten.
#
# SERVO_TRIM lets you correct that in software instead of re-splining a
# horn: it's added to every angle you command for that joint before it's
# sent to the servo. Find these values with calibrate.py's `trim` command -
# it walks you through nudging a joint until it visually matches the pose
# you want, then prints the trim value to paste here.
#
# Defaults are 0 (no correction) - until you calibrate per joint, angles in
# this file are only as accurate as your horn placement happened to be.
SERVO_TRIM = {
    "base": 0,
    "shoulder": 0,
    "elbow": 0,
    "wrist_pitch": 0,
    "wrist_roll": 0,
    "gripper": 0,
}

# SOFT_LIMITS constrain each joint to the range that's actually safe on
# YOUR frame - tighter than the servo's mechanical 0-180 sweep. Values
# outside this range are clamped before being sent to the servo, in
# move_joint_smooth/move_pose_smooth AND in the trim-adjusted _write().
# These defaults are conservative placeholders, not verified for your
# build - use calibrate.py's `limits` command to test and narrow them,
# especially shoulder/elbow (frame collisions) and gripper (mechanical
# stop, so it doesn't stall the motor against itself).
SOFT_LIMITS = {
    "base": (0, 180),
    "shoulder": (20, 160),
    "elbow": (20, 160),
    "wrist_pitch": (0, 180),
    "wrist_roll": (0, 180),
    "gripper": (30, 150),
}

# ---------------------------------------------------------------------------
# OLED
# ---------------------------------------------------------------------------
OLED_I2C_ADDRESS = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 64  # change to 32 if you've got the smaller module

# ---------------------------------------------------------------------------
# Buzzer
# ---------------------------------------------------------------------------
BUZZER_GPIO_PIN = 18  # BCM numbering, PWM-capable pin

# ---------------------------------------------------------------------------
# Camera / vision
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
WAVE_MOTION_THRESHOLD = 25000   # sum of thresholded pixel diff to count as "waving"
WAVE_CONFIRM_FRAMES = 3         # need motion on N consecutive checks

# MobileNet-SSD model files for real object detection (see README for the
# download step). If these files aren't present, Vision.identify_object()
# falls back to the color guess automatically.
SSD_PROTOTXT = "/home/bre/models/MobileNetSSD_deploy.prototxt"
SSD_MODEL = "/home/bre/models/MobileNetSSD_deploy.caffemodel"

# ---------------------------------------------------------------------------
# Face tracking
# ---------------------------------------------------------------------------
# 2-axis tracking: base joint pans left/right, shoulder tilts up/down.
# This is a simple proportional controller, not true IK - fine for keeping
# a face centered in frame.
TRACK_BASE_JOINT = "base"
TRACK_TILT_JOINT = "shoulder"
TRACK_DEADZONE_PX = 30        # ignore offsets smaller than this (avoids jitter)
TRACK_GAIN = 0.03             # how many degrees to move per pixel of offset
TRACK_MAX_STEP_DEG = 4        # clamp how far it can move in one correction
TRACK_BASE_LIMITS = (30, 150)     # don't let tracking drive the base past these
TRACK_TILT_LIMITS = (60, 130)     # or the shoulder past these
FACE_DETECTION_CONFIDENCE = 0.6

# ---------------------------------------------------------------------------
# Wake word / voice commands (Vosk)
# ---------------------------------------------------------------------------
# Download a small model from https://alphacephei.com/vosk/models
# e.g. vosk-model-small-en-us-0.15, unzip it, point this at the folder.
VOSK_MODEL_PATH = "/home/bre/vosk-model-small-en-us-0.15"
AUDIO_SAMPLE_RATE = 16000
AUDIO_DEVICE = None  # None = default input device; set an index if you have multiple mics

# Locking Vosk to a grammar (rather than open dictation) makes recognition of
# short commands like these dramatically more reliable on a Pi 4.
COMMAND_GRAMMAR = [
    "hi volt",
    "grab volt",
    "dance volt",
    "do a shimmy volt",
    "what's this volt",
    "whats this volt",
    "[unk]",
]

# ---------------------------------------------------------------------------
# Poses, all in (base, shoulder, elbow, wrist_pitch, wrist_roll, gripper) order
# ---------------------------------------------------------------------------

HOME_POSE = (90, 90, 65, 90, 90, 40)  # from stacking.ino initial pose

GRIPPER_OPEN = 50
GRIPPER_CLOSED = 120

# Wave gesture for "Hi Volt!" - oscillates base + wrist roll like a hand wave.
# Built fresh (no wave sequence existed in your Arduino code).
WAVE_SEQUENCE = [
    (90, 70, 60, 90, 60, 40),
    (90, 70, 60, 90, 130, 40),
    (90, 70, 60, 90, 60, 40),
    (90, 70, 60, 90, 130, 40),
    (90, 90, 65, 90, 90, 40),  # back to home
]

# Grab-and-place sequence, adapted from redTask() in the color sorting sketch
# (that's the fullest pick-and-place example you had). Triggered by motion/
# wave detection in frame rather than color, since there's no color sensor
# wired to the Pi build.
GRAB_SEQUENCE = [
    (94, 90, 70, 100, 100, GRIPPER_OPEN),
    (94, 95, 70, 55, 100, 95),
    (94, 95, 60, 55, 100, 95),
    (175, 90, 60, 120, 180, 95),
    (175, 80, 65, 100, 180, GRIPPER_OPEN),
    (175, 80, 50, 100, 180, GRIPPER_OPEN),
    (94, 90, 70, 100, 100, GRIPPER_CLOSED),
]

# Dance emote - original sequence + tune (see buzzer.py), fairly big swingy
# movements set to a short jingle.
DANCE_SEQUENCE = [
    (60, 100, 80, 70, 60, 40),
    (120, 80, 50, 110, 130, 90),
    (60, 100, 80, 70, 60, 40),
    (120, 80, 50, 110, 130, 90),
    (90, 90, 65, 90, 90, 40),
]

# Shimmy emote - smaller, faster wrist/base wiggle, different tune.
SHIMMY_SEQUENCE = [
    (80, 90, 65, 80, 70, 40),
    (100, 90, 65, 100, 110, 40),
    (80, 90, 65, 80, 70, 40),
    (100, 90, 65, 100, 110, 40),
    (80, 90, 65, 80, 70, 40),
    (100, 90, 65, 100, 110, 40),
    (90, 90, 65, 90, 90, 40),
]

# Pose to look "down and forward" at an object in front of the gripper,
# used before running the "what's this" color guess.
INSPECT_POSE = (94, 95, 70, 60, 90, GRIPPER_OPEN)

# Named lookup for the single-pose presets above (sequences like WAVE_SEQUENCE
# stay as lists since they're multi-step - this is for one-shot target poses
# used by calibrate.py, debug.py, and arm.move_named()).
POSES = {
    "home": HOME_POSE,
    "inspect": INSPECT_POSE,
}
# For gripper-only moves, use arm.open_gripper() / arm.close_gripper() instead
# of a named full pose - GRIPPER_OPEN / GRIPPER_CLOSED above are the values
# those use.

# ---------------------------------------------------------------------------
# Persisted pose state (see arm.py) - lets the Pi remember the last angle it
# commanded each joint to across script restarts, instead of blindly
# assuming every joint is at 90 on every boot.
# ---------------------------------------------------------------------------
STATE_FILE_PATH = "/home/bre/.volt_arm_state.json"
