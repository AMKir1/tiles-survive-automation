import numpy as np

from tiles_survive_automation.playback.strategies import (
    resolve_relative,
    resolve_relative_point,
    resolve_visual,
)
from tiles_survive_automation.rules.models import RuleStep, StepType, StrategyType


def _step(params, confidence_threshold=0.9):
    return RuleStep(id=1, order_index=0, step_type=StepType.CLICK_IMAGE,
                     name="Click", enabled=True, params=params, template_path="t.png",
                     confidence_threshold=confidence_threshold,
                     strategy=StrategyType.VISUAL_THEN_RELATIVE, verification=None,
                     screenshot_path=None, delay_after_ms=0)


def test_resolve_visual_returns_center_of_match():
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    marker = np.full((10, 10, 3), 200, dtype=np.uint8)
    frame[40:50, 30:40] = marker

    result = resolve_visual(_step({}), frame, marker)

    assert result == (35, 45)


def test_resolve_visual_returns_none_below_threshold():
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    template = np.full((10, 10, 3), 200, dtype=np.uint8)

    result = resolve_visual(_step({}, confidence_threshold=0.99), frame, template)

    assert result is None


def test_resolve_relative_computes_pixel_coords():
    step = _step({"relative_x": 0.25, "relative_y": 0.5})

    result = resolve_relative(step, window_width=800, window_height=600)

    assert result == (200, 300)


def test_resolve_relative_returns_none_without_relative_params():
    step = _step({})

    assert resolve_relative(step, window_width=800, window_height=600) is None


def test_resolve_relative_point_supports_custom_keys_for_drag():
    params = {"to_relative_x": 0.1, "to_relative_y": 0.9}

    result = resolve_relative_point(params, "to_relative_x", "to_relative_y",
                                     window_width=1000, window_height=200)

    assert result == (100, 180)


def test_resolve_relative_point_returns_none_when_key_missing():
    result = resolve_relative_point({}, "to_relative_x", "to_relative_y",
                                     window_width=1000, window_height=200)

    assert result is None
