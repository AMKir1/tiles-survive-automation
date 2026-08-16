from typing import Callable

from pynput import keyboard

from tiles_survive_automation.input.ports import InputController


class EmergencyStop:
    def __init__(self, input_controller: InputController,
                 on_trigger: Callable[[], None], hotkey: str = "f9") -> None:
        self._input_controller = input_controller
        self._on_trigger = on_trigger
        self._hotkey = f"<{hotkey}>"
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        self._listener = keyboard.GlobalHotKeys({self._hotkey: self._trigger})
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()

    def _trigger(self) -> None:
        self._input_controller.release_all()
        self._on_trigger()
