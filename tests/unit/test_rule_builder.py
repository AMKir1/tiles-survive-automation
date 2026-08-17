from tiles_survive_automation.input.models import RawEvent
from tiles_survive_automation.recorder.recording_session import RecordedStep
from tiles_survive_automation.rules.models import StepType, StrategyType
from tiles_survive_automation.rules.rule_builder import RuleBuilder


def _step(kind, t, x=None, y=None, rx=None, ry=None, button=None, key=None,
          template_path=None, dx=0, dy=0):
    event = RawEvent(timestamp=t, kind=kind, x=x, y=y, button=button, key=key,
                      scroll_dx=dx, scroll_dy=dy)
    return RecordedStep(event=event, relative_x=rx, relative_y=ry,
                         template_path=template_path, screenshot_path=None)


def test_click_pair_becomes_click_image_step():
    steps = [
        _step("mouse_down", 0.0, x=100, y=50, rx=0.5, ry=0.25, button="left",
              template_path="click_1.png"),
        _step("mouse_up", 0.05, x=100, y=50, rx=0.5, ry=0.25, button="left"),
    ]

    rule = RuleBuilder("Alliance Help", window_title_hint="Tiles Survive").build(steps)

    assert len(rule.steps) == 1
    step = rule.steps[0]
    assert step.step_type == StepType.CLICK_IMAGE
    assert step.params == {"relative_x": 0.5, "relative_y": 0.25}
    assert step.template_path == "click_1.png"
    assert step.strategy == StrategyType.VISUAL_THEN_RELATIVE


def test_right_button_pair_becomes_right_click_step():
    steps = [
        _step("mouse_down", 0.0, x=10, y=10, rx=0.1, ry=0.1, button="right",
              template_path="click_1.png"),
        _step("mouse_up", 0.02, x=10, y=10, rx=0.1, ry=0.1, button="right"),
    ]

    rule = RuleBuilder("R", None).build(steps)

    assert rule.steps[0].step_type == StepType.RIGHT_CLICK


def test_far_apart_pair_becomes_drag_step():
    steps = [
        _step("mouse_down", 0.0, x=10, y=10, rx=0.1, ry=0.1, button="left",
              template_path="click_1.png"),
        _step("mouse_up", 0.3, x=200, y=150, rx=0.8, ry=0.7, button="left"),
    ]

    rule = RuleBuilder("R", None).build(steps)

    assert rule.steps[0].step_type == StepType.DRAG
    assert rule.steps[0].params == {
        "from_relative_x": 0.1, "from_relative_y": 0.1,
        "to_relative_x": 0.8, "to_relative_y": 0.7, "duration_ms": 300,
    }


def test_scroll_becomes_scroll_step():
    steps = [_step("scroll", 0.0, x=5, y=5, rx=0.5, ry=0.5, dx=0, dy=-3)]

    rule = RuleBuilder("R", None).build(steps)

    assert rule.steps[0].step_type == StepType.SCROLL
    assert rule.steps[0].params == {"relative_x": 0.5, "relative_y": 0.5, "delta": -3}


def test_key_down_up_becomes_key_press_step():
    steps = [
        _step("key_down", 0.0, key="a"),
        _step("key_up", 0.05, key="a"),
    ]

    rule = RuleBuilder("R", None).build(steps)

    assert rule.steps[0].step_type == StepType.KEY_PRESS
    assert rule.steps[0].params == {"key": "a"}


def test_gap_between_steps_inserts_wait_step():
    steps = [
        _step("mouse_down", 0.0, x=10, y=10, rx=0.1, ry=0.1, button="left",
              template_path="click_1.png"),
        _step("mouse_up", 0.02, x=10, y=10, rx=0.1, ry=0.1, button="left"),
        _step("mouse_down", 1.0, x=20, y=20, rx=0.2, ry=0.2, button="left",
              template_path="click_2.png"),
        _step("mouse_up", 1.02, x=20, y=20, rx=0.2, ry=0.2, button="left"),
    ]

    rule = RuleBuilder("R", None).build(steps)

    assert [s.step_type for s in rule.steps] == [
        StepType.CLICK_IMAGE, StepType.WAIT, StepType.CLICK_IMAGE,
    ]
    assert rule.steps[1].params["duration_ms"] == 980


def test_two_close_clicks_at_same_spot_merge_into_double_click():
    steps = [
        _step("mouse_down", 0.0, x=10, y=10, rx=0.1, ry=0.1, button="left",
              template_path="click_1.png"),
        _step("mouse_up", 0.02, x=10, y=10, rx=0.1, ry=0.1, button="left"),
        _step("mouse_down", 0.1, x=11, y=10, rx=0.11, ry=0.1, button="left",
              template_path="click_2.png"),
        _step("mouse_up", 0.12, x=11, y=10, rx=0.11, ry=0.1, button="left"),
    ]

    rule = RuleBuilder("R", None).build(steps)

    assert [s.step_type for s in rule.steps] == [StepType.DOUBLE_CLICK]


def test_two_close_clicks_at_different_spots_do_not_merge():
    steps = [
        _step("mouse_down", 0.0, x=10, y=10, rx=0.1, ry=0.1, button="left",
              template_path="click_1.png"),
        _step("mouse_up", 0.02, x=10, y=10, rx=0.1, ry=0.1, button="left"),
        _step("mouse_down", 0.1, x=300, y=10, rx=0.4, ry=0.1, button="left",
              template_path="click_2.png"),
        _step("mouse_up", 0.12, x=300, y=10, rx=0.4, ry=0.1, button="left"),
    ]

    rule = RuleBuilder("R", None).build(steps)

    assert [s.step_type for s in rule.steps] == [
        StepType.CLICK_IMAGE, StepType.CLICK_IMAGE
    ]
    assert rule.steps[0].params == {"relative_x": 0.1, "relative_y": 0.1}
    assert rule.steps[1].params == {"relative_x": 0.4, "relative_y": 0.1}
