import threading

from PySide6.QtCore import QObject, QTimer, Signal

from tiles_survive_automation.playback.state import PlaybackContext


class PlaybackController(QObject):
    finished = Signal(object)

    def __init__(self, engine) -> None:
        super().__init__()
        self._engine = engine
        self._result_holder: list = []
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)

    def run_async(self, rule, hwnd: int) -> None:
        self._result_holder.clear()
        # Clear any abort latched by a previous run (e.g. an F9 press) before
        # spawning this run's worker thread -- otherwise every run after the
        # first abort() would immediately see the flag set and return STOPPED.
        self._engine.reset()
        thread = threading.Thread(target=self._run_in_thread, args=(rule, hwnd),
                                    daemon=True)
        thread.start()
        self._poll_timer.start(50)

    def abort(self) -> None:
        self._engine.abort()

    def _run_in_thread(self, rule, hwnd: int) -> None:
        try:
            context = self._engine.run(rule, hwnd)
        except Exception as e:
            # Defense-in-depth backstop: PlaybackEngine.run() already catches
            # per-step exceptions internally, but if something still escapes
            # here, make sure _result_holder is populated regardless so the
            # QTimer poll always completes and `finished` is emitted.
            context = PlaybackContext()
            context.start()
            context.fail(str(e))
        self._result_holder.append(context)

    def _poll(self) -> None:
        if not self._result_holder:
            return
        self._poll_timer.stop()
        self.finished.emit(self._result_holder[0])
