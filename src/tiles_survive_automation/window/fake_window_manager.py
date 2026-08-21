from tiles_survive_automation.window.ports import WindowInfo


class FakeWindowManager:
    def __init__(self, windows: list[WindowInfo],
                 accepts_synthetic_input: bool = True) -> None:
        self._windows = {w.hwnd: w for w in windows}
        self._accepts_synthetic_input = accepts_synthetic_input

    def list_windows(self) -> list[WindowInfo]:
        return list(self._windows.values())

    def get_client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        return self._windows[hwnd].client_rect

    def activate(self, hwnd: int) -> bool:
        return hwnd in self._windows

    def exists(self, hwnd: int) -> bool:
        return hwnd in self._windows

    def accepts_synthetic_input(self, hwnd: int) -> bool:
        return self._accepts_synthetic_input

    def move_window(self, hwnd: int, rect: tuple[int, int, int, int]) -> None:
        window = self._windows[hwnd]
        self._windows[hwnd] = WindowInfo(hwnd=window.hwnd, title=window.title,
                                          client_rect=rect)
