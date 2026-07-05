"""
VOLT - live face tracking

Camera -> MediaPipe face detection -> face center -> proportional servo
correction -> repeat. This is the "live face tracking" milestone from your
original roadmap (image detect -> live camera detect -> track).

Simple 2-axis tracking: base joint pans left/right, shoulder tilts up/down,
enough to keep a face roughly centered - not full 6DOF gaze tracking.

Install:
    pip3 install mediapipe

Run:
    python3 track.py            # tracking + console debug line
    python3 track.py --oled     # also show a "tracking" face on the OLED
"""

import sys
import time
import cv2
import config
from arm import Arm
from debug import Debug

try:
    import mediapipe as mp
except ImportError:
    mp = None


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def run_tracking(show_oled=False):
    if mp is None:
        raise RuntimeError("mediapipe not installed. Run: pip3 install mediapipe")

    arm = Arm()
    arm.confirm_and_home()
    dbg = Debug()

    eyes = None
    if show_oled:
        from oled import Eyes
        eyes = Eyes()
        eyes.draw_open_eyes()

    face_detector = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=config.FACE_DETECTION_CONFIDENCE
    )

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    base_angle = arm.current[config.TRACK_BASE_JOINT]
    tilt_angle = arm.current[config.TRACK_TILT_JOINT]
    base_lo, base_hi = config.TRACK_BASE_LIMITS
    tilt_lo, tilt_hi = config.TRACK_TILT_LIMITS

    print("Tracking started. Ctrl+C to stop.\n")

    try:
        while True:
            dbg.tick()
            ok, frame = cap.read()
            if not ok:
                continue

            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = face_detector.process(rgb)

            faces_found = 0
            tracking = False

            if result.detections:
                faces_found = len(result.detections)
                # track the first/most confident detection
                box = result.detections[0].location_data.relative_bounding_box
                face_cx = (box.xmin + box.width / 2) * w
                face_cy = (box.ymin + box.height / 2) * h

                offset_x = face_cx - (w / 2)
                offset_y = face_cy - (h / 2)

                if abs(offset_x) > config.TRACK_DEADZONE_PX:
                    delta = clamp(offset_x * config.TRACK_GAIN, -config.TRACK_MAX_STEP_DEG, config.TRACK_MAX_STEP_DEG)
                    # camera x increasing (face moves right in frame) -> base should turn
                    # to follow it. Flip sign here if it tracks backwards on your build.
                    base_angle = clamp(base_angle + delta, base_lo, base_hi)

                if abs(offset_y) > config.TRACK_DEADZONE_PX:
                    delta = clamp(offset_y * config.TRACK_GAIN, -config.TRACK_MAX_STEP_DEG, config.TRACK_MAX_STEP_DEG)
                    tilt_angle = clamp(tilt_angle + delta, tilt_lo, tilt_hi)

                arm._write(config.TRACK_BASE_JOINT, round(base_angle))
                arm._write(config.TRACK_TILT_JOINT, round(tilt_angle))
                tracking = True

            dbg.status(
                faces=faces_found,
                tracking=tracking,
                base=round(base_angle),
                tilt=round(tilt_angle),
                state="TRACKING" if tracking else "SEARCHING",
            )

            time.sleep(0.03)  # ~30 loop cap; actual FPS reported by dbg.fps

    except KeyboardInterrupt:
        dbg.newline()
        print("Stopping tracking.")
    finally:
        cap.release()
        arm.go_home()


if __name__ == "__main__":
    run_tracking(show_oled="--oled" in sys.argv)
