from dataclasses import dataclass
from typing import Protocol


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    client_rect: tuple[int, int, int, int]  # left, top, width, height


class WindowManager(Protocol):
    def list_windows(self) -> list[WindowInfo]: ...
    def get_client_rect(self, hwnd: int) -> tuple[int, int, int, int]: ...
    def activate(self, hwnd: int) -> bool: ...
    def exists(self, hwnd: int) -> bool: ...
    def accepts_synthetic_input(self, hwnd: int) -> bool: ...
