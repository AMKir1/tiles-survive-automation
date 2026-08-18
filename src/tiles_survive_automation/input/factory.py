import sys

from tiles_survive_automation.input.fake_input import (
    FakeInputController,
    FakeManualClickWatcher,
    NoOpInputRecorder,
)
from tiles_survive_automation.input.ports import (
    InputController,
    InputRecorder,
    ManualClickWatcher,
)


def get_input_recorder() -> InputRecorder:
    if sys.platform == "win32":
        from tiles_survive_automation.input.pynput_recorder import PynputRecorder

        return PynputRecorder()
    return NoOpInputRecorder()


def get_input_controller() -> InputController:
    if sys.platform == "win32":
        from tiles_survive_automation.input.win32_input_controller import (
            Win32InputController,
        )

        return Win32InputController()
    return FakeInputController()


def get_manual_click_watcher() -> ManualClickWatcher:
    if sys.platform == "win32":
        from tiles_survive_automation.input.win32_manual_click_watcher import (
            Win32ManualClickWatcher,
        )

        return Win32ManualClickWatcher()
    return FakeManualClickWatcher()
