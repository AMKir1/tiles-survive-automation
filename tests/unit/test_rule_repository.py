from tiles_survive_automation.rules.models import (
    Rule,
    RuleStep,
    StepType,
    StrategyType,
)
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.rule_repository import RuleRepository


def _rule() -> Rule:
    step = RuleStep(
        id=None,
        order_index=0,
        step_type=StepType.CLICK_IMAGE,
        name="Click -> Alliance",
        enabled=True,
        params={"relative_x": 0.5, "relative_y": 0.5},
        template_path="templates/1/1.png",
        confidence_threshold=0.85,
        strategy=StrategyType.VISUAL_THEN_RELATIVE,
        verification=None,
        screenshot_path=None,
        delay_after_ms=500,
    )
    return Rule(id=None, name="Alliance Help", description=None,
                window_title_hint="Tiles Survive", steps=[step])


def test_save_assigns_ids_and_get_round_trips():
    repo = RuleRepository(connect(":memory:"))

    saved = repo.save(_rule())
    loaded = repo.get(saved.id)

    assert loaded is not None
    assert loaded.name == "Alliance Help"
    assert len(loaded.steps) == 1
    assert loaded.steps[0].name == "Click -> Alliance"
    assert loaded.steps[0].id is not None


def test_save_twice_replaces_steps_not_duplicates():
    repo = RuleRepository(connect(":memory:"))
    saved = repo.save(_rule())

    saved.steps[0].name = "Click -> Alliance (renamed)"
    repo.save(saved)
    loaded = repo.get(saved.id)

    assert len(loaded.steps) == 1
    assert loaded.steps[0].name == "Click -> Alliance (renamed)"


def test_list_all_returns_all_rules():
    repo = RuleRepository(connect(":memory:"))
    repo.save(_rule())
    repo.save(_rule())

    assert len(repo.list_all()) == 2


def test_delete_removes_rule_and_steps():
    repo = RuleRepository(connect(":memory:"))
    saved = repo.save(_rule())

    repo.delete(saved.id)

    assert repo.get(saved.id) is None
