"""
VOLT - wake word / voice commands

Offline speech recognition via Vosk, restricted to a small grammar (see
config.COMMAND_GRAMMAR) instead of open dictation. This is what makes
recognition of short phrases like "Hi Volt!" reliable on a Pi 4 - Vosk
only has to decide between your handful of known phrases, not transcribe
free speech.

Install:
    pip3 install vosk sounddevice

Model:
    Download a small English model (~40MB) from
    https://alphacephei.com/vosk/models - "vosk-model-small-en-us-0.15" is
    the one to grab. Unzip it and set config.VOSK_MODEL_PATH to the folder.
"""

import json
import queue
import config

try:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
except ImportError:
    sd = None
    Model = None
    KaldiRecognizer = None


COMMAND_MAP = {
    "hi volt": "greet",
    "grab volt": "grab",
    "dance volt": "dance",
    "do a shimmy volt": "shimmy",
    "what's this volt": "identify",
    "whats this volt": "identify",
}


class WakeListener:
    def __init__(self):
        if Model is None or sd is None:
            raise RuntimeError(
                "vosk / sounddevice not installed. Run: pip3 install vosk sounddevice"
            )
        self.model = Model(config.VOSK_MODEL_PATH)
        grammar = json.dumps(config.COMMAND_GRAMMAR)
        self.recognizer = KaldiRecognizer(self.model, config.AUDIO_SAMPLE_RATE, grammar)
        self.audio_queue = queue.Queue()

    def _callback(self, indata, frames, time_info, status):
        self.audio_queue.put(bytes(indata))

    def listen_for_command(self):
        """
        Blocks until a recognized command phrase comes through, then returns
        the mapped action string (one of: greet, grab, dance, shimmy,
        identify) or None if the stream produced an [unk]/empty result.
        """
        with sd.RawInputStream(
            samplerate=config.AUDIO_SAMPLE_RATE,
            blocksize=8000,
            device=config.AUDIO_DEVICE,
            dtype="int16",
            channels=1,
            callback=self._callback,
        ):
            while True:
                data = self.audio_queue.get()
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").strip()
                    if text and text != "[unk]":
                        return COMMAND_MAP.get(text)
                    # otherwise keep listening


if __name__ == "__main__":
    listener = WakeListener()
    print("Listening for: Hi Volt / Grab Volt / Dance Volt / Do a shimmy Volt / What's this Volt")
    while True:
        action = listener.listen_for_command()
        if action:
            print("Heard command ->", action)
