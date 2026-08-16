import mss
import numpy as np


class MssScreenCapture:
    def grab(self, rect: tuple[int, int, int, int]) -> np.ndarray:
        left, top, width, height = rect
        monitor = {"left": left, "top": top, "width": width, "height": height}
        with mss.mss() as sct:
            raw = sct.grab(monitor)
        frame = np.array(raw)  # BGRA
        return frame[:, :, :3]
