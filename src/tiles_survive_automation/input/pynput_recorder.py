import time
from typing import Callable

from pynput import keyboard, mouse

from tiles_survive_automation.input.models import RawEvent

_BUTTON_NAMES = {
    "Button.left": "left",
    "Button.right": "right",
    "Button.middle": "middle",
}


class PynputRecorder:
    def __init__(self) -> None:
        self._on_event: Callable[[RawEvent], None] | None = None
        self._paused = False
        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None

    def start(self, on_event: Callable[[RawEvent], None]) -> None:
        self._on_event = on_event
        self._paused = False
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click_raw, on_scroll=self._on_scroll_raw,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_down_raw, on_release=self._on_key_up_raw,
        )
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._keyboard_listener is not None:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass

    def _emit(self, event: RawEvent) -> None:
        if self._paused or self._on_event is None:
            return
        self._on_event(event)

    def _on_click_raw(self, x, y, button, pressed) -> None:
        self._on_click(x, y, str(button), pressed)

    def _on_click(self, x: int, y: int, button_repr: str, pressed: bool) -> None:
        button = _BUTTON_NAMES.get(button_repr, "left")
        kind = "mouse_down" if pressed else "mouse_up"
        self._emit(RawEvent(timestamp=time.perf_counter(), kind=kind, x=x, y=y,
                             button=button))

    def _on_scroll_raw(self, x, y, dx, dy) -> None:
        self._on_scroll(x, y, dx, dy)

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._emit(RawEvent(timestamp=time.perf_counter(), kind="scroll", x=x, y=y,
                             scroll_dx=dx, scroll_dy=dy))

    def _on_key_down_raw(self, key) -> None:
        self._on_key_down(_key_name(key))

    def _on_key_down(self, key: str) -> None:
        self._emit(RawEvent(timestamp=time.perf_counter(), kind="key_down", key=key))

    def _on_key_up_raw(self, key) -> None:
        self._on_key_up(_key_name(key))

    def _on_key_up(self, key: str) -> None:
        self._emit(RawEvent(timestamp=time.perf_counter(), kind="key_up", key=key))


def _key_name(key) -> str:
    return getattr(key, "char", None) or str(key).replace("Key.", "")
