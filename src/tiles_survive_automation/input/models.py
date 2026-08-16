from dataclasses import dataclass


@dataclass(frozen=True)
class RawEvent:
    timestamp: float
    kind: str  # mouse_down | mouse_up | scroll | key_down | key_up
    x: int | None = None
    y: int | None = None
    button: str | None = None
    key: str | None = None
    scroll_dx: int = 0
    scroll_dy: int = 0
