from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QInputDialog, QMessageBox

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.fake_input import FakeInputController
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.ui.main_window import MainWindow
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo

import numpy as np


def _make_window(qtbot, tmp_path, rule_repository=None, execution_repository=None,
                  input_controller=None):
    window_manager = FakeWindowManager(
        [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 800, 600))]
    )
    rule_repository = rule_repository or RuleRepository(connect(":memory:"))
    execution_repository = execution_repository or ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    window = MainWindow(
        window_manager=window_manager,
        screen_capture=FakeScreenCapture(np.zeros((600, 800, 3), dtype="uint8")),
        input_recorder=ScriptedRecorder(),
        input_controller=input_controller or FakeInputController(),
        rule_repository=rule_repository,
        execution_repository=execution_repository,
        logger=logger,
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        start_emergency_stop=False,
    )
    qtbot.addWidget(window)
    return window, rule_repository


def _make_rule(name="R"):
    step = RuleStep(id=None, order_index=0, step_type=StepType.CLICK_IMAGE, name="Click",
                     enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
                     template_path=None, confidence_threshold=0.9,
                     strategy=StrategyType.RELATIVE_ONLY, verification=None,
                     screenshot_path=None, delay_after_ms=0)
    return Rule(id=None, name=name, description=None, window_title_hint=None, steps=[step])


class ScriptedRecorder:
    def start(self, on_event):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self):
        return []


def test_main_window_lists_windows_and_rules_on_startup(qtbot, tmp_path):
    window_manager = FakeWindowManager(
        [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 800, 600))]
    )
    rule_repository = RuleRepository(connect(":memory:"))
    execution_repository = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    window = MainWindow(
        window_manager=window_manager,
        screen_capture=FakeScreenCapture(np.zeros((600, 800, 3), dtype="uint8")),
        input_recorder=ScriptedRecorder(),
        input_controller=FakeInputController(),
        rule_repository=rule_repository,
        execution_repository=execution_repository,
        logger=logger,
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        start_emergency_stop=False,
    )
    qtbot.addWidget(window)

    assert window.window_combo.count() == 1
    assert window.window_combo.itemText(0) == "Tiles Survive"
    assert window.rule_list.count() == 0


def test_emergency_stop_trigger_aborts_playback_and_releases_input(qtbot, tmp_path):
    window_manager = FakeWindowManager(
        [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 800, 600))]
    )
    rule_repository = RuleRepository(connect(":memory:"))
    execution_repository = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")
    input_controller = FakeInputController()

    window = MainWindow(
        window_manager=window_manager,
        screen_capture=FakeScreenCapture(np.zeros((600, 800, 3), dtype="uint8")),
        input_recorder=ScriptedRecorder(),
        input_controller=input_controller,
        rule_repository=rule_repository,
        execution_repository=execution_repository,
        logger=logger,
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        start_emergency_stop=False,
    )
    qtbot.addWidget(window)

    window._emergency_stop._trigger()

    assert ("release_all",) in input_controller.calls
    assert window._playback_controller._engine._abort_event.is_set()


def test_play_button_disabled_during_playback_and_reenabled_when_finished(qtbot, tmp_path):
    window_manager = FakeWindowManager(
        [WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 800, 600))]
    )
    rule_repository = RuleRepository(connect(":memory:"))
    step = RuleStep(id=None, order_index=0, step_type=StepType.CLICK_IMAGE, name="Click",
                     enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
                     template_path=None, confidence_threshold=0.9,
                     strategy=StrategyType.RELATIVE_ONLY, verification=None,
                     screenshot_path=None, delay_after_ms=0)
    rule_repository.save(Rule(id=None, name="R", description=None,
                                window_title_hint=None, steps=[step]))
    execution_repository = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    window = MainWindow(
        window_manager=window_manager,
        screen_capture=FakeScreenCapture(np.zeros((600, 800, 3), dtype="uint8")),
        input_recorder=ScriptedRecorder(),
        input_controller=FakeInputController(),
        rule_repository=rule_repository,
        execution_repository=execution_repository,
        logger=logger,
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        start_emergency_stop=False,
    )
    qtbot.addWidget(window)

    window.rule_list.setCurrentRow(0)
    assert window._play_button.isEnabled()

    with qtbot.waitSignal(window._playback_controller.finished, timeout=2000):
        window._on_play_clicked()
        assert not window._play_button.isEnabled()

    assert window._play_button.isEnabled()


