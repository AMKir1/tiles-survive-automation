import sys

from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowManager


def get_window_manager() -> WindowManager:
    if sys.platform == "win32":
        from tiles_survive_automation.window.win32_window_manager import (
            Win32WindowManager,
        )

        return Win32WindowManager()
    return FakeWindowManager([])
