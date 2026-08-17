import sys

from tiles_survive_automation.input.fake_input import FakeInputController, NoOpInputRecorder
from tiles_survive_automation.input.ports import InputController, InputRecorder


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
