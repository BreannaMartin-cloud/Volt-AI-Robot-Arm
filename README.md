# Volt AI Robot Arm

A 6-DOF robot arm project with two parallel builds:

- **`arduino/`** - three standalone sketches (testing/calibration,
  color-sorting, stacking) that drive the arm directly from an Arduino.
- **`pi/`** - a Python port of the same arm control logic for a Raspberry Pi
  4 driving the servos over I2C through a PCA9685, plus voice commands
  ("Hi Volt!", "Grab Volt!", etc.), an OLED face, a buzzer, and camera-based
  vision/face-tracking.

Both talk to the same 6 joints in the same order everywhere in this repo:
**base, shoulder, elbow, wrist pitch, wrist roll, gripper.**

## Why all three Arduino sketches are for the same frame

All three sketches (`6DOF_TESTING_AND_CALIBRATION`,
`6DOF_ROBOTIC_ARM_COLOR_SORTING`, `6DOF_STACKING`) use the identical pin
map:

| Joint | Pin |
|---|---|
| Base | 3 |
| Shoulder | 5 |
| Elbow | 6 |
| Wrist pitch | 9 |
| Wrist roll | 10 |
| Gripper | 11 |

and the identical joint order and 0-180 degree convention. That's a strong
signal (not a coincidence) that they were all written against the same
physical kit/frame - this pin layout matches the common 6-DOF acrylic arm
kits sold with an Arduino example sketch using exactly these pins, and
whoever wrote the color-sorting and stacking sketches was clearly starting
from that same base sketch and layering behavior on top (the movement
helpers - `moveSmooth`, `smoothServoMove`, `moveArmSmooth` - are the same
idea reimplemented three times with small naming differences, which is
what you'd expect from incremental copies of one starting sketch rather
than three independently-designed programs).

So: if your physical wiring matches that pin table, all three sketches
should be electrically compatible with your frame. What they can't
guarantee is that the *angles* in the code line up with the true physical
position of each joint on your specific build - see below.

## The actual danger: servo horns vs. software angles

Hobby servos are open-loop - once a horn is screwed onto the servo spline,
neither the Arduino nor the Pi has any way to sense where that joint
really is. All the code can do is remember what angle it last *commanded*.
Two things follow from that:

1. **If a horn wasn't attached at exactly the angle the code assumes for
   "home"**, then commanding "elbow = 65" (or whatever the sketch calls
   home) does not put that joint where the sketch's author intended - it's
   off by however many degrees the horn was rotated from true. Most servo
   horns only index onto the spline in ~15-17 degree steps (21-25 teeth),
   so landing exactly on-angle by horn placement alone is close to
   impossible - some mismatch is normal, not a mistake you made.
2. **The moment a servo is attached/powered, it snaps at full speed toward
   whatever angle it's told**, with no ramp, regardless of where it
   physically was a moment before. The "smooth" ramping in all of these
   sketches only paces how fast *software* updates its target - it can't
   make the servo itself move gently if the very first commanded angle is
   far from the joint's true resting angle.

Put together, this is exactly the hazard you described: the arm rests
folded at the elbow with the claw down on the desk while unpowered - that's
normal, gravity plus a folded pose. The risk is what happens the instant
you power on or start a script: if the elbow's true resting angle doesn't
match what the code assumes, the very first move can be a bigger, faster,
more sudden motion than the "smooth" ramp implies, right as the claw is
sitting on (or near) the desk and possibly near your hands.

### What was changed to address this

- **Every Arduino sketch now waits for you to type `ARM`** over Serial
  before attaching any servo or moving anything. Use that pause to clear
  the area and be ready to support the arm. The first move after `ARM` also
  runs at a slower step delay than normal.
- **Every Arduino sketch now has per-joint soft limits** (`limitLoX`/
  `limitHiX` in the testing sketch, adjustable at runtime with
  `LIMIT <A-F> <lo> <hi>`) so a bad command can't drive a joint past a
  range you've confirmed is safe on your frame.
- **On the Pi side, `arm.py` never silently assumes every joint is at 90.**
  `confirm_and_home()` treats the first move of a fresh run as a genuine
  unknown, warns, and waits for you to type `arm`. It also persists the
  last commanded pose to disk so a script restart (not a power cycle)
  doesn't reset that assumption.
- **`config.py` gained `SERVO_TRIM` and `SOFT_LIMITS`**, and
  `calibrate.py` gained `trim` and `limits` commands, so you can correct
  for a horn that wasn't installed exactly on-angle without taking it back
  off the spline - see `pi/README.md`'s "Calibrating a new build" section
  for the exact steps.

### What you still need to do physically

No amount of software can substitute for actually checking, joint by
joint, where your horns landed. Do this once, with the arm supported and
the area clear:

1. Power up either the Arduino sketch or `calibrate.py` and type
   `ARM`/`arm`.
2. Command each joint to 90 (or whatever its intended home angle is) one
   at a time and look at it. If it's not where you expect, that joint's
   horn is off-angle from software's assumption - normal, not a defect.
3. Use `LIMIT`/`limits` and `trim` (or the Arduino sketch's `LIMIT`
   command) to record the real safe range and correction for that joint.
4. Only after all six joints have been checked this way should you trust
   any of the automatic sequences (color sorting, stacking, grab-and-place,
   dance) to run unattended.

## Other fixes made in this pass

- **`6DOF_TESTING_AND_CALIBRATION.ino`**: `moveSmooth` took the `Servo` by
  value instead of by reference (inconsistent with the other two sketches,
  and fragile if the function is ever extended); command parsing silently
  treated a servo letter with no digits after it as angle 0 (e.g. a stray
  `A` in the input would drive that joint to 0) - it now reports the
  problem instead of moving anywhere.
- **`6DOF_ROBOTIC_ARM_COLOR_SORTING.ino`**: `pulseIn()` on the color
  sensor had no timeout, so a miswired or flaky TCS3200 connection could
  hang the sketch indefinitely mid-motion; it now times out at 25ms and
  treats a non-response as "no reading" instead of freezing.
- **`6DOF_STACKING.ino`**: one release step called
  `moveArmSmooth(90, 73, 6+5, 64, 90, 40)` - `6+5` evaluates to `11`, not
  the `65` every surrounding line uses, which would have snapped the elbow
  to a very different angle than intended during a release step. Fixed to
  `65`. The routine also looped forever automatically before; it now runs
  once and requires `ARM` again to repeat, instead of an unattended
  infinite loop.

## Layout

```
arduino/
  6DOF_TESTING_AND_CALIBRATION/6DOF_TESTING_AND_CALIBRATION.ino
  6DOF_ROBOTIC_ARM_COLOR_SORTING/6DOF_ROBOTIC_ARM_COLOR_SORTING.ino
  6DOF_STACKING/6DOF_STACKING.ino
pi/
  config.py, arm.py, calibrate.py, main.py, track.py,
  oled.py, vision.py, buzzer.py, wake.py, debug.py, README.md
```

See `pi/README.md` for the full Raspberry Pi install/setup/voice-command
walkthrough.
