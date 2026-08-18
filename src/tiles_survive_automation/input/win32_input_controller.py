import ctypes
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("Win32InputController can only be used on Windows")

import win32api
import win32gui

ULONG_PTR = ctypes.c_size_t

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_KEYUP = 0x0002

_MOUSE_DOWN_FLAG = {
    "left": MOUSEEVENTF_LEFTDOWN,
    "right": MOUSEEVENTF_RIGHTDOWN,
    "middle": MOUSEEVENTF_MIDDLEDOWN,
}
_MOUSE_UP_FLAG = {
    "left": MOUSEEVENTF_LEFTUP,
    "right": MOUSEEVENTF_RIGHTUP,
    "middle": MOUSEEVENTF_MIDDLEUP,
}

_MAX_MOVE_STEP_PX = 10
_MOVE_STEP_DELAY_S = 0.012

# Tags every SendInput mouse event this process generates, so a low-level
# mouse hook (Win32ManualClickWatcher) can tell our own synthetic clicks
# apart from a real human click on dwExtraInfo -- pynput's mouse.Listener
# doesn't expose that field, so this marker only helps a raw WH_MOUSE_LL
# hook, not pynput-based code.
SYNTHETIC_CLICK_MARKER = 0xC0FFEE01

SPI_GETMOUSE = 0x0003
SPI_SETMOUSE = 0x0004
SPI_GETMOUSESPEED = 0x0070
SPI_SETMOUSESPEED = 0x0071
SPIF_SENDCHANGE = 0x0002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SystemParametersInfoW.restype = wintypes.BOOL
_user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT,
                                            ctypes.c_void_p, wintypes.UINT]
_user32.GetDpiForSystem.restype = wintypes.UINT
_user32.GetDpiForSystem.argtypes = []
_user32.GetDpiForWindow.restype = wintypes.UINT
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _send_mouse_input(dw_flags: int, dx: int = 0, dy: int = 0, mouse_data: int = 0) -> None:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=mouse_data & 0xFFFFFFFF,
                         dwFlags=dw_flags, time=0, dwExtraInfo=SYNTHETIC_CLICK_MARKER)
    sent = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _send_key_input(vk_code: int, key_up: bool) -> None:
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk_code, wScan=0,
                         dwFlags=KEYEVENTF_KEYUP if key_up else 0,
                         time=0, dwExtraInfo=0)
    sent = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


class _PointerAccelerationGuard:
    """Temporarily zeroes Windows pointer acceleration and resets pointer
    speed to the neutral default (10) for a `with` block, restoring the
    user's real settings on exit. Never persisted to the registry, so a
    reboot alone would revert it even if restore didn't run.

    Needed because relative SendInput deltas go through the same
    acceleration curve and speed multiplier as a real mouse -- without
    this, our deliberately small, evenly-spaced move increments still get
    distorted.
    """

    def __enter__(self):
        self._original_mouse = (ctypes.c_int * 3)()
        _user32.SystemParametersInfoW(SPI_GETMOUSE, 0, self._original_mouse, 0)
        self._original_speed = ctypes.c_int()
        _user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0,
                                       ctypes.byref(self._original_speed), 0)

        disabled = (ctypes.c_int * 3)(self._original_mouse[0], self._original_mouse[1], 0)
        _user32.SystemParametersInfoW(SPI_SETMOUSE, 0, disabled, SPIF_SENDCHANGE)
        _user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0, ctypes.c_void_p(10),
                                       SPIF_SENDCHANGE)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _user32.SystemParametersInfoW(SPI_SETMOUSE, 0, self._original_mouse, SPIF_SENDCHANGE)
        _user32.SystemParametersInfoW(
            SPI_SETMOUSESPEED, 0, ctypes.c_void_p(self._original_speed.value),
            SPIF_SENDCHANGE)


def _dpi_scale() -> float:
    """GetCursorPos/GetClientRect report logical pixels; SendInput's
    relative MOUSEEVENTF_MOVE deltas move the cursor in physical pixels.
    At 150% display scaling that's a 1.5x mismatch, so relative deltas
    computed from logical coordinates must be divided by this scale
    before being sent.

    Uses GetDpiForWindow on the current foreground window rather than
    GetDpiForSystem: for a PROCESS_PER_MONITOR_DPI_AWARE process (which
    this app is, see Win32WindowManager), GetDpiForSystem always returns
    the primary monitor's DPI, not the DPI of the monitor the target
    window actually sits on -- wrong on any multi-monitor setup where the
    game isn't on the primary display, even without moving windows
    between monitors during a run. GetDpiForWindow asks for the DPI of
    that specific window's monitor, which is what these deltas need.
    """
    hwnd = win32gui.GetForegroundWindow()
    dpi = _user32.GetDpiForWindow(hwnd) if hwnd else _user32.GetDpiForSystem()
    return dpi / 96.0 if dpi else 1.0


