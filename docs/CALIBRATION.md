# VOLT calibration guide

Do this once after assembly, and again any time you re-seat a servo horn,
swap a servo, or change the frame. Until it's done, `main.py` will refuse
to move the robot.

Everything you measure is saved automatically to `calibration.json`
(next to the code; the previous version is backed up to
`calibration_backup.json` before every overwrite). `config.py` holds only
factory defaults and is **never edited by hand** — `calibration.apply()`
overlays your measured values at runtime.

## Why calibration is not optional

- Servo horns index onto the output spline in ~15–17° steps. When the arm
  was assembled, every horn landed *near* — but almost certainly not *at* —
  the intended angle. `SERVO_TRIM_DEG` corrects this in software.
- The servo's mechanical 0–180° sweep is wider than what the *frame* can
  safely do: joints collide with the base, the table, and each other well
  before the servo stalls. `SOFT_LIMITS_DEG` records the real safe range.
- The three poses (`HOME_POSE`, `IDLE_POSE`, `SAFE_SHUTDOWN_POSE`) ship as
  guesses. They must be verified against *your* robot.

## Setup

1. Clear the table around the arm. Nothing within a full arm's reach.
2. Have one hand free to support the forearm — the elbow servo carries the
   whole forearm/wrist/claw mass.
3. Servo power on, then:

```bash
python3 calibrate.py
```

Nothing moves at startup. Every servo stays limp until you command it.

## Procedure

### 1. Engage joints one at a time

Work from the gripper inward (lightest load first):

```
volt> gripper 90
```

You'll get a warning that powering the joint snaps it from an unknown
position; type `yes` with the arm supported. Then repeat for
`wrist_roll`, `wrist_pitch`, `elbow`, `shoulder`, `base`.

For the **elbow and shoulder**, pick your first angle near where the joint
*physically is right now* (folded ≈ low angle), not 90 — that minimizes
the engagement jump. You can estimate by eye; being 20° off at low speed
is manageable, 90° off is not.

### 2. Find each trim

For each joint, command the angle that *should* be a known physical
reference (e.g. `base 90` should face straight forward; `elbow 90` should
put the forearm perpendicular to the upper arm — use the frame's geometry):

```
volt> base 90
volt> +2
volt> +2
volt> -1
```

Nudge until physical reality matches the reference, then record the total
offset as trim:

```
volt> trim base 3
```

Trims are saved to `calibration.json` immediately — nothing to copy.
If a trim would exceed ±20°, the tool refuses: the horn is a full spline
tooth off — power down and re-seat it mechanically instead.

### 3. Find each joint's true limits

Move each joint in small steps toward each end of travel. Stop at the
first sign of the frame touching anything (or the geometry becoming
unsafe), back off a few degrees, and record:

```
volt> limits shoulder 30 150
```

Limits are saved to `calibration.json` immediately. Pay special
attention to:

- **gripper** — its mechanical stop comes long before 0/180; driving past
  it stalls and overheats the servo.
- **shoulder/elbow combinations** that put the claw into the table.

### 4. Save the three poses

```
volt> home     # factory guess - adjust joints until the claw is
volt> +2       # comfortably above the table, then:
volt> save home
```

Do the same for the idle posture (`save idle` — compact, low gravity
torque on shoulder/elbow).

For `SAFE_SHUTDOWN_POSE`: position the arm so the claw is resting at (or
a couple of degrees above) the spot it naturally falls to when unpowered,
then `save shutdown`. The goal: when power is cut in this pose, **nothing
falls**.

The moment all three poses are saved, the tool announces that
`CALIBRATED` is now true in `calibration.json` — no config edits, ever.
Check what's stored at any time with:

```
volt> show calibration
```

### 5. Test shutdown

```
volt> shutdown
```

Watch it fold. When it holds the rest pose and displays "Safe To Power
Off", cut servo power and confirm the arm doesn't move. `main.py` is now
unlocked (it re-reads `calibration.json` at startup and even while
waiting at the "Calibration Required" screen).

## Re-calibration triggers

Re-run this procedure (delete `calibration.json` first if you want the
robot locked while you work — the old file is your `calibration_backup.json`)
after:

- removing/re-seating any servo horn,
- replacing a servo,
- any crash/collision hard enough to slip a horn,
- changing the mounting surface in a way that alters the rest posture.
