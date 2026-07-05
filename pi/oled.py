"""
VOLT - OLED display (eyes + status text)

Install:
    pip3 install luma.oled

If you'd rather use adafruit-circuitpython-ssd1306 instead, the draw calls
below (self.draw) are just PIL ImageDraw, so most of this ports over with
minor changes to device init - only replace __init__.
"""

import time
import threading
import config

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306


class Eyes:
    def __init__(self):
        serial = i2c(port=1, address=config.OLED_I2C_ADDRESS)
        self.device = ssd1306(serial, width=config.OLED_WIDTH, height=config.OLED_HEIGHT)
        self._stop_idle = threading.Event()
        self._idle_thread = None

    # ---- primitive frames ----

    def draw_open_eyes(self):
        w, h = self.device.width, self.device.height
        cy = h // 2
        eye_w, eye_h = 20, 26
        gap = 16
        cx1 = w // 2 - gap // 2 - eye_w // 2
        cx2 = w // 2 + gap // 2 + eye_w // 2
        with canvas(self.device) as draw:
            draw.ellipse((cx1 - eye_w // 2, cy - eye_h // 2, cx1 + eye_w // 2, cy + eye_h // 2), fill="white")
            draw.ellipse((cx2 - eye_w // 2, cy - eye_h // 2, cx2 + eye_w // 2, cy + eye_h // 2), fill="white")

    def draw_blink(self):
        w, h = self.device.width, self.device.height
        cy = h // 2
        eye_w = 20
        gap = 16
        cx1 = w // 2 - gap // 2 - eye_w // 2
        cx2 = w // 2 + gap // 2 + eye_w // 2
        with canvas(self.device) as draw:
            draw.line((cx1 - eye_w // 2, cy, cx1 + eye_w // 2, cy), fill="white", width=3)
            draw.line((cx2 - eye_w // 2, cy, cx2 + eye_w // 2, cy), fill="white", width=3)

    def draw_happy_eyes(self):
        """Upward curved arcs, used for dance/shimmy/greeting."""
        w, h = self.device.width, self.device.height
        cy = h // 2
        gap = 16
        eye_w = 22
        cx1 = w // 2 - gap // 2 - eye_w // 2
        cx2 = w // 2 + gap // 2 + eye_w // 2
        with canvas(self.device) as draw:
            draw.arc((cx1 - eye_w // 2, cy - 10, cx1 + eye_w // 2, cy + 20), start=200, end=340, fill="white", width=3)
            draw.arc((cx2 - eye_w // 2, cy - 10, cx2 + eye_w // 2, cy + 20), start=200, end=340, fill="white", width=3)

    def draw_confused(self):
        """One eye normal, one eyebrow-raised - used when grab/identify comes up empty."""
        w, h = self.device.width, self.device.height
        cy = h // 2
        eye_w, eye_h = 20, 26
        gap = 16
        cx1 = w // 2 - gap // 2 - eye_w // 2
        cx2 = w // 2 + gap // 2 + eye_w // 2
        with canvas(self.device) as draw:
            draw.ellipse((cx1 - eye_w // 2, cy - eye_h // 2, cx1 + eye_w // 2, cy + eye_h // 2), fill="white")
            draw.ellipse((cx2 - eye_w // 2, cy - eye_h // 2 + 6, cx2 + eye_w // 2, cy + eye_h // 2 - 6), fill="white")
            draw.line((cx2 - eye_w // 2 - 2, cy - eye_h // 2 - 4, cx2 + eye_w // 2 + 2, cy - eye_h // 2 - 8), fill="white", width=2)

    def draw_tracking(self):
        """Small crosshair under the eyes, used during live face tracking."""
        self.draw_open_eyes()
        w, h = self.device.width, self.device.height
        with canvas(self.device) as draw:
            draw.text((w // 2 - 24, h - 14), "tracking...", fill="white")

    def draw_listening(self):
        """Small pulsing dots under the eyes to show VOLT is listening."""
        self.draw_open_eyes()
        w, h = self.device.width, self.device.height
        with canvas(self.device) as draw:
            draw.text((w // 2 - 18, h - 14), "listening...", fill="white")

    def draw_thinking(self):
        w, h = self.device.width, self.device.height
        with canvas(self.device) as draw:
            draw.text((w // 2 - 20, h // 2 - 4), "thinking...", fill="white")

    def draw_text_screen(self, line1, line2=""):
        w, h = self.device.width, self.device.height
        with canvas(self.device) as draw:
            draw.text((4, h // 2 - 14), line1, fill="white")
            if line2:
                draw.text((4, h // 2 + 2), line2, fill="white")

    # ---- idle animation (blink every few seconds) ----

    def start_idle(self):
        self._stop_idle.clear()
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._idle_thread.start()

    def stop_idle(self):
        self._stop_idle.set()
        if self._idle_thread:
            self._idle_thread.join(timeout=1)

    def _idle_loop(self):
        self.draw_open_eyes()
        while not self._stop_idle.is_set():
            time.sleep(4)
            if self._stop_idle.is_set():
                break
            self.draw_blink()
            time.sleep(0.15)
            self.draw_open_eyes()


if __name__ == "__main__":
    eyes = Eyes()
    eyes.draw_open_eyes()
    time.sleep(1)
    eyes.draw_blink()
    time.sleep(0.3)
    eyes.draw_happy_eyes()
    time.sleep(1)
    eyes.draw_text_screen("Hi, I'm VOLT!")
