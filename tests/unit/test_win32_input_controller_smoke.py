# tests/unit/test_win32_input_controller_smoke.py
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_release_all_clears_held_state_without_raising():
    from tiles_survive_automation.input.win32_input_controller import (
        Win32InputController,
    )

    controller = Win32InputController()
    controller.press_and_hold("left")

    controller.release_all()

    assert controller._held_buttons == set()