def _move_and_button(x: int, y: int, button_flag: int = 0, mouse_data: int = 0) -> None:
    """Move the cursor to (x, y) and optionally fire a button/wheel event
    on the final step, using RELATIVE deltas from the current cursor
    position rather than MOUSEEVENTF_ABSOLUTE.

    Absolute positioning teleports the OS-tracked cursor (GetCursorPos
    reflects it correctly) but doesn't generate the relative-delta events
    that games reading raw/relative mouse input listen to -- many games
    hide the system cursor and render their own, driven purely by deltas.
    The move is split into small, evenly-time-spaced increments (real
    mouse hardware never reports one giant delta) and DPI/acceleration
    are compensated for -- see _dpi_scale and _PointerAccelerationGuard.
    """
    with _PointerAccelerationGuard():
        before = win32api.GetCursorPos()
        scale = _dpi_scale()
        total_dx = round((x - before[0]) / scale)
        total_dy = round((y - before[1]) / scale)

        steps = max(1, max(abs(total_dx), abs(total_dy)) // _MAX_MOVE_STEP_PX + 1)
        sent_dx = sent_dy = 0
        for i in range(1, steps + 1):
            step_x = round(total_dx * i / steps)
            step_y = round(total_dy * i / steps)
            dx, dy = step_x - sent_dx, step_y - sent_dy
            sent_dx, sent_dy = step_x, step_y
            is_last = i == steps
            _send_mouse_input(MOUSEEVENTF_MOVE | (button_flag if is_last else 0),
                               dx, dy, mouse_data if is_last else 0)
            if not is_last:
                time.sleep(_MOVE_STEP_DELAY_S)

        time.sleep(0.05)


class Win32InputController:
    """Synthesizes mouse/keyboard input via SendInput, moving the cursor
    with RELATIVE deltas rather than absolute positioning (see
    _move_and_button's docstring for why).
    """

    def __init__(self) -> None:
        self._held_buttons: set[str] = set()
        self._held_keys: set[str] = set()

    def click(self, x: int, y: int, button: str = "left") -> None:
        _move_and_button(x, y, _MOUSE_DOWN_FLAG[button])
        _send_mouse_input(_MOUSE_UP_FLAG[button])

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y)
        time.sleep(0.08)
        self.click(x, y)

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int,
              duration_ms: int) -> None:
        _move_and_button(from_x, from_y, MOUSEEVENTF_LEFTDOWN)
        self._held_buttons.add("left")

        steps = max(1, duration_ms // 15)
        for i in range(1, steps + 1):
            x = from_x + (to_x - from_x) * i // steps
            y = from_y + (to_y - from_y) * i // steps
            _move_and_button(x, y)
            time.sleep(duration_ms / 1000 / steps)

        _move_and_button(to_x, to_y, MOUSEEVENTF_LEFTUP)
        self._held_buttons.discard("left")

    def scroll(self, x: int, y: int, delta: int) -> None:
        _move_and_button(x, y, MOUSEEVENTF_WHEEL, mouse_data=delta)

    def key_press(self, key: str) -> None:
        vk_code = win32api.VkKeyScan(key) & 0xFF
        _send_key_input(vk_code, key_up=False)
        _send_key_input(vk_code, key_up=True)

    def hotkey(self, keys: list[str]) -> None:
        vk_codes = [win32api.VkKeyScan(k) & 0xFF for k in keys]
        for code in vk_codes:
            _send_key_input(code, key_up=False)
            self._held_keys.add(code)
        for code in reversed(vk_codes):
            _send_key_input(code, key_up=True)
            self._held_keys.discard(code)

    def press_and_hold(self, button: str) -> None:
        _send_mouse_input(_MOUSE_DOWN_FLAG[button])
        self._held_buttons.add(button)

    def press_and_hold_key(self, key: str) -> None:
        vk_code = win32api.VkKeyScan(key) & 0xFF
        _send_key_input(vk_code, key_up=False)
        self._held_keys.add(vk_code)

    def release_all(self) -> None:
        for button in list(self._held_buttons):
            _send_mouse_input(_MOUSE_UP_FLAG[button])
        self._held_buttons.clear()

        for vk_code in list(self._held_keys):
            _send_key_input(vk_code, key_up=True)
        self._held_keys.clear()
