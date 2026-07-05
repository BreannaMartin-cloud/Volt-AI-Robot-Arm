"""
VOLT - buzzer songs

Simple passive-buzzer tone player using RPi.GPIO software PWM. Both tunes
below are original short jingles I wrote for VOLT (not transcriptions of any
existing copyrighted song) - safe to use freely and easy to tweak.

Install:
    pip3 install RPi.GPIO

Wiring: buzzer +  -> config.BUZZER_GPIO_PIN (through the transistor/resistor
if it's not a Pi-safe buzzer module), buzzer - -> GND.
"""

import time
import config

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

# Note frequencies (Hz)
NOTE = {
    "C4": 262, "D4": 294, "E4": 330, "F4": 349, "G4": 392, "A4": 440, "B4": 494,
    "C5": 523, "D5": 587, "E5": 659, "F5": 698, "G5": 784, "A5": 880,
    "REST": 0,
}

# (note, duration_seconds) - a bouncy little riff for the full Dance emote
DANCE_SONG = [
    ("C4", 0.15), ("E4", 0.15), ("G4", 0.15), ("C5", 0.25),
    ("REST", 0.05),
    ("G4", 0.15), ("E4", 0.15), ("C4", 0.15), ("G4", 0.25),
    ("REST", 0.05),
    ("A4", 0.15), ("C5", 0.15), ("A4", 0.15), ("F4", 0.3),
]

# Quicker, wigglier riff for the Shimmy emote
SHIMMY_SONG = [
    ("E4", 0.1), ("G4", 0.1), ("E4", 0.1), ("G4", 0.1),
    ("A4", 0.1), ("G4", 0.1), ("A4", 0.1), ("G4", 0.1),
    ("F4", 0.1), ("A4", 0.1), ("F4", 0.1), ("A4", 0.1),
    ("E4", 0.25),
]


class Buzzer:
    def __init__(self):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not installed. Run: pip3 install RPi.GPIO")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.BUZZER_GPIO_PIN, GPIO.OUT)
        self.pwm = GPIO.PWM(config.BUZZER_GPIO_PIN, 440)
        self._active = False

    def play_note(self, note, duration):
        freq = NOTE.get(note, 0)
        if freq == 0:
            time.sleep(duration)
            return
        if not self._active:
            self.pwm.start(50)
            self._active = True
        self.pwm.ChangeFrequency(freq)
        time.sleep(duration)

    def stop(self):
        if self._active:
            self.pwm.stop()
            self._active = False

    def play_song(self, song):
        for note, duration in song:
            self.play_note(note, duration)
        self.stop()

    def play_dance_song(self):
        self.play_song(DANCE_SONG)

    def play_shimmy_song(self):
        self.play_song(SHIMMY_SONG)

    def cleanup(self):
        self.stop()
        GPIO.cleanup(config.BUZZER_GPIO_PIN)


if __name__ == "__main__":
    b = Buzzer()
    b.play_dance_song()
    time.sleep(0.3)
    b.play_shimmy_song()
    b.cleanup()
