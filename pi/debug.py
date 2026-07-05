"""
VOLT - debug overlay

Lightweight console debug screen, meant to be called from inside a loop
(track.py, or your own test scripts) to see what the robot is doing in
real time without needing a separate GUI.

Usage:
    from debug import Debug
    dbg = Debug()
    while True:
        dbg.tick()  # call once per loop iteration
        ...
        dbg.status(faces=1, tracking=True, base=91, tilt=88, state="TRACKING")
"""

import time


class Debug:
    def __init__(self, print_every=0.2):
        self.print_every = print_every
        self._last_print = 0.0
        self._frame_times = []

    def tick(self):
        """Call once per loop iteration to feed the FPS counter."""
        now = time.time()
        self._frame_times.append(now)
        # keep last ~1 second of timestamps
        cutoff = now - 1.0
        self._frame_times = [t for t in self._frame_times if t >= cutoff]

    @property
    def fps(self):
        return len(self._frame_times)

    def status(self, **kwargs):
        """
        Prints a single overwriting status line, throttled to print_every
        seconds so it doesn't flood the terminal.

        e.g. dbg.status(faces=1, tracking=True, base=91, tilt=88, state="TRACKING")
        -> FPS: 28 | faces: 1 | tracking: True | base: 91 | tilt: 88 | state: TRACKING
        """
        now = time.time()
        if now - self._last_print < self.print_every:
            return
        self._last_print = now

        parts = [f"FPS: {self.fps}"]
        for key, value in kwargs.items():
            parts.append(f"{key}: {value}")
        line = " | ".join(parts)
        print("\r" + line + " " * 10, end="", flush=True)

    def newline(self):
        print()
