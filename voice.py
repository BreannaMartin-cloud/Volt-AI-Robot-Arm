"""VOLT robot - voice control.

Sits between the raw phrase stream (wake.py) and the state machine
(main.py). Implements the interaction contract:

1. All speech is IGNORED until the wake word ("hi volt") is heard.
2. After the wake word, listen for exactly ONE command, for at most
   ``COMMAND_TIMEOUT_S`` seconds.
3. Return the parsed command (or a timeout/greet result) to the caller,
   which executes it and returns the robot to idle.

This module performs no motion and touches no hardware other than the
microphone - it only *reports* what the human asked for.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional

import config
from utils import get_logger
from wake import PhraseRecognizer

log = get_logger("voice")


class Command(enum.Enum):
    """Canonical voice commands (values match config.VOICE_COMMANDS)."""

    GREET = "greet"
    HOME = "home"
    CALIBRATE = "calibrate"
    STOP = "stop"
    SHUTDOWN = "shutdown"
    DANCE = "dance"
    SHIMMY = "shimmy"
    TRACK = "track"
    OPEN_CLAW = "open_claw"
    CLOSE_CLAW = "close_claw"
    GRAB = "grab"
    RELEASE = "release"
    IDLE = "idle"
    SLEEP = "sleep"


@dataclass
class VoiceEvent:
    """Outcome of one wake-word interaction."""

    command: Optional[Command]  # None = timed out waiting for a command
    phrase: str                 # raw phrase heard ("" on timeout)


def parse_command(phrase: str) -> Optional[Command]:
    """Map a recognized phrase to a :class:`Command`, if it is one."""
    name = config.VOICE_COMMANDS.get(phrase.strip().lower())
    if name is None:
        return None
    try:
        return Command(name)
    except ValueError:
        log.error("config maps %r to unknown command %r", phrase, name)
        return None


class VoiceController:
    """Wake-word-gated, one-command-at-a-time voice interface."""

    def __init__(self, recognizer: Optional[PhraseRecognizer] = None) -> None:
        self._recognizer = recognizer or PhraseRecognizer()

    def wait_for_wake_word(self) -> None:
        """Block until the wake word is heard; everything else is ignored."""
        log.info("waiting for wake word %r", config.WAKE_WORD)
        for phrase in self._recognizer.phrases():
            if phrase == config.WAKE_WORD:
                log.info("wake word detected")
                return
            log.debug("ignoring %r (not awake)", phrase)

    def listen_for_command(self) -> VoiceEvent:
        """After the wake word: capture at most one command, then return.

        A second "hi volt" while listening is the greeting command. An
        unrecognized in-grammar phrase keeps listening until the timeout.
        """
        log.info("listening for one command (%.0fs timeout)", config.COMMAND_TIMEOUT_S)
        for phrase in self._recognizer.phrases(timeout_s=config.COMMAND_TIMEOUT_S):
            command = parse_command(phrase)
            if command is not None:
                log.info("command: %s (%r)", command.name, phrase)
                return VoiceEvent(command=command, phrase=phrase)
            log.debug("not a command: %r", phrase)
        log.info("no command before timeout")
        return VoiceEvent(command=None, phrase="")

    def next_interaction(self) -> VoiceEvent:
        """One full interaction: wait for wake word, then one command."""
        self.wait_for_wake_word()
        return self.listen_for_command()


if __name__ == "__main__":
    controller = VoiceController()
    print(f"Say {config.WAKE_WORD!r}, then a command. Ctrl+C to quit.")
    try:
        while True:
            event = controller.next_interaction()
            if event.command:
                print(f"-> {event.command.name}")
            else:
                print("-> (timed out)")
    except KeyboardInterrupt:
        print("\nBye.")
