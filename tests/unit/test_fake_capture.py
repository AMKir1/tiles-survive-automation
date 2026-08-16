import numpy as np

from tiles_survive_automation.capture.fake_capture import FakeScreenCapture


def test_grab_returns_full_frame_when_rect_matches_frame():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[10, 20] = (1, 2, 3)
    capture = FakeScreenCapture(frame)

    result = capture.grab((0, 0, 1280, 720))

    assert result.shape == (720, 1280, 3)
    assert tuple(result[10, 20]) == (1, 2, 3)


def test_grab_crops_subregion():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[100, 200] = (9, 9, 9)
    capture = FakeScreenCapture(frame)

    result = capture.grab((150, 50, 100, 100))  # left=150, top=50, w=100, h=100

    assert result.shape == (100, 100, 3)
    assert tuple(result[50, 50]) == (9, 9, 9)
