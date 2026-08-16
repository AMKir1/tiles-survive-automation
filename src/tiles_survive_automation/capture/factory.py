import sys

from tiles_survive_automation.capture.ports import ScreenCapture


def get_screen_capture() -> ScreenCapture:
    if sys.platform == "win32":
        from tiles_survive_automation.capture.mss_capture import MssScreenCapture

        return MssScreenCapture()
    from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
    import numpy as np

    return FakeScreenCapture(np.zeros((720, 1280, 3), dtype="uint8"))
