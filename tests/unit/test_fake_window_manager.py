from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo


def test_list_windows_returns_configured_windows():
    windows = [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 1280, 720))]
    manager = FakeWindowManager(windows)

    assert manager.list_windows() == windows


def test_get_client_rect_returns_current_rect():
    windows = [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 1280, 720))]
    manager = FakeWindowManager(windows)

    assert manager.get_client_rect(1) == (0, 0, 1280, 720)


def test_move_window_updates_client_rect():
    windows = [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 1280, 720))]
    manager = FakeWindowManager(windows)

    manager.move_window(1, (100, 50, 1280, 720))

    assert manager.get_client_rect(1) == (100, 50, 1280, 720)


def test_exists_returns_false_for_unknown_hwnd():
    manager = FakeWindowManager([])

    assert manager.exists(999) is False


def test_activate_returns_true_for_known_hwnd():
    windows = [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 1280, 720))]
    manager = FakeWindowManager(windows)

    assert manager.activate(1) is True
    assert manager.activate(999) is False
