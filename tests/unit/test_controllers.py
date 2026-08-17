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
    def __init__(self):
        self.reset_calls = 0

    def run(self, rule, hwnd):
        context = PlaybackContext()
        context.start()
        context.complete()
        return context

    def abort(self):
        self.aborted = True

    def reset(self):
        self.reset_calls += 1


class RaisingEngine:
    def run(self, rule, hwnd):
        raise RuntimeError("boom")

    def abort(self):
        self.aborted = True

    def reset(self):
        pass


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


def test_playback_controller_run_async_calls_reset_before_starting(qtbot):
    engine = DummyEngine()
    controller = PlaybackController(engine)

    with qtbot.waitSignal(controller.finished, timeout=1000):
        controller.run_async(rule=object(), hwnd=1)

    assert engine.reset_calls == 1


def test_playback_controller_two_runs_with_abort_between_both_complete(qtbot):
    # Exercises the C2 fix: engine.abort() should not permanently latch
    # run_async() into always returning STOPPED for subsequent runs.
    engine = DummyEngine()
    controller = PlaybackController(engine)

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker1:
        controller.run_async(rule=object(), hwnd=1)
    assert blocker1.args[0].state == PlaybackState.COMPLETED

    controller.abort()

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker2:
        controller.run_async(rule=object(), hwnd=1)
    assert blocker2.args[0].state == PlaybackState.COMPLETED
    assert engine.reset_calls == 2


def test_playback_controller_emits_finished_even_when_engine_raises(qtbot):
    engine = RaisingEngine()
    controller = PlaybackController(engine)

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker:
        controller.run_async(rule=object(), hwnd=1)

    context = blocker.args[0]
    assert context.state == PlaybackState.FAILED
