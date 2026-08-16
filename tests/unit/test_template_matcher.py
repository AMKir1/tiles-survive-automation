import numpy as np

from tiles_survive_automation.vision.template_matcher import TemplateMatcher


def _frame_with_marker(x: int, y: int, size: int = 20) -> np.ndarray:
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    frame[:, :] = (40, 40, 40)
    marker = np.random.RandomState(42).randint(0, 255, (size, size, 3), dtype=np.uint8)
    frame[y:y + size, x:x + size] = marker
    return frame, marker


def test_find_locates_exact_template():
    frame, marker = _frame_with_marker(120, 60)
    matcher = TemplateMatcher()

    result = matcher.find(frame, marker, confidence_threshold=0.9)

    assert result is not None
    assert result.x == 120
    assert result.y == 60
    assert result.confidence >= 0.9


def test_find_returns_none_when_template_absent():
    frame = np.full((200, 300, 3), 40, dtype=np.uint8)
    unrelated_template = np.random.RandomState(1).randint(0, 255, (20, 20, 3), dtype=np.uint8)
    matcher = TemplateMatcher()

    result = matcher.find(frame, unrelated_template, confidence_threshold=0.9)

    assert result is None
