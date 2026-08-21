import sys

if sys.platform != "win32":
    raise ImportError("Win32WindowManager can only be used on Windows")

import ctypes

import win32con
import win32gui
import win32process
from ctypes import wintypes

from tiles_survive_automation.window.ports import WindowInfo

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20


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

    def accepts_synthetic_input(self, hwnd: int) -> bool:
        """False when the target window belongs to an elevated process and we
        are not elevated.

        Windows UIPI drops synthesized input aimed at a higher-integrity
        window, but SendInput still returns success -- so playback logs clicks
        that never reached the game and the cursor never moves. Detecting it
        here is the only way to tell the user instead of looking dead.
        """
        try:
            return not self._is_elevated(self._pid_of(hwnd)) or self._is_elevated(
                _kernel32.GetCurrentProcessId())
        except OSError:
            return True  # can't tell -- never block the user on a guess

    @staticmethod
    def _pid_of(hwnd: int) -> int:
        return win32process.GetWindowThreadProcessId(hwnd)[1]

    @staticmethod
    def _is_elevated(pid: int) -> bool:
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Access denied on a limited query means the target outranks us.
            return True
        try:
            token = wintypes.HANDLE()
            if not _advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
                return True
            try:
                elevation = wintypes.DWORD()
                size = wintypes.DWORD()
                if not _advapi32.GetTokenInformation(
                        token, TOKEN_ELEVATION, ctypes.byref(elevation),
                        ctypes.sizeof(elevation), ctypes.byref(size)):
                    return False
                return bool(elevation.value)
            finally:
                _kernel32.CloseHandle(token)
        finally:
            _kernel32.CloseHandle(handle)

    def _client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
        return (screen_left, screen_top, right - left, bottom - top)
