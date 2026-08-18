from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.ui.controllers.rule_editor_controller import (
    RuleEditorController,
)


class FakeRuleRepository:
    def __init__(self) -> None:
        self.save_calls: list[Rule] = []

    def save(self, rule: Rule) -> Rule:
        self.save_calls.append(rule)
        return rule


def _step(step_id: int, order_index: int, name: str) -> RuleStep:
    return RuleStep(
        id=step_id, order_index=order_index, step_type=StepType.CLICK_IMAGE,
        name=name, enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
        template_path=None, confidence_threshold=0.9,
        strategy=StrategyType.RELATIVE_ONLY, verification=None,
        screenshot_path=None, delay_after_ms=0,
    )


def _rule() -> Rule:
    return Rule(
        id=1, name="R", description=None, window_title_hint=None,
        steps=[_step(1, 0, "A"), _step(2, 1, "B"), _step(3, 2, "C")],
    )


def test_move_up_swaps_with_previous_and_reindexes():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_up(1)  # B (index 1) <-> A (index 0)

    assert [s.name for s in controller.draft.steps] == ["B", "A", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1, 2]


def test_move_up_at_first_index_is_a_noop():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_up(0)

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C"]


def test_move_down_swaps_with_next_and_reindexes():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_down(0)  # A (index 0) <-> B (index 1)

    assert [s.name for s in controller.draft.steps] == ["B", "A", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1, 2]


def test_move_down_at_last_index_is_a_noop():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_down(2)

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C"]


def test_delete_step_removes_and_reindexes_remaining():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.delete_step(1)  # remove B

    assert [s.name for s in controller.draft.steps] == ["A", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1]


def test_delete_all_steps_leaves_empty_list():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.delete_step(0)
    controller.delete_step(0)
    controller.delete_step(0)

    assert controller.draft.steps == []


def test_update_step_replaces_only_given_fields():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.update_step(1, name="Renamed", enabled=False, delay_after_ms=500,
                            confidence_threshold=0.75, strategy=StrategyType.VISUAL_ONLY)

    step = controller.draft.steps[1]
    assert step.name == "Renamed"
    assert step.enabled is False
    assert step.delay_after_ms == 500
    assert step.confidence_threshold == 0.75
    assert step.strategy == StrategyType.VISUAL_ONLY
    assert step.id == 2
    assert step.order_index == 1
    assert step.step_type == StepType.CLICK_IMAGE


def test_no_repository_write_happens_before_save():
    repository = FakeRuleRepository()
    controller = RuleEditorController(_rule(), repository)

    controller.update_step(0, name="Changed")
    controller.delete_step(2)
    controller.move_down(0)

    assert repository.save_calls == []


def test_save_calls_repository_exactly_once_with_final_draft():
    repository = FakeRuleRepository()
    controller = RuleEditorController(_rule(), repository)

    controller.update_step(1, name="Renamed")

    controller.save()

    assert len(repository.save_calls) == 1
    saved = repository.save_calls[0]
    assert [s.name for s in saved.steps] == ["A", "Renamed", "C"]


def test_original_rule_object_passed_in_is_not_mutated():
    original = _rule()
    controller = RuleEditorController(original, FakeRuleRepository())

    controller.update_step(0, name="Changed")
    controller.delete_step(2)

    assert [s.name for s in original.steps] == ["A", "B", "C"]
