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


_MAX_MOVE_STEP_PX = 10
_MOVE_STEP_DELAY_S = 0.012

SPI_GETMOUSE = 0x0003
SPI_SETMOUSE = 0x0004
SPIF_SENDCHANGE = 0x0002


class _PointerAccelerationGuard:
    """Temporarily disables Windows pointer acceleration ('Enhance pointer
    precision') for the duration of a `with` block, restoring the user's
    original setting on exit -- never persisted to the registry (no
    SPIF_UPDATEINIFILE), so even if restore somehow didn't run, a reboot
    reverts to the user's real setting.

    Confirmed via cursor_before/after debug logging that acceleration
    was still distorting relative SendInput moves even after splitting
    them into small, time-spaced steps: even the OS's own GetCursorPos
    ended up far from the intended target, occasionally clamped at a
    screen edge from a modest nominal delta. Disabling acceleration at
    the source removes the distortion instead of trying to out-guess it
    with step size/timing.
    """

    def __enter__(self):
        self._original = (ctypes.c_int * 3)()
        _user32.SystemParametersInfoW(SPI_GETMOUSE, 0, self._original, 0)
        disabled = (ctypes.c_int * 3)(self._original[0], self._original[1], 0)
        _user32.SystemParametersInfoW(SPI_SETMOUSE, 0, disabled, SPIF_SENDCHANGE)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _user32.SystemParametersInfoW(SPI_SETMOUSE, 0, self._original, SPIF_SENDCHANGE)


def _move_and_button(x: int, y: int, button_flag: int = 0, mouse_data: int = 0) -> None:
    """Move the cursor to (x, y) and optionally fire a button/wheel event
    on the final step, using RELATIVE deltas from the current cursor
    position (not MOUSEEVENTF_ABSOLUTE) broken into many small increments.

    MOUSEEVENTF_ABSOLUTE teleports the OS-tracked cursor position (visible
    in GetCursorPos) but does not generate the relative-delta events that
    games reading raw/relative mouse input listen to -- many games hide
    the system cursor and render their own, driven entirely by relative
    deltas. Confirmed on this project: GetCursorPos matched the target
    exactly after an absolute move, but the in-game cursor barely moved
    and clicks landed on nothing.

    A single huge relative delta isn't enough either: Windows applies
    pointer-acceleration ("Enhance pointer precision") to MOUSEEVENTF_MOVE
    deltas, which non-linearly distorts one big jump -- confirmed by
    clicks landing "somewhere completely unrelated" to the target. A real
    mouse never reports one giant delta; it reports many small ones per
    second. Splitting the move into <= _MAX_MOVE_STEP_PX-sized increments
    fixed the gross distortion, but the acceleration curve keys off
    IMPLIED VELOCITY (delta / time-since-last-event), not just delta size
    -- sending small steps too close together in time still reads as a
    very fast flick and overshoots. _MOVE_STEP_DELAY_S spaces steps out
    enough that the implied speed stays in a realistic, near-linear range.
    """
    with _PointerAccelerationGuard():
        before = win32api.GetCursorPos()
        total_dx, total_dy = x - before[0], y - before[1]
        _debug_log(
            f"target=({x},{y}) cursor_before={before} total_delta=({total_dx},{total_dy}) "
            f"button_flag={button_flag}"
        )

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
        after = win32api.GetCursorPos()
        _debug_log(f"cursor_after={after} (target was ({x},{y})) steps={steps}")


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
