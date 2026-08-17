import ctypes
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("Win32InputController can only be used on Windows")

import win32api

from tiles_survive_automation import config

_user32 = ctypes.WinDLL("user32", use_last_error=True)


def _debug_log(message: str) -> None:
    """Temporary diagnostic logging while we track down a cursor-movement
    bug: appends straight to the execution log file so it shows up
    alongside the app's own logs without needing a logger instance
    threaded through InputController's constructor."""
    try:
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.LOGS_DIR / "execution.log", "a", encoding="utf-8") as f:
            f.write(f"[CURSOR-DEBUG] {message}\n")
    except OSError:
        pass


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
                         dwFlags=dw_flags, time=0, dwExtraInfo=0)
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


def _move_and_button(x: int, y: int, button_flag: int = 0, mouse_data: int = 0) -> None:
    """Move the cursor to (x, y) and optionally fire a button/wheel event
    in the same SendInput call, using a RELATIVE delta from the current
    cursor position (not MOUSEEVENTF_ABSOLUTE).

    MOUSEEVENTF_ABSOLUTE teleports the OS-tracked cursor position (visible
    in GetCursorPos) but does not generate the relative-delta events that
    games reading raw/relative mouse input listen to -- many games hide
    the system cursor and render their own, driven entirely by relative
    deltas. Confirmed on this project: GetCursorPos matched the target
    exactly after an absolute move, but the in-game cursor barely moved
    and clicks landed on nothing. A relative MOUSEEVENTF_MOVE is what real
    physical mouse movement generates, so it's what those games see.
    """
    before = win32api.GetCursorPos()
    dx, dy = x - before[0], y - before[1]
    _debug_log(
        f"target=({x},{y}) cursor_before={before} relative_delta=({dx},{dy}) "
        f"button_flag={button_flag}"
    )
    _send_mouse_input(MOUSEEVENTF_MOVE | button_flag, dx, dy, mouse_data)
    time.sleep(0.05)
    after = win32api.GetCursorPos()
    _debug_log(f"cursor_after={after} (target was ({x},{y}))")


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
