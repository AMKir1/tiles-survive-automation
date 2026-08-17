from PySide6.QtCore import QObject, Signal


class RecorderController(QObject):
    started = Signal()
    stopped = Signal(list)

    def __init__(self, session) -> None:
        super().__init__()
        self._session = session

    def start(self, hwnd: int) -> None:
        self._session.start(hwnd)
        self.started.emit()

    def pause(self) -> None:
        self._session.pause()

    def resume(self) -> None:
        self._session.resume()

    def stop(self) -> None:
        steps = self._session.stop()
        self.stopped.emit(steps)
