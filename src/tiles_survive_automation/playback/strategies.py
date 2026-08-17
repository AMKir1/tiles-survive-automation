import numpy as np

from tiles_survive_automation.rules.models import RuleStep
from tiles_survive_automation.vision.template_matcher import TemplateMatcher

_matcher = TemplateMatcher()


def resolve_visual(step: RuleStep, frame: np.ndarray,
                    template: np.ndarray) -> tuple[int, int] | None:
    result = _matcher.find(frame, template, step.confidence_threshold)
    if result is None:
        return None
    return result.center


def resolve_relative_point(params: dict, x_key: str, y_key: str, window_width: int,
                             window_height: int) -> tuple[int, int] | None:
    if x_key not in params or y_key not in params:
        return None
    x = round(params[x_key] * window_width)
    y = round(params[y_key] * window_height)
    return (x, y)


def resolve_relative(step: RuleStep, window_width: int,
                      window_height: int) -> tuple[int, int] | None:
    return resolve_relative_point(step.params, "relative_x", "relative_y",
                                    window_width, window_height)
