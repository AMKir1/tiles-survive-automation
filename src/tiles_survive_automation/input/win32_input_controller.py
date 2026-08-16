import sys
import time

if sys.platform != "win32":
    raise ImportError("Win32InputController can only be used on Windows")

import win32api
import win32con

_MOUSE_DOWN = {
    "left": win32con.MOUSEEVENTF_LEFTDOWN,
    "right": win32con.MOUSEEVENTF_RIGHTDOWN,
    "middle": win32con.MOUSEEVENTF_MIDDLEDOWN,
}
_MOUSE_UP = {
    "left": win32con.MOUSEEVENTF_LEFTUP,
    "right": win32con.MOUSEEVENTF_RIGHTUP,
    "middle": win32con.MOUSEEVENTF_MIDDLEUP,
}


class Win32InputController:
    def __init__(self) -> None:
        self._held_buttons: set[str] = set()
        self._held_keys: set[str] = set()

    def click(self, x: int, y: int, button: str = "left") -> None:
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(_MOUSE_DOWN[button], x, y, 0, 0)
        win32api.mouse_event(_MOUSE_UP[button], x, y, 0, 0)

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y)
        time.sleep(0.08)
        self.click(x, y)

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int,
              duration_ms: int) -> None:
        win32api.SetCursorPos((from_x, from_y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, from_x, from_y, 0, 0)
        self._held_buttons.add("left")

        steps = max(1, duration_ms // 15)
        for i in range(1, steps + 1):
            x = from_x + (to_x - from_x) * i // steps
            y = from_y + (to_y - from_y) * i // steps
            win32api.SetCursorPos((x, y))
            time.sleep(duration_ms / 1000 / steps)

        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, to_x, to_y, 0, 0)
        self._held_buttons.discard("left")

    def scroll(self, x: int, y: int, delta: int) -> None:
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, delta, 0)

    def key_press(self, key: str) -> None:
        vk_code = win32api.VkKeyScan(key) & 0xFF
        win32api.keybd_event(vk_code, 0, 0, 0)
        win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

    def hotkey(self, keys: list[str]) -> None:
        vk_codes = [win32api.VkKeyScan(k) & 0xFF for k in keys]
        for code in vk_codes:
            win32api.keybd_event(code, 0, 0, 0)
            self._held_keys.add(code)
        for code in reversed(vk_codes):
            win32api.keybd_event(code, 0, win32con.KEYEVENTF_KEYUP, 0)
            self._held_keys.discard(code)

    def press_and_hold(self, button: str) -> None:
        x, y = win32api.GetCursorPos()
        win32api.mouse_event(_MOUSE_DOWN[button], x, y, 0, 0)
        self._held_buttons.add(button)

    def press_and_hold_key(self, key: str) -> None:
        vk_code = win32api.VkKeyScan(key) & 0xFF
        win32api.keybd_event(vk_code, 0, 0, 0)
        self._held_keys.add(vk_code)

    def release_all(self) -> None:
        x, y = win32api.GetCursorPos()
        for button in list(self._held_buttons):
            win32api.mouse_event(_MOUSE_UP[button], x, y, 0, 0)
        self._held_buttons.clear()

        for vk_code in list(self._held_keys):
            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
        self._held_keys.clear()
