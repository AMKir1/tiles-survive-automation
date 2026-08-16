import sys

from tiles_survive_automation.window.factory import get_window_manager


def test_get_window_manager_returns_fake_on_non_windows():
    if sys.platform == "win32":
        return

    from tiles_survive_automation.window.fake_window_manager import FakeWindowManager

    assert isinstance(get_window_manager(), FakeWindowManager)
