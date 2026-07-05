"""VOLT robot - low-level speech recognition (Vosk).

Thin wrapper around Vosk + sounddevice that yields recognized phrases as
plain lowercase strings. Recognition is locked to a small grammar (the
wake word plus the command phrases from config) - on a Pi 4 this is what
makes short-phrase recognition fast and reliable compared to open
dictation.

Wake-word gating and command semantics live one level up in voice.py;
this module knows nothing about what the phrases mean.
"""

from __future__ import annotations

import json
import queue
from typing import Iterator, List

import config
from utils import HardwareUnavailableError, get_logger

try:
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model
except ImportError:  # pragma: no cover
    sd = KaldiRecognizer = Model = None

log = get_logger("wake")

#: Vosk's token for out-of-grammar speech.
UNKNOWN_TOKEN = "[unk]"


def build_grammar() -> List[str]:
    """The full phrase list the recognizer is allowed to output."""
    phrases = {config.WAKE_WORD, *config.VOICE_COMMANDS.keys(), UNKNOWN_TOKEN}
    return sorted(phrases)


class PhraseRecognizer:
    """Streams microphone audio into Vosk and yields recognized phrases."""

    def __init__(self) -> None:
        if Model is None or sd is None:
            raise HardwareUnavailableError(
                "microphone",
                "vosk / sounddevice not installed "
                "(pip3 install vosk sounddevice)",
            )
        try:
            self._model = Model(config.VOSK_MODEL_PATH)
        except Exception as exc:  # vosk raises bare Exception on bad path
            raise HardwareUnavailableError(
                "microphone",
                f"Vosk model not found at {config.VOSK_MODEL_PATH} "
                "(see README for the download step)",
            ) from exc
        self._recognizer = KaldiRecognizer(
            self._model,
            config.AUDIO_SAMPLE_RATE,
            json.dumps(build_grammar()),
        )
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        log.info("Vosk model loaded; grammar: %s", build_grammar())

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            log.debug("audio stream status: %s", status)
        self._audio_queue.put(bytes(indata))

    def phrases(self, timeout_s: float | None = None) -> Iterator[str]:
        """Yield recognized phrases; stop yielding after ``timeout_s`` of
        silence (None = listen forever)."""
        with sd.RawInputStream(
            samplerate=config.AUDIO_SAMPLE_RATE,
            blocksize=config.AUDIO_BLOCK_SIZE,
            device=config.AUDIO_DEVICE,
            dtype="int16",
            channels=config.AUDIO_CHANNELS,
            callback=self._on_audio,
        ):
            while True:
                try:
                    data = self._audio_queue.get(timeout=timeout_s)
                except queue.Empty:
                    return
                if not self._recognizer.AcceptWaveform(data):
                    continue
                result = json.loads(self._recognizer.Result())
                text = result.get("text", "").strip().lower()
                if text and text != UNKNOWN_TOKEN:
                    log.debug("heard: %r", text)
                    yield text


if __name__ == "__main__":
    recognizer = PhraseRecognizer()
    print(f"Grammar: {build_grammar()}")
    print("Speak a phrase (Ctrl+C to quit)...")
    try:
        for phrase in recognizer.phrases():
            print(f"-> {phrase}")
    except KeyboardInterrupt:
        print("\nBye.")
