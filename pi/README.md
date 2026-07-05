# VOLT - voice-controlled 6DOF arm (Raspberry Pi 4B)

Python port of your Arduino sequences (`6DOF_TESTING_AND_CALIBRATION.ino`,
`6DOF_ROBOTIC_ARM_COLOR_SORTING.ino`, `6DOF-stacking.ino`), driven off the Pi
instead of the Arduino, with mic-based wake/command detection added per your
objectives sheet.

## Read this before you power anything on

Hobby servos have no position feedback - nothing in this code (or in the
Arduino sketches) can ever know the arm's true physical angle, only what
angle it last *told* a servo to go to. If a servo horn was attached to its
spline at some angle other than exactly what the code calls "90", every
pose in `config.py` is off by however much that joint is mis-indexed - and
because the elbow joint is what the forearm/wrist/gripper hang from when
the arm is folded at rest, a mismatch there is the one most likely to
produce a sudden, larger-than-expected move the instant power/signal is
applied.

That's why `arm.py`'s `confirm_and_home()` (used by `main.py`, `track.py`,
and `calibrate.py` instead of a plain `go_home()`) won't move anything on a
truly fresh run without you typing `arm` first - use that pause to clear
the area and be ready to support the arm. It's also why `calibrate.py` has
`trim` and `limits` commands: run through those once, per joint, before
trusting any of this to move on its own. See "Calibrating a new build"
below for the actual step-by-step.

## Commands implemented

| Say | What happens |
|---|---|
| "Hi Volt!" | Wave gesture + happy eyes on OLED |
| "Grab Volt!" | Watches camera for motion/an object, runs pick-and-place sequence |
| "Dance Volt!" | Dance sequence + buzzer jingle |
| "Do a shimmy Volt!" | Shimmy sequence + a different buzzer jingle |
| "What's this Volt?" | Looks at object, guesses its color, shows guess on OLED |

## Files

| File | Purpose |
|---|---|
| `config.py` | all settings, pin/channel maps, poses, sequences |
| `arm.py` | PCA9685 servo control - all 6 joints move **simultaneously** now |
| `oled.py` | eyes: open, blink, happy, thinking, listening, confused, tracking |
| `buzzer.py` | dance/shimmy jingles |
| `vision.py` | motion detection (grab trigger) + object identification |
| `wake.py` | Vosk grammar-based voice commands |
| `main.py` | ties it all together into the voice-command loop |
| `calibrate.py` | interactive joint-by-joint tuning tool |
| `track.py` | live face tracking (MediaPipe) - separate mode from voice commands |
| `debug.py` | console FPS/status overlay, used by `track.py` |

## Install

```bash
pip3 install adafruit-circuitpython-servokit luma.oled RPi.GPIO vosk sounddevice mediapipe --break-system-packages
```

(opencv/numpy you already have installed)

Download a Vosk model (offline speech recognition):
```bash
cd ~
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```
Then set `VOSK_MODEL_PATH` in `config.py` to that folder's path.

Download the MobileNet-SSD model for real "What's this Volt?" detection
(optional - without it, identify falls back to the color guess automatically):
```bash
mkdir -p ~/models && cd ~/models
wget https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt -O MobileNetSSD_deploy.prototxt
wget https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel -O MobileNetSSD_deploy.caffemodel
```
Then set `SSD_PROTOTXT` / `SSD_MODEL` in `config.py` to match. Note this
model only knows 20 general object classes (bottle, chair, cat, person,
etc.) - it won't recognize everything, but it's real detection rather than
a color heuristic.

## Before running

1. **Check `SERVO_CHANNELS` in `config.py`** - I assumed PCA9685 channels 0-5
   map to base/shoulder/elbow/wristPitch/wristRoll/gripper in that order,
   matching your Arduino pin order. Confirm this against your actual wiring.
2. **Check `BUZZER_GPIO_PIN`** - set to whatever GPIO your buzzer is on.
3. **Check mic works**: `python3 -c "import sounddevice as sd; print(sd.query_devices())"`
   and set `AUDIO_DEVICE` in `config.py` if you've got more than one input
   device and the default isn't the right mic.
4. **Calibrate every joint** - see "Calibrating a new build" below. Do this
   before running `main.py` unattended, and definitely before "Grab Volt"
   or "Dance Volt" ever run on their own from a voice command.

## Calibrating a new build

Run this once (and again any time you re-seat a horn or re-string the arm):

```bash
python3 calibrate.py
```

1. Type `arm` at the safe-boot prompt. The arm will home slowly - watch it,
   don't assume it'll behave.
2. Type `pose` to see what the software thinks every joint's angle is.
3. Move one joint at a time (e.g. `elbow 90`) and compare the number to
   where the joint physically ends up. If "90" doesn't look like the
   middle of that joint's travel (or wherever you want its zero to be),
   the horn wasn't installed exactly on-angle - that's expected, hobby
   servo horns only index in ~15-17 degree steps.
