import time

from tiles_survive_automation.playback.state import PlaybackContext, PlaybackState
from tiles_survive_automation.ui.controllers.playback_controller import (
    PlaybackController,
)
from tiles_survive_automation.ui.controllers.recorder_controller import (
    RecorderController,
)


class DummySession:
    def start(self, hwnd):
        self.started_hwnd = hwnd

    def pause(self):
        self.paused = True

    def resume(self):
        self.resumed = True

    def stop(self):
        return ["step-1", "step-2"]


class DummyEngine:
    def run(self, rule, hwnd):
        context = PlaybackContext()
        context.start()
        context.complete()
        return context

    def abort(self):
        self.aborted = True


def test_recorder_controller_start_delegates_to_session(qtbot):
    session = DummySession()
    controller = RecorderController(session)

    with qtbot.waitSignal(controller.started, timeout=1000):
        controller.start(hwnd=42)

    assert session.started_hwnd == 42


def test_recorder_controller_stop_emits_recorded_steps(qtbot):
    session = DummySession()
    controller = RecorderController(session)
    controller.start(hwnd=1)

    with qtbot.waitSignal(controller.stopped, timeout=1000) as blocker:
        controller.stop()

    assert blocker.args == [["step-1", "step-2"]]


def test_playback_controller_run_async_emits_finished_context(qtbot):
    engine = DummyEngine()
    controller = PlaybackController(engine)

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker:
        controller.run_async(rule=object(), hwnd=1)

    context = blocker.args[0]
    assert context.state == PlaybackState.COMPLETED


def test_playback_controller_abort_delegates_to_engine(qtbot):
    engine = DummyEngine()
    controller = PlaybackController(engine)

    controller.abort()

    assert engine.aborted is True
