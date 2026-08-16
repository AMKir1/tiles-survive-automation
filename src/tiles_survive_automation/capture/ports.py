from typing import Protocol

import numpy as np


class ScreenCapture(Protocol):
    def grab(self, rect: tuple[int, int, int, int]) -> np.ndarray: ...
