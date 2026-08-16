import numpy as np


class FakeScreenCapture:
    def __init__(self, frame: np.ndarray) -> None:
        self._frame = frame

    def grab(self, rect: tuple[int, int, int, int]) -> np.ndarray:
        left, top, width, height = rect
        return self._frame[top:top + height, left:left + width].copy()