4. Use `trim <joint> <delta>` to nudge the correction until the numbers
   match reality - e.g. if commanding `elbow 90` visibly sits a bit low,
   try `trim elbow 5` and check again. It prints a ready-to-paste line for
   `config.SERVO_TRIM` when you're done.
5. Use `limits <joint> <lo> <hi>` once you've found, by testing carefully
   in small steps, the actual safe range for that joint on your frame
   (where it starts colliding with the base, the desk, or another link).
   It prints a ready-to-paste line for `config.SOFT_LIMITS`.
6. Once every joint's trim and limits are dialed in and pasted into
   `config.py`, use `save <name>` at any pose you like to get a
   ready-to-paste `config.POSES` entry - handy for a known-good rest pose
   that isn't necessarily `HOME_POSE`.

## Testing pieces individually

Each module runs standalone for isolated testing:
```bash
python3 arm.py         # homes, then waves (now moves all joints together)
python3 oled.py        # cycles through eye states
python3 buzzer.py      # plays both jingles
python3 vision.py      # 10s motion test + object identification
python3 wake.py        # prints recognized commands, no hardware needed
python3 calibrate.py   # interactive joint tuning - type "shoulder 94" etc.
python3 track.py       # live face tracking with console debug line
python3 track.py --oled  # same, plus a "tracking..." eye state on the OLED
```

Once each piece works on its own:
```bash
python3 main.py
```

`track.py` is a separate mode from `main.py` - it's for continuous face
tracking (uses the camera the whole time), while `main.py` runs the
voice-command loop where the camera is only used briefly for grab/identify.
They're not meant to run at the same time (both want the camera).

## What changed in this pass

Safety-focused changes, prompted by "the arm rests folded on its elbow with
the claw on the desk when unpowered, and I'm not sure which angle the
servos were installed at":
- **`confirm_and_home()`** (`arm.py`) replaces silently calling `go_home()`
  on startup. The first move after a fresh process start (no saved pose on
  disk) now warns loudly and waits for you to type `arm` before attaching/
  moving anything, then homes at a slower step delay for that one move.
  `main.py` and `track.py` both use it now instead of `go_home()`.
- **Persisted pose state** (`arm.py`'s `_load_state`/`_save_state`, backed
  by `config.STATE_FILE_PATH`) - the last commanded angle for every joint
  is written to disk after each move, so a script restart (not a power
  cycle) doesn't reset to an assumed pose of "everything is at 90".
- **`SERVO_TRIM` and `SOFT_LIMITS`** (`config.py`) - per-joint calibration
  offset and safe angle range, applied in `arm._write()`. `calibrate.py`
  gained `trim` and `limits` commands to find and paste these in. Trim is
  applied only to the physical pulse, never fed back into the tracked
  logical angle, so repeated moves don't compound it.

Fixed based on your friend's review:
- **Simultaneous joint motion** - `move_pose_smooth()` now ramps all 6
  servos together over the same duration instead of moving one joint fully
  before the next starts. This is the one that most affects how natural
  the arm looks.
- **Named poses** - `config.POSES` dict + `arm.move_named("home")`, and
  `calibrate.py`'s `save <name>` command prints a ready-to-paste POSES entry.
- **Calibration utility** - `calibrate.py`, direct port of the interactive
  style from `6DOF_TESTING_AND_CALIBRATION.ino` but with named joints.
- **Live face tracking** - `track.py`, using MediaPipe face detection with
  a simple proportional pan/tilt controller. This was your actual next
  roadmap milestone (image detect -> live camera detect -> track).
- **Debug screen** - `debug.py`, gives a live FPS/state status line, wired
  into `track.py`.
- **Real object detection** - `vision.py`'s `identify_object()` now uses
  MobileNet-SSD when the model files are present, falling back to the
  color guess automatically if they're not (see Install above).
- **More OLED expressions** - added confused (used when grab finds nothing)
  and tracking states.

Not changed, on purpose:
- Haar Cascades - never present in this codebase; that critique applied to
  earlier standalone scripts (`face_test.py`), not this project.
- Open-ended voice intent parsing ("grab the blue bottle") - would need a
  full ASR + NLU pipeline instead of grammar-locked Vosk; worth doing later
  but a separate, bigger project than this pass.

## Known limitations / next steps

- **Grab Volt** still uses motion detection to *trigger* a fixed
  pick-and-place arc, not true vision-guided reaching to a specific object
  location - that needs inverse kinematics, still on your roadmap. `track.py`
  is a step toward this (it proves out camera->servo closed-loop control),
  but grab and reach aren't unified yet.
- **What's this Volt** with the SSD model only knows 20 general object
  classes - good for bottle/chair/cat/person, not everything you might
  hold up to it.
- Vosk grammar recognition means VOLT is only listening for your exact
  five phrases - it won't respond to "volt" alone as a bare wake word
  followed by an open command. If you want true always-listening bare
  "Volt" wake detection later, openWakeWord (already in your BMO stack)
  is the right tool for that.
