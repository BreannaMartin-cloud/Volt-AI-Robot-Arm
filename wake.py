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

        # Find a capture rate this microphone actually supports. Many USB
        # mics refuse 16 kHz (they only do 44.1/48 kHz natively) and ALSA
        # fails the stream open with 'Invalid sample rate'. Vosk accepts
        # whatever rate we declare to KaldiRecognizer, so we adapt to the
        # hardware instead of demanding Vosk's preferred rate.
        self.sample_rate = self._resolve_sample_rate()
        # Keep chunk duration (~0.5 s) constant regardless of rate.
        self._block_size = int(
            config.AUDIO_BLOCK_SIZE * self.sample_rate / config.AUDIO_SAMPLE_RATE
        )
        self._recognizer = KaldiRecognizer(
            self._model,
            self.sample_rate,
            json.dumps(build_grammar()),
        )
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        log.info(
            "Vosk model loaded; capture at %d Hz; grammar: %s",
            self.sample_rate, build_grammar(),
        )

    def _resolve_sample_rate(self) -> int:
        """First capture rate the input device accepts, preferring the
        configured rate, then the device's own default, then fallbacks."""
        candidates: list = [config.AUDIO_SAMPLE_RATE]
        try:
            device_info = sd.query_devices(config.AUDIO_DEVICE, "input")
            candidates.append(int(device_info["default_samplerate"]))
        except Exception as exc:  # noqa: BLE001 - no input device at all
            raise HardwareUnavailableError(
                "microphone", f"no usable input device ({exc})"
            ) from exc
        candidates.extend(config.AUDIO_FALLBACK_SAMPLE_RATES)

        tried = []
        for rate in dict.fromkeys(candidates):  # de-dupe, keep order
            try:
                sd.check_input_settings(
                    device=config.AUDIO_DEVICE,
                    samplerate=rate,
                    channels=config.AUDIO_CHANNELS,
                    dtype="int16",
                )
            except Exception:  # noqa: BLE001 - this rate is unsupported
                tried.append(rate)
                continue
            if rate != config.AUDIO_SAMPLE_RATE:
                log.warning(
                    "microphone refused %d Hz; capturing at %d Hz instead "
                    "(Vosk resamples internally - recognition unaffected)",
                    config.AUDIO_SAMPLE_RATE, rate,
                )
            return rate
        raise HardwareUnavailableError(
            "microphone", f"no supported sample rate (tried {tried})"
        )

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            log.debug("audio stream status: %s", status)
        self._audio_queue.put(bytes(indata))

    def phrases(self, timeout_s: float | None = None) -> Iterator[str]:
        """Yield recognized phrases; stop yielding after ``timeout_s`` of
        silence (None = listen forever)."""
        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self._block_size,
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
