import sys

from tiles_survive_automation.input.factory import (
    get_input_controller,
    get_input_recorder,
    get_manual_click_watcher,
)


def test_get_input_recorder_returns_noop_on_non_windows():
    if sys.platform == "win32":
        return

    from tiles_survive_automation.input.fake_input import NoOpInputRecorder

    assert isinstance(get_input_recorder(), NoOpInputRecorder)


def test_get_input_controller_returns_fake_on_non_windows():
    if sys.platform == "win32":
        return

    from tiles_survive_automation.input.fake_input import FakeInputController

    assert isinstance(get_input_controller(), FakeInputController)


def test_get_manual_click_watcher_returns_fake_on_non_windows():
    if sys.platform == "win32":
        return

    from tiles_survive_automation.input.fake_input import FakeManualClickWatcher

    assert isinstance(get_manual_click_watcher(), FakeManualClickWatcher)
