import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable

if sys.platform != "win32":
    raise ImportError("Win32ManualClickWatcher can only be used on Windows")

from tiles_survive_automation.input.win32_input_controller import (
    SYNTHETIC_CLICK_MARKER,
)

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_QUIT = 0x0012
HC_ACTION = 0

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
_HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE,
                                       wintypes.DWORD]
_user32.CallNextHookEx.restype = LRESULT
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM,
                                    wintypes.LPARAM]
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                 wintypes.UINT]
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM,
                                        wintypes.LPARAM]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class Win32ManualClickWatcher:
    """Fires on_manual_click() on a real left-mouse-button-down, ignoring
    this app's own synthetic clicks (tagged with SYNTHETIC_CLICK_MARKER in
    win32_input_controller.py).

    Implemented as a raw WH_MOUSE_LL hook rather than pynput.mouse.Listener
    because pynput doesn't expose MSLLHOOKSTRUCT.dwExtraInfo, which is the
    only way to tell a real click from one this process just generated via
    SendInput. A low-level hook must be installed and pumped from the same
    thread, so start() spins up a dedicated thread with its own message
    loop; stop() posts WM_QUIT to unwind it.
    """

    def __init__(self) -> None:
        self._on_manual_click: Callable[[], None] | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook = None
        self._hook_proc = None  # keep alive -- ctypes doesn't hold a ref for us

    def start(self, on_manual_click: Callable[[], None]) -> None:
        self._on_manual_click = on_manual_click
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(timeout=2)

    def stop(self) -> None:
        if self._thread_id is not None:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None

    def _run(self, ready: threading.Event) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()

        def _proc(n_code, w_param, l_param):
            if n_code == HC_ACTION and w_param == WM_LBUTTONDOWN:
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if info.dwExtraInfo != SYNTHETIC_CLICK_MARKER and self._on_manual_click:
                    self._on_manual_click()
            return _user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        self._hook_proc = _HOOKPROC(_proc)
        self._hook = _user32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc, None, 0)
        ready.set()

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass

        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
