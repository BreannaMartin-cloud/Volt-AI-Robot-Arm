# VOLT architecture

## Layering

```
                      main.py  (state machine, boot verification)
                     /   |    \
        voice.py  track.py   calibrate.py / shutdown.py / debug.py
           |         |     \      |
        wake.py   vision.py  \    |
                              motion.py   (profiles, poses, gestures, lock)
                                  |
                               arm.py     (limits, trims, engagement, persistence)
                                  |
                              PCA9685     (hardware)
config.py + utils.py underpin every layer.
```

Rules the layering enforces:

- **Only `arm.py` touches the PCA9685.** One write point applies soft
  limits and trims; there is no second path to the hardware.
- **Only `motion.py` calls `arm.set_angle` in bulk.** Behaviors ask for
  poses/gestures; they never step servos directly. (`nudge_joint` is the
  single, step-bounded exception used by tracking and breathing.)
- **`config.py` is the single source of truth for defaults.** Channels,
  trims, limits, poses, gains, thresholds. `config.validate()`
  cross-checks it all. Measured calibration lives in `calibration.json`
  and is overlaid onto config at runtime by `calibration.apply()`
  (called by `Arm.__init__`, `main.py`, and `debug.py`) — config.py is
  never hand-edited during calibration.

## Safety invariants

| Invariant | Enforced by |
|---|---|
| No pulse at startup | `Arm.__init__` never writes an angle |
| No motion without consent | `engage_joint` required per joint; REPL/CLI confirmations |
| No motion when uncalibrated | `main.py` gates on `CALIBRATED` in `calibration.json` (via `calibration.apply()`) |
| Every angle clamped | single write point `Arm._write` |
| Every trim bounded | `MAX_SAFE_TRIM_DEG`, checked in `validate()` and `calibrate.py` |
| No instantaneous jumps | trapezoidal profile in `MotionController` |
| One controller at a time | `RobotState` machine + motion `RLock` |
| Tracking moves 2 joints only | `track.py` reads joints exclusively from config; steps bounded |
| Holding torque never dropped automatically | `release_all()` exists but is called nowhere |
| Shutdown ends at gravity's rest | `SAFE_SHUTDOWN_POSE` + 3 s settle before "Safe To Power Off" |

## State machine

`utils.RobotState` / `utils.StateMachine` (thread-safe, transitions logged):

```
BOOTING → READY → IDLE
IDLE → LISTENING → THINKING → {DANCING | TRACKING_FACE | GRABBING | …} → IDLE
any → SHUTTING_DOWN (terminal)   any → ERROR
```

The idle personality (OLED blinks, wrist "breathing") runs only in `IDLE`
and acquires the motion lock non-blockingly — it can never delay or fight
a real command.

## Degradation policy

Peripherals fail soft; actuation fails hard.

- OLED/buzzer missing → `NullEyes` / `NullBuzzer` no-op stand-ins; robot
  fully functional.
- Camera/microphone missing → the behaviors needing them are unavailable;
  boot reports `warn` and everything else works.
- PCA9685 or config invalid → boot reports `FAIL` and `main.py` exits;
  there is no degraded mode for the thing that moves mass.

## Pose persistence

`arm.py` persists the last commanded pose to `STATE_FILE_PATH` after every
move. On the next run it is offered as the engagement pose — if servo
power was maintained, re-engaging there produces **zero** movement. The
file is advisory only: every consumer states that a power cycle
invalidates it, and engagement still requires explicit consent.
