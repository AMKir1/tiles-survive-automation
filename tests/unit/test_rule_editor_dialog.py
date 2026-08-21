from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.recorder.image_io import write_image
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo

HWND = 1


class ScriptedRecorder:
    """Fake InputRecorder whose on_event callback can be driven manually via emit()."""

    def __init__(self) -> None:
        self._on_event = None

    def start(self, on_event) -> None:
        self._on_event = on_event

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        self._on_event = None

    def emit(self, event) -> None:
        assert self._on_event is not None, "recorder not started"
        self._on_event(event)


def _window_manager() -> FakeWindowManager:
    return FakeWindowManager(
        [WindowInfo(hwnd=HWND, title="Tiles Survive", client_rect=(0, 0, 200, 100))]
    )


def _screen_capture() -> FakeScreenCapture:
    frame = np.full((100, 200, 3), 50, dtype=np.uint8)
    return FakeScreenCapture(frame)


def _step(step_id=None, order_index=0, name="A", template_path=None,
          screenshot_path=None, strategy=StrategyType.RELATIVE_ONLY,
          confidence_threshold=0.9) -> RuleStep:
    return RuleStep(
        id=step_id, order_index=order_index, step_type=StepType.CLICK_IMAGE,
        name=name, enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
        template_path=template_path, confidence_threshold=confidence_threshold,
        strategy=strategy, verification=None,
        screenshot_path=screenshot_path, delay_after_ms=0,
    )


def _rule(*steps) -> Rule:
    return Rule(id=None, name="R", description=None, window_title_hint=None,
                steps=list(steps) or [_step()])


def _dialog(qtbot, tmp_path, rule=None, rule_repository=None, recorder=None,
            playback_controller=None, hwnd=HWND):
    rule_repository = rule_repository or RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(rule or _rule())
    dialog = RuleEditorDialog(
        saved_rule, rule_repository,
        window_manager=_window_manager(),
        screen_capture=_screen_capture(),
        input_recorder=recorder or ScriptedRecorder(),
        playback_controller=playback_controller,
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        hwnd=hwnd,
    )
    qtbot.addWidget(dialog)
    return dialog, rule_repository


def test_dialog_shows_no_image_when_step_has_no_paths(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_step()))

    dialog.step_list.setCurrentRow(0)

    assert dialog.screenshot_preview.text() == "No image"
    assert dialog.template_preview.text() == "No image"


def test_dialog_shows_previews_when_step_has_paths(qtbot, tmp_path):
    screenshot_path = tmp_path / "shot.png"
    template_rel = "session/click_1.png"
    frame = np.full((10, 10, 3), 200, dtype=np.uint8)
    write_image(screenshot_path, frame)
    template_full = tmp_path / "templates" / template_rel
    template_full.parent.mkdir(parents=True, exist_ok=True)
    write_image(template_full, frame[:6, :6])

    step = _step(template_path=template_rel, screenshot_path=str(screenshot_path))
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))

    dialog.step_list.setCurrentRow(0)

    assert dialog.screenshot_preview.text() == ""
    assert not dialog.screenshot_preview.pixmap().isNull()
    assert dialog.template_preview.text() == ""
    assert not dialog.template_preview.pixmap().isNull()


def test_changing_strategy_combo_survives_real_save(qtbot, tmp_path):
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_rule(_step(strategy=StrategyType.RELATIVE_ONLY)))
    assert saved_rule.steps[0].strategy == StrategyType.RELATIVE_ONLY

    dialog, _ = _dialog(qtbot, tmp_path, rule=saved_rule, rule_repository=rule_repository)

    dialog.step_list.setCurrentRow(0)
    new_index = dialog.strategy_combo.findText(StrategyType.VISUAL_ONLY.value)
    assert new_index >= 0
    dialog.strategy_combo.setCurrentIndex(new_index)

    # Must not raise (pre-fix, this would AttributeError inside step.to_row()
    # because itemData() round-trips as a bare str, not a StrategyType).
    dialog._on_save_clicked()

    reloaded = rule_repository.get(saved_rule.id)
    assert reloaded.steps[0].strategy == StrategyType.VISUAL_ONLY
    assert isinstance(reloaded.steps[0].strategy, StrategyType)


def test_editing_name_refreshes_step_list_row_without_reorder(qtbot, tmp_path):
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_rule())

    dialog, _ = _dialog(qtbot, tmp_path, rule=saved_rule, rule_repository=rule_repository)

    dialog.step_list.setCurrentRow(0)
    dialog.name_edit.setText("Renamed Step")
    dialog.name_edit.editingFinished.emit()

    assert "Renamed Step" in dialog.step_list.item(0).text()
    assert dialog.controller.draft.steps[0].name == "Renamed Step"

    dialog.enabled_check.setChecked(False)

    assert dialog.step_list.item(0).foreground().color() == QColor(Qt.gray)
