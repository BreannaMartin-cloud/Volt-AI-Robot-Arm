# VOLT — Voice-Operated 6DOF Desktop Robot

VOLT is a Yahboom 6DOF robot arm rebuilt as an interactive desktop robot:
voice-controlled, face-tracking, with OLED eyes, a buzzer voice, and a
safety-first motion stack — all running directly on a Raspberry Pi 4
(no Arduino).

```
"Hi Volt"  →  👀 listening…  →  "dance volt"  →  💃 + 🎵  →  back to idle
```

## Hardware

| Part | Interface | Notes |
|---|---|---|
| Yahboom 6DOF arm | — | 6 hobby servos, open-loop |
| Raspberry Pi 4 | — | runs everything |
| PCA9685 servo driver | I2C `0x40` | 16-channel PWM |
| CSI camera | CSI | face detection/tracking, motion trigger |
| 0.96" SSD1306 OLED | I2C `0x3C` | VOLT's eyes |
| Passive buzzer | GPIO 18 (BCM) | chimes and jingles |
| USB microphone | USB | offline speech recognition (Vosk) |
| ToF sensor / IMU | — | future |

### Servo channel map (the only one in the project — `config.SERVO_CHANNELS`)

| Channel | Joint |
|---|---|
| 0 | base |
| 1 | shoulder |
| 2 | elbow |
| 3 | wrist_pitch |
| 4 | wrist_roll |
| 5 | *reserved (unused)* |
| 6 | *reserved (unused)* |
| 7 | gripper |

No other file may contain a channel number. `config.validate()` enforces
the reserved channels; `debug.py` re-checks it on every run.

### Wiring

- PCA9685 → Pi: `VCC→3V3`, `GND→GND`, `SDA→GPIO2`, `SCL→GPIO3`.
- PCA9685 servo power (`V+`): **separate 5–6 V supply** rated ≥ 3 A —
  never the Pi's 5 V rail. Common ground with the Pi.
