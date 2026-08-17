from PySide6.QtCore import QObject, QTimer, Signal

from tiles_survive_automation.playback.state import PlaybackState


class ScheduleController(QObject):
    """Repeats a Rule via a PlaybackController a fixed number of times,
    in batches with a pause between batches (no pause within a batch).
    Any non-COMPLETED result (failure or abort/F9) halts the whole
    schedule, including any still-pending inter-batch pause.
    """

    progress = Signal(int, int, int, int)  # completed_runs, total_runs, batch_index, batch_count
    finished = Signal(str)  # "completed" | "failed" | "stopped"

    def __init__(self, playback_controller) -> None:
        super().__init__()
        self._playback_controller = playback_controller
        self._playback_controller.finished.connect(self._on_run_finished)
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._start_next_run)
        self._active = False

    def is_active(self) -> bool:
        return self._active

    def start(self, rule, hwnd, total_runs: int, batch_size: int,
              batch_interval_ms: int) -> None:
        self._rule = rule
        self._hwnd = hwnd
        self._total_runs = total_runs
        self._batch_size = batch_size
        self._batch_interval_ms = batch_interval_ms
        self._completed_runs = 0
        self._active = True
        self._start_next_run()

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        self._batch_timer.stop()
        self.finished.emit("stopped")

    def _start_next_run(self) -> None:
        self._playback_controller.run_async(self._rule, self._hwnd)

    def _on_run_finished(self, context) -> None:
        if not self._active:
            return  # stop() already fired (e.g. F9); ignore a straggling result

        if context.state != PlaybackState.COMPLETED:
            self._active = False
            reason = "failed" if context.state == PlaybackState.FAILED else "stopped"
            self.finished.emit(reason)
            return

        self._completed_runs += 1
        batch_count = (self._total_runs + self._batch_size - 1) // self._batch_size
        batch_index = (self._completed_runs - 1) // self._batch_size + 1
        self.progress.emit(self._completed_runs, self._total_runs, batch_index, batch_count)

        if self._completed_runs >= self._total_runs:
            self._active = False
            self.finished.emit("completed")
            return

        if self._completed_runs % self._batch_size == 0:
            self._batch_timer.start(self._batch_interval_ms)
        else:
            self._start_next_run()
