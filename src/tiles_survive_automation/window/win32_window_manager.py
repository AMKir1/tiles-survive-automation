import sys

if sys.platform != "win32":
    raise ImportError("Win32WindowManager can only be used on Windows")

import ctypes

import win32con
import win32gui
import win32process

from tiles_survive_automation.window.ports import WindowInfo


class Win32WindowManager:
    def __init__(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()

    def list_windows(self) -> list[WindowInfo]:
        results: list[WindowInfo] = []

        def _on_window(hwnd: int, _: None) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            results.append(WindowInfo(hwnd=hwnd, title=title,
                                       client_rect=self._client_rect(hwnd)))

        win32gui.EnumWindows(_on_window, None)
        return results

    def get_client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        return self._client_rect(hwnd)

    def activate(self, hwnd: int) -> bool:
        if not self.exists(hwnd):
            return False
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except win32gui.error:
            return False
        return win32gui.GetForegroundWindow() == hwnd

    def exists(self, hwnd: int) -> bool:
        return bool(win32gui.IsWindow(hwnd))

    def _client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
        return (screen_left, screen_top, right - left, bottom - top)
