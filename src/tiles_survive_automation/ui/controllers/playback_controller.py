import threading

from PySide6.QtCore import QObject, QTimer, Signal


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
        thread = threading.Thread(target=self._run_in_thread, args=(rule, hwnd),
                                    daemon=True)
        thread.start()
        self._poll_timer.start(50)

    def abort(self) -> None:
        self._engine.abort()

    def _run_in_thread(self, rule, hwnd: int) -> None:
        context = self._engine.run(rule, hwnd)
        self._result_holder.append(context)

    def _poll(self) -> None:
        if not self._result_holder:
            return
        self._poll_timer.stop()
        self.finished.emit(self._result_holder[0])
