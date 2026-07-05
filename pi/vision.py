"""
VOLT - vision helpers

Two jobs for now, matching what's in your notes:

1. wait_for_wave_or_object() - watches the camera feed for motion/an object
   in front of the arm, to trigger the "Grab Volt" pick-and-place sequence.
   This is frame-differencing motion detection, not gesture recognition -
   good enough to know "something is there and moving," which is what your
   notes describe ("detect any object that is waving or in front of it").

2. guess_object_color() - captures a frame and reports the dominant color
   in the center region (red/green/blue/yellow/unknown), used for
   "What's this Volt?" Because your Arduino color-sort logic used a TCS3200
   color sensor that isn't wired into the Pi build, this reuses the same
   red/green/blue idea but reads it from the camera image instead.

Honest caveat: this is a heuristic color guess, not real object
identification. True object recognition (telling a cup from a phone from a
block) needs a trained detection model - that's your "Object detection"
roadmap item. When you get there, swap guess_object_color() out for
something like OpenCV's DNN module with a MobileNet-SSD model, and this
function signature can stay the same so main.py doesn't need to change.
"""

import os
import time
import cv2
import numpy as np
import config

# MobileNet-SSD class labels (Caffe model, 20 VOC classes + background)
SSD_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
    "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
    "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor",
]


class Vision:
    def __init__(self):
        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

        # Real object detection (MobileNet-SSD), loaded only if the model
        # files are present - see README for the download step. If they're
        # missing, identify_object() gracefully falls back to the color
        # guess so nothing crashes on a fresh setup.
        self.net = None
        if os.path.exists(config.SSD_PROTOTXT) and os.path.exists(config.SSD_MODEL):
            self.net = cv2.dnn.readNetFromCaffe(config.SSD_PROTOTXT, config.SSD_MODEL)

    def _read_gray(self):
        ok, frame = self.cap.read()
        if not ok:
            return None, None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        return frame, gray

    def wait_for_wave_or_object(self, timeout=None):
        """
        Blocks (polling) until motion above WAVE_MOTION_THRESHOLD is seen on
        WAVE_CONFIRM_FRAMES consecutive checks, or timeout (seconds) elapses.
        Returns True if triggered, False if it timed out.
        """
        _, prev_gray = self._read_gray()
        if prev_gray is None:
            return False

        confirm_count = 0
        start = time.time()

        while True:
            if timeout is not None and (time.time() - start) > timeout:
                return False

            _, gray = self._read_gray()
            if gray is None:
                continue

            diff = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
            motion_score = int(np.sum(thresh) / 255)

            if motion_score > config.WAVE_MOTION_THRESHOLD:
                confirm_count += 1
            else:
                confirm_count = 0

            if confirm_count >= config.WAVE_CONFIRM_FRAMES:
                return True

            prev_gray = gray
            time.sleep(0.05)

    def guess_object_color(self):
        """Returns one of: 'red', 'green', 'blue', 'yellow', 'unknown'."""
        ok, frame = self.cap.read()
        if not ok:
            return "unknown"

        h, w, _ = frame.shape
        cx1, cx2 = int(w * 0.4), int(w * 0.6)
        cy1, cy2 = int(h * 0.4), int(h * 0.6)
        center = frame[cy1:cy2, cx1:cx2]

        hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
        avg_h = float(np.mean(hsv[:, :, 0]))
        avg_s = float(np.mean(hsv[:, :, 1]))
        avg_v = float(np.mean(hsv[:, :, 2]))

        if avg_s < 40 or avg_v < 40:
            return "unknown"

        # OpenCV hue range is 0-179
        if avg_h < 10 or avg_h > 170:
            return "red"
        elif 10 <= avg_h < 35:
            return "yellow"
        elif 35 <= avg_h < 85:
            return "green"
        elif 85 <= avg_h < 130:
            return "blue"
        return "unknown"

    def identify_object(self):
        """
        Real object detection when the SSD model is available (returns a
        label like 'bottle', 'cup' isn't in this 20-class set so common
        household items are hit-or-miss - see README for swapping in a
        bigger model later). Falls back to guess_object_color() if the
        model files aren't downloaded.

        Returns (label, confidence) - confidence is None for the color
        fallback since it's a heuristic, not a real detection score.
        """
        if self.net is None:
            return self.guess_object_color(), None

        ok, frame = self.cap.read()
        if not ok:
            return "unknown", None

        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()

        best_label = "unknown"
        best_conf = 0.0
        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            if confidence > best_conf and confidence > 0.4:
                class_id = int(detections[0, 0, i, 1])
                if 0 <= class_id < len(SSD_CLASSES):
                    best_label = SSD_CLASSES[class_id]
                    best_conf = confidence

        if best_label in ("background", "unknown"):
            return self.guess_object_color(), None
        return best_label, best_conf

    def release(self):
        self.cap.release()


if __name__ == "__main__":
    v = Vision()
    print("Watching for motion (10s test)...")
    triggered = v.wait_for_wave_or_object(timeout=10)
    print("Triggered!" if triggered else "No motion seen.")
    print("Color guess:", v.guess_object_color())
    v.release()