def test_rename_button_updates_rule_name(qtbot, tmp_path, monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("Old Name"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)

    window.rule_list.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New Name", True))

    window._on_rename_clicked()

    assert window.rule_list.item(0).text() == "New Name"
    assert rule_repository.list_all()[0].name == "New Name"


def test_rename_button_cancelled_leaves_rule_unchanged(qtbot, tmp_path, monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("Old Name"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)

    window.rule_list.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New Name", False))

    window._on_rename_clicked()

    assert rule_repository.list_all()[0].name == "Old Name"


def test_delete_button_removes_rule_after_confirmation(qtbot, tmp_path, monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)

    window.rule_list.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    window._on_delete_clicked()

    assert window.rule_list.count() == 0
    assert rule_repository.list_all() == []


def test_delete_button_declined_confirmation_keeps_rule(qtbot, tmp_path, monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)

    window.rule_list.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)

    window._on_delete_clicked()

    assert window.rule_list.count() == 1
    assert len(rule_repository.list_all()) == 1


def test_schedule_button_disables_play_and_schedule_until_finished(qtbot, tmp_path, monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)

    window.rule_list.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **k: (1, True))

    with qtbot.waitSignal(window._schedule_controller.finished, timeout=2000):
        window._on_schedule_clicked()
        assert not window._play_button.isEnabled()
        assert not window._schedule_button.isEnabled()

    assert window._play_button.isEnabled()
    assert window._schedule_button.isEnabled()


def test_edit_button_saves_changes_made_in_the_dialog(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog

    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)
    window.rule_list.setCurrentRow(0)

    def fake_exec(self):
        self.controller.update_step(0, name="Renamed", enabled=False)
        self.controller.save()
        return QDialog.Accepted

    monkeypatch.setattr(RuleEditorDialog, "exec", fake_exec)

    window._on_edit_clicked()

    saved = rule_repository.list_all()[0]
    assert saved.steps[0].name == "Renamed"
    assert saved.steps[0].enabled is False


def test_edit_button_cancelled_leaves_rule_unchanged(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog

    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)
    window.rule_list.setCurrentRow(0)

    def fake_exec(self):
        self.controller.update_step(0, name="Should not persist")
        return QDialog.Rejected

    monkeypatch.setattr(RuleEditorDialog, "exec", fake_exec)

    window._on_edit_clicked()

    saved = rule_repository.list_all()[0]
    assert saved.steps[0].name == "Click"


def test_changing_strategy_combo_survives_real_save(qtbot, tmp_path):
    from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog

    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_make_rule("R"))
    assert saved_rule.steps[0].strategy == StrategyType.RELATIVE_ONLY

    dialog = RuleEditorDialog(saved_rule, rule_repository)
    qtbot.addWidget(dialog)

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
    from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog

    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_make_rule("R"))

    dialog = RuleEditorDialog(saved_rule, rule_repository)
    qtbot.addWidget(dialog)

    dialog.step_list.setCurrentRow(0)
    dialog.name_edit.setText("Renamed Step")
    dialog.name_edit.editingFinished.emit()

    assert "Renamed Step" in dialog.step_list.item(0).text()
    assert dialog.controller.draft.steps[0].name == "Renamed Step"

    dialog.enabled_check.setChecked(False)

    assert dialog.step_list.item(0).foreground().color() == QColor(Qt.gray)
