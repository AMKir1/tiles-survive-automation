from dataclasses import dataclass, field
from enum import Enum


class PlaybackState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


_TERMINAL_STATES = {PlaybackState.STOPPED, PlaybackState.FAILED, PlaybackState.COMPLETED}


@dataclass
class PlaybackContext:
    state: PlaybackState = PlaybackState.IDLE
    held_buttons: set[str] = field(default_factory=set)
    held_keys: set[str] = field(default_factory=set)
    error_message: str | None = None

    def start(self) -> None:
        if self.state != PlaybackState.IDLE:
            raise RuntimeError(f"cannot start from {self.state}")
        self.state = PlaybackState.RUNNING

    def complete(self) -> None:
        if self.state != PlaybackState.RUNNING:
            raise RuntimeError(f"cannot complete from {self.state}")
        self.state = PlaybackState.COMPLETED

    def fail(self, message: str) -> None:
        if self.state != PlaybackState.RUNNING:
            raise RuntimeError(f"cannot fail from {self.state}")
        self.state = PlaybackState.FAILED
        self.error_message = message

    def abort(self) -> None:
        if self.state in _TERMINAL_STATES:
            raise RuntimeError(f"cannot abort from {self.state}")
        self.state = PlaybackState.STOPPED
