import time

import numpy as np

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.fake_input import FakeInputController
from tiles_survive_automation.playback.engine import PlaybackEngine
from tiles_survive_automation.playback.state import PlaybackContext, PlaybackState
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.ui.controllers.playback_controller import (
    PlaybackController,
)
from tiles_survive_automation.ui.controllers.recorder_controller import (
    RecorderController,
)
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo


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


def test_real_engine_runs_through_threaded_controller_twice_across_an_abort(qtbot, tmp_path):
    # I6: no other test composes a REAL PlaybackEngine + REAL ExecutionRepository
    # (backed by a real sqlite3 connection) through PlaybackController's actual
    # threading.Thread + QTimer path. This is specifically meant to catch
    # regressions in the C1 (check_same_thread), C2 (abort-latch reset), and C3
    # (exception handling) fixes together, since they all live in this seam.
    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 100, 100))
    window_manager = FakeWindowManager([window])
    capture = FakeScreenCapture(np.full((100, 100, 3), 10, dtype=np.uint8))
    input_controller = FakeInputController()
    repo = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    engine = PlaybackEngine(window_manager, capture, input_controller, repo, logger,
                              templates_dir=tmp_path / "templates")
    controller = PlaybackController(engine)

    step = RuleStep(id=1, order_index=0, step_type=StepType.CLICK_IMAGE, name="Click",
                     enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
                     template_path=None, confidence_threshold=0.9,
                     strategy=StrategyType.RELATIVE_ONLY, verification=None,
                     screenshot_path=None, delay_after_ms=0)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])

    # (a) Completes without the C1 sqlite3.ProgrammingError from writing to the
    # connection from the worker thread.
    with qtbot.waitSignal(controller.finished, timeout=2000) as blocker1:
        controller.run_async(rule, hwnd=1)
    assert blocker1.args[0].state == PlaybackState.COMPLETED

    # (b) After abort() + a fresh run_async() (exercising the C2 reset() fix), a
    # second run also completes successfully rather than immediately STOPPED.
    controller.abort()
    with qtbot.waitSignal(controller.finished, timeout=2000) as blocker2:
        controller.run_async(rule, hwnd=1)
    assert blocker2.args[0].state == PlaybackState.COMPLETED
