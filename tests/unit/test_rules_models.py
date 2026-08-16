from tiles_survive_automation.rules.models import (
    Rule,
    RuleStep,
    StepType,
    StrategyType,
)


def _step(**overrides) -> RuleStep:
    defaults = dict(
        id=None,
        order_index=0,
        step_type=StepType.CLICK_IMAGE,
        name="Click -> Alliance",
        enabled=True,
        params={"relative_x": 0.42, "relative_y": 0.61},
        template_path="templates/1/1.png",
        confidence_threshold=0.85,
        strategy=StrategyType.VISUAL_THEN_RELATIVE,
        verification=None,
        screenshot_path=None,
        delay_after_ms=800,
    )
    defaults.update(overrides)
    return RuleStep(**defaults)


def test_relative_coordinates_are_fractions_of_window_size():
    step = _step(params={"relative_x": 0.25, "relative_y": 0.5})

    window_width, window_height = 1280, 720
    x = round(step.params["relative_x"] * window_width)
    y = round(step.params["relative_y"] * window_height)

    assert x == 320
    assert y == 360


def test_rule_step_round_trips_through_row_dict():
    step = _step()
    row = step.to_row()
    restored = RuleStep.from_row(row)

    assert restored == step


def test_rule_step_verification_none_round_trips():
    step = _step(verification=None)
    row = step.to_row()
    restored = RuleStep.from_row(row)

    assert restored.verification is None


def test_rule_step_verification_empty_dict_round_trips():
    step = _step(verification={})
    row = step.to_row()
    restored = RuleStep.from_row(row)

    assert restored.verification == {}
    assert restored.verification is not None


def test_rule_holds_ordered_steps():
    steps = [_step(order_index=0), _step(order_index=1, name="Click -> Help")]
    rule = Rule(id=None, name="Alliance Help", description=None,
                window_title_hint="Tiles Survive", steps=steps)

    assert [s.name for s in rule.steps] == ["Click -> Alliance", "Click -> Help"]
