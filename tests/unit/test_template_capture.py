import numpy as np

from tiles_survive_automation.recorder.template_capture import capture_template


def test_crops_square_region_around_point():
    frame = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100, 100, 3)

    template = capture_template(frame, client_x=50, client_y=50, half_size=10)

    assert template.shape == (20, 20, 3)
    assert np.array_equal(template, frame[40:60, 40:60])


def test_clamps_to_frame_bounds_near_top_left_corner():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    template = capture_template(frame, client_x=2, client_y=3, half_size=10)

    assert template.shape == (13, 12, 3)  # y: 0..13, x: 0..12


def test_clamps_to_frame_bounds_near_bottom_right_corner():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    template = capture_template(frame, client_x=98, client_y=97, half_size=10)

    assert template.shape == (13, 12, 3)  # y: 87..100, x: 88..100


def test_default_half_size_matches_recording_session_convention():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)

    template = capture_template(frame, client_x=100, client_y=100)

    assert template.shape == (60, 60, 3)  # 2 * TEMPLATE_HALF_SIZE (30)
