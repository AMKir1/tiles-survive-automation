from PySide6.QtCore import QObject, Signal

from tiles_survive_automation.playback.state import PlaybackContext, PlaybackState
from tiles_survive_automation.ui.controllers.schedule_controller import (
    ScheduleController,
)


class FakePlaybackController(QObject):
    """Records run_async() calls; the test manually emits `finished` to
    simulate each run's outcome, since ScheduleController only cares about
    the signal/call contract, not real playback."""

    finished = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.run_calls: list[tuple] = []

    def run_async(self, rule, hwnd) -> None:
        self.run_calls.append((rule, hwnd))

    def complete_last_run(self) -> None:
        context = PlaybackContext()
        context.start()
        context.complete()
        self.finished.emit(context)

    def fail_last_run(self, message: str = "boom") -> None:
        context = PlaybackContext()
        context.start()
        context.fail(message)
        self.finished.emit(context)

    def stop_last_run(self) -> None:
        context = PlaybackContext()
        context.start()
        context.abort()
        self.finished.emit(context)


def test_start_runs_first_execution_immediately(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)

    controller.start(rule="R", hwnd=1, total_runs=3, batch_size=5, batch_interval_ms=1000)

    assert playback.run_calls == [("R", 1)]
    assert controller.is_active() is True


def test_completions_within_a_batch_continue_immediately_without_timer(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)
    controller.start(rule="R", hwnd=1, total_runs=10, batch_size=5, batch_interval_ms=60000)

    playback.complete_last_run()  # run 1 of batch done -> run 2 starts immediately
    playback.complete_last_run()  # run 2 done -> run 3
    playback.complete_last_run()  # run 3 done -> run 4

    assert len(playback.run_calls) == 4
    assert controller._batch_timer.isActive() is False


def test_batch_boundary_schedules_next_batch_via_timer_not_immediately(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)
    controller.start(rule="R", hwnd=1, total_runs=10, batch_size=2, batch_interval_ms=60000)

    playback.complete_last_run()  # run 1 done -> run 2 starts immediately (still batch 1)
    assert len(playback.run_calls) == 2

    playback.complete_last_run()  # run 2 done -> batch boundary, run 3 must wait for the timer
    assert len(playback.run_calls) == 2
    assert controller._batch_timer.isActive() is True


def test_batch_timer_firing_starts_the_next_run(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)
    controller.start(rule="R", hwnd=1, total_runs=10, batch_size=1, batch_interval_ms=30)

    playback.complete_last_run()  # batch of 1 -> immediately schedules the timer
    assert len(playback.run_calls) == 1

    qtbot.wait(100)

    assert len(playback.run_calls) == 2


def test_schedule_emits_completed_after_total_runs_reached(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker:
        controller.start(rule="R", hwnd=1, total_runs=2, batch_size=5, batch_interval_ms=60000)
        playback.complete_last_run()
        playback.complete_last_run()

    assert blocker.args == ["completed"]
    assert len(playback.run_calls) == 2
    assert controller.is_active() is False


def test_failed_run_stops_the_whole_schedule(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker:
        controller.start(rule="R", hwnd=1, total_runs=100, batch_size=5, batch_interval_ms=60000)
        playback.complete_last_run()
        playback.fail_last_run("no template match")

    assert blocker.args == ["failed"]
    assert len(playback.run_calls) == 2
    assert controller.is_active() is False


def test_stop_cancels_a_pending_batch_timer_and_emits_stopped(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)
    controller.start(rule="R", hwnd=1, total_runs=10, batch_size=1, batch_interval_ms=60000)
    playback.complete_last_run()  # batch boundary reached, timer now pending
    assert controller._batch_timer.isActive() is True

    with qtbot.waitSignal(controller.finished, timeout=1000) as blocker:
        controller.stop()

    assert blocker.args == ["stopped"]
    assert controller._batch_timer.isActive() is False
    assert controller.is_active() is False


def test_stop_when_not_active_is_a_noop(qtbot):
    playback = FakePlaybackController()
    controller = ScheduleController(playback)

    received = []
    controller.finished.connect(received.append)
    controller.stop()

    assert received == []


def test_finished_signal_arriving_after_stop_is_ignored(qtbot):
    # Simulates F9: stop() is called while a run is in flight; the engine's
    # own (aborted) run later emits `finished` too -- that straggler must
    # not restart the schedule or emit a second `finished`.
    playback = FakePlaybackController()
    controller = ScheduleController(playback)
    controller.start(rule="R", hwnd=1, total_runs=10, batch_size=5, batch_interval_ms=60000)

    received = []
    controller.finished.connect(received.append)
    controller.stop()
    assert received == ["stopped"]

    playback.stop_last_run()  # the straggling result from the aborted run

    assert received == ["stopped"]
    assert len(playback.run_calls) == 1