- OLED → same I2C bus (addresses don't clash: `0x40` vs `0x3C`).
- Buzzer + → GPIO 18, − → GND (through a transistor if it's a bare buzzer).

## ⚠ Read this before powering anything

Hobby servos are **open-loop**: software can never know where a joint
physically is, only what it last commanded. The moment a pulse is applied,
a servo drives at **full speed** toward the commanded angle. Additionally,
servo horns index onto their splines in ~15–17° steps, so **no joint's
"90°" should be assumed to match physical reality** until measured.

VOLT's safety model is therefore:

1. **Nothing moves at startup.** Constructing the arm attaches the PCA9685
   but applies *no pulse* — every servo stays limp. If you reboot the Pi
   with the arm assembled, the arm does not move at all.
2. **Every engagement is consented.** The first pulse to any servo happens
   only after you type `yes`, with a warning telling you exactly which
   joint will move and to where.
3. **Every angle is clamped** to per-joint soft limits (`SOFT_LIMITS_DEG`)
   and corrected by per-joint trims (`SERVO_TRIM_DEG`) at a single write
   point in `arm.py`.
4. **Every move is profiled.** `motion.py` applies trapezoidal
   velocity/acceleration limits; nothing steps instantly to a distant angle.
5. **Holding torque is never dropped automatically.** Only the manual
   `shutdown` command folds the arm to its resting pose, waits
   3 seconds, and declares "Safe To Power Off".
6. **`main.py` refuses to move an uncalibrated robot.** Until calibration
   is complete (all three poses saved, which flips `CALIBRATED` true in
   `calibration.json` automatically), it displays *"Robot Ready /
   Calibration Required"* and waits.

At rest (unpowered), this robot folds at the elbow with the claw on the
table. That's normal — and it's why `SAFE_SHUTDOWN_POSE` exists: shutdown
places the arm where gravity wants it *before* power is cut.

## Installation

```bash
sudo raspi-config          # enable I2C, Camera
sudo apt install python3-opencv python3-numpy
pip3 install -r requirements.txt --break-system-packages

# Offline speech model (~40 MB)
cd ~
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
# then point config.VOSK_MODEL_PATH at that folder
```

Verify everything (moves nothing):

```bash
python3 debug.py
```

## Calibration (required once, and after any mechanical change)

Full procedure: [docs/CALIBRATION.md](docs/CALIBRATION.md). Short version:

```bash
python3 calibrate.py
```

- `base 92` — powers *only* the base (after a confirmation) and moves it.
- `+2` / `-2` — nudge the last joint to fine-tune.
- `trim elbow 5` — record that this joint's horn is 5° off; saved to
  `calibration.json` immediately and applied to every future command.
  Trims beyond ±20° are refused — re-seat the horn instead.
- `limits shoulder 30 150` — record the true safe range on your frame
  (also saved immediately).
- `save home` / `save idle` / `save shutdown` — store the **current**
  position as that pose. `save trims`, `save all` also available.
- `show calibration` — print everything currently stored.
- `status`, `home`, `idle`, `shutdown`, `help`, `quit`.

All measurements persist to `calibration.json` (previous version backed
up to `calibration_backup.json` on every write) — `config.py` holds only
factory defaults and is never edited by hand. Once all three poses are
saved, `CALIBRATED` flips true in the file automatically and `main.py`
unlocks — it even notices while sitting at the "Calibration Required"
screen.

## Running

```bash
python3 main.py
```

Boot verifies config → PCA9685 → OLED → camera → microphone, then asks
consent before engaging the servos. After that:

**"Hi Volt"** wakes it (eyes change, confirmation beep), then say one of:

`home` · `calibrate` · `stop` · `shutdown` · `dance volt` · `shimmy volt` ·
`track me` / `follow face` · `open claw` · `close claw` · `grab object` ·
`release object` · `go idle` · `sleep` · `hi volt` (greet + wave)

After every command the robot returns to `IDLE_POSE` (servos stay powered)
and resumes its idle personality: blinking eyes and a subtle wrist
"breathing" sway.

### Shutdown

Say **"shutdown"** (or run `python3 shutdown.py`): the arm folds to
`SAFE_SHUTDOWN_POSE`, holds 3 s, plays the shutdown tone, and displays
**"Safe To Power Off."** Only then remove power.

## Project structure

```
config.py     every setting, channel, pose, threshold (factory defaults)
calibration.py  persists measured trims/limits/poses to calibration.json
utils.py      logging, state machine, shared helpers
arm.py        low-level servo I/O — the only module that touches the PCA9685
motion.py     profiled motion: velocity/accel limits, poses, gestures, lock
calibrate.py  interactive calibration REPL
vision.py     camera: face/motion/color detection
track.py      face tracking (base + wrist_pitch ONLY)
oled.py       eyes and status text (graceful without hardware)
buzzer.py     chimes and jingles (graceful without hardware)
wake.py       Vosk phrase recognition (grammar-locked)
voice.py      wake-word gating + command parsing
main.py       boot verification + top-level state machine
debug.py      read-only diagnostics
shutdown.py   standalone safe shutdown
docs/         calibration guide, architecture notes
images/ videos/  media for the portfolio write-up
```

### State machine

```
BOOTING → READY → IDLE ⇄ LISTENING → THINKING → {TRACKING_FACE, DANCING,
GRABBING, SEARCHING, …} → IDLE → … → SHUTTING_DOWN     (ERROR from anywhere)
```

One state at a time; voice, tracking, gestures and idle animations never
compete for the servos (see `utils.StateMachine` + the motion lock).

## Future upgrades

- **ToF sensor** — approach/grasp distance gating for `grab object`.
- **IMU** — base-tilt compensation and bump detection.
- **YOLO object detection** — extend `vision.py`; the `Vision` API is
  already shaped for it (methods in, plain data out).
- **Open-vocabulary voice** — swap the Vosk grammar for streaming ASR + an
  intent parser in `voice.py`; `wake.py`'s interface stays the same.
- **Inverse kinematics** — a `kinematics.py` between `motion.py` and
  behaviors, so "grab" can reach a *seen* location instead of a canned pose.
