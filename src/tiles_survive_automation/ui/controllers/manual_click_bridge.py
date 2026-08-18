from PySide6.QtCore import QObject, Signal


class ManualClickBridge(QObject):
    """Turns a ManualClickWatcher callback -- which may run on a raw
    background thread (see win32_manual_click_watcher.py's own message
    loop thread) -- into a Qt signal. Signal.emit() is safe to call from
    any thread; Qt auto-queues delivery to the connected slot on the GUI
    thread. Touching a widget (e.g. MainWindow.log_view) directly from
    that background thread would not be safe.
    """

    detected = Signal()
