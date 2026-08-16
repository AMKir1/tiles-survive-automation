import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_list_windows_returns_at_least_one_visible_window():
    from tiles_survive_automation.window.win32_window_manager import Win32WindowManager

    manager = Win32WindowManager()

    assert len(manager.list_windows()) > 0
