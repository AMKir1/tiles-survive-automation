from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.fake_input import FakeInputController
from tiles_survive_automation.input.models import RawEvent
from tiles_survive_automation.recorder.image_io import write_image
from tiles_survive_automation.playback.engine import PlaybackEngine
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.ui.controllers.playback_controller import PlaybackController
from tiles_survive_automation.ui.dialogs.add_step_dialog import AddStepDialog
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


def test_recapture_updates_step_paths_on_click_inside_window(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)

    dialog.recapture_button.click()
    assert dialog._awaiting_recapture is True
    assert dialog.status_label.text().startswith("Click on the game window")

    recorder.emit(RawEvent(timestamp=0.0, kind="mouse_down", x=50, y=40, button="left"))
    qtbot.waitUntil(lambda: not dialog._awaiting_recapture, timeout=1000)

    step = dialog.controller.draft.steps[0]
    assert step.template_path is not None
    assert (tmp_path / "templates" / step.template_path).exists()
    assert step.screenshot_path is not None
    assert Path(step.screenshot_path).exists()
    assert dialog.status_label.text() == "Template recaptured."


def test_recapture_ignores_click_outside_client_rect(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    original_template_path = dialog.controller.draft.steps[0].template_path

    dialog.recapture_button.click()
    recorder.emit(RawEvent(timestamp=0.0, kind="mouse_down", x=5000, y=5000, button="left"))
    qtbot.wait(50)

    assert dialog._awaiting_recapture is True
    assert dialog.controller.draft.steps[0].template_path == original_template_path


def test_escape_cancels_recapture_without_changing_draft(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    original_template_path = dialog.controller.draft.steps[0].template_path

    dialog.recapture_button.click()
    QTest.keyClick(dialog, Qt.Key_Escape)

    assert dialog._awaiting_recapture is False
    assert dialog.controller.draft.steps[0].template_path == original_template_path
    assert dialog.status_label.text() == "Recapture cancelled."


def test_test_button_disabled_when_step_has_no_template(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_step(template_path=None)))

    dialog.step_list.setCurrentRow(0)

    assert dialog.test_button.isEnabled() is False


def test_test_button_disabled_when_strategy_is_relative_only(qtbot, tmp_path):
    step = _step(template_path="session/click_1.png", strategy=StrategyType.RELATIVE_ONLY)
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))

    dialog.step_list.setCurrentRow(0)

    assert dialog.test_button.isEnabled() is False


def test_test_button_reports_match_found(qtbot, tmp_path):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[40:60, 80:100] = 255
    template = frame[40:60, 80:100].copy()

    template_rel = "session/click_1.png"
    template_full = tmp_path / "templates" / template_rel
    template_full.parent.mkdir(parents=True, exist_ok=True)
    write_image(template_full, template)

    step = _step(template_path=template_rel, strategy=StrategyType.VISUAL_ONLY)
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))
    dialog._screen_capture = FakeScreenCapture(frame)
    dialog.step_list.setCurrentRow(0)

    dialog.test_button.click()

    assert dialog.status_label.text().startswith("Match found: confidence=1.00")


def test_test_button_reports_no_match(qtbot, tmp_path):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    template = np.full((20, 20, 3), 255, dtype=np.uint8)

    template_rel = "session/click_1.png"
    template_full = tmp_path / "templates" / template_rel
    template_full.parent.mkdir(parents=True, exist_ok=True)
    write_image(template_full, template)

    step = _step(template_path=template_rel, strategy=StrategyType.VISUAL_ONLY,
                 confidence_threshold=0.99)
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))
    dialog._screen_capture = FakeScreenCapture(frame)
    dialog.step_list.setCurrentRow(0)

    dialog.test_button.click()

    assert dialog.status_label.text() == "No match found"


def test_step_controls_disabled_when_no_step_is_selected(qtbot, tmp_path):
    # The plan's version of this test asserted the panel is disabled right after
    # the dialog opens, but _refresh_list() auto-selects row 0 whenever the rule
    # has steps -- so the real invariant to pin down is the empty-list one:
    # nothing selected => no index => Run from here (and every other per-step
    # action) is unreachable.
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_step()))
    dialog.step_list.setCurrentRow(0)
    assert dialog.field_panel.isEnabled() is True

    dialog._on_delete_clicked()

    assert dialog.step_list.count() == 0
    assert dialog._current_index is None
    assert dialog.field_panel.isEnabled() is False


def test_run_from_here_executes_only_steps_from_selected_index(qtbot, tmp_path):
    input_controller = FakeInputController()
    engine = PlaybackEngine(
        _window_manager(), _screen_capture(), input_controller,
        ExecutionRepository(connect(":memory:")),
        get_execution_logger(tmp_path / "execution.log"), tmp_path / "templates",
    )
    controller = PlaybackController(engine)

    steps = [_step(name="A", order_index=0), _step(name="B", order_index=1),
             _step(name="C", order_index=2)]
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(*steps), playback_controller=controller)
    dialog.step_list.setCurrentRow(1)

    with qtbot.waitSignal(controller.finished, timeout=2000):
        dialog.run_from_here_button.click()
        assert dialog.step_list.isEnabled() is False

    assert dialog.step_list.isEnabled() is True
    assert len(input_controller.calls) == 2  # only steps B and C ran, not A


def test_recapture_handles_an_event_delivered_from_a_recorder_thread(qtbot, tmp_path):
    """The real PynputRecorder calls back from its own listener thread, never
    from the Qt thread. QTimer.singleShot() started off a thread with no event
    loop never fires, so the capture silently never happened -- the dialog just
    kept waiting. Every other recapture test emits from the main thread, which
    is exactly why they missed this."""
    import threading

    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    dialog.recapture_button.click()

    event = RawEvent(timestamp=0.0, kind="mouse_down", x=50, y=40, button="left")
    thread = threading.Thread(target=lambda: recorder.emit(event))
    thread.start()
    thread.join()

    qtbot.waitUntil(lambda: not dialog._awaiting_recapture, timeout=2000)
    step = dialog.controller.draft.steps[0]
    assert step.template_path is not None
    assert (tmp_path / "templates" / step.template_path).exists()


def _accept_add_step_dialog(monkeypatch, step_type, value):
    """Drives AddStepDialog without a modal loop: fills its widgets and reports
    Accepted, the same way the existing MainWindow tests drive RuleEditorDialog."""
    def fake_exec(dialog):
        dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(step_type))
        dialog.duration_spin.setValue(value)
        return QDialog.Accepted

    monkeypatch.setattr(AddStepDialog, "exec", fake_exec)


def test_add_step_inserts_the_chosen_step_after_the_selected_one(qtbot, tmp_path,
                                                                monkeypatch):
    steps = [_step(name="A", order_index=0), _step(name="B", order_index=1)]
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(*steps))
    dialog.step_list.setCurrentRow(0)
    _accept_add_step_dialog(monkeypatch, StepType.WAIT_FOR_IMAGE, 4000)

    dialog.add_step_button.click()

    names = [s.step_type.value for s in dialog.controller.draft.steps]
    assert names == ["ClickImage", "WaitForImage", "ClickImage"]
    assert dialog.controller.draft.steps[1].params["timeout_ms"] == 4000


def test_add_step_selects_the_new_step_so_recapture_targets_it(qtbot, tmp_path,
                                                              monkeypatch):
    steps = [_step(name="A", order_index=0), _step(name="B", order_index=1)]
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(*steps))
    dialog.step_list.setCurrentRow(0)
    _accept_add_step_dialog(monkeypatch, StepType.WAIT_FOR_IMAGE, 4000)

    dialog.add_step_button.click()

    assert dialog.step_list.currentRow() == 1
    assert dialog._current_index == 1


def test_add_step_cancelled_changes_nothing(qtbot, tmp_path, monkeypatch):
    dialog, _ = _dialog(qtbot, tmp_path)
    dialog.step_list.setCurrentRow(0)
    monkeypatch.setattr(AddStepDialog, "exec", lambda dialog: QDialog.Rejected)

    dialog.add_step_button.click()

    assert len(dialog.controller.draft.steps) == 1


def test_add_step_writes_nothing_to_the_repository_until_save(qtbot, tmp_path,
                                                             monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_rule())
    dialog, _ = _dialog(qtbot, tmp_path, rule=saved_rule,
                        rule_repository=rule_repository)
    dialog.step_list.setCurrentRow(0)
    _accept_add_step_dialog(monkeypatch, StepType.WAIT, 1500)

    dialog.add_step_button.click()

    assert len(rule_repository.get(saved_rule.id).steps) == 1
    dialog._on_save_clicked()
    assert len(rule_repository.get(saved_rule.id).steps) == 2


def _wait_step(step_type=StepType.WAIT_FOR_IMAGE, timeout_ms=5000, name="W"):
    return RuleStep(
        id=None, order_index=0, step_type=step_type, name=name, enabled=True,
        params={"timeout_ms": timeout_ms, "poll_interval_ms": 250},
        template_path=None, confidence_threshold=0.9,
        strategy=StrategyType.VISUAL_ONLY, verification=None,
        screenshot_path=None, delay_after_ms=0,
    )


def _plain_wait_step(duration_ms=800):
    return RuleStep(
        id=None, order_index=0, step_type=StepType.WAIT, name="Pause", enabled=True,
        params={"duration_ms": duration_ms}, template_path=None,
        confidence_threshold=0.9, strategy=StrategyType.VISUAL_ONLY,
        verification=None, screenshot_path=None, delay_after_ms=0,
    )


def test_timeout_spin_shows_the_timeout_of_a_wait_step(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_wait_step(timeout_ms=7000)))

    dialog.step_list.setCurrentRow(0)

    assert dialog.timeout_spin.isEnabled() is True
    assert dialog.timeout_spin.value() == 7000


def test_editing_the_timeout_writes_it_into_the_step_params(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_wait_step(timeout_ms=7000)))
    dialog.step_list.setCurrentRow(0)

    dialog.timeout_spin.setValue(2500)

    params = dialog.controller.draft.steps[0].params
    assert params["timeout_ms"] == 2500
    assert params["poll_interval_ms"] == 250  # untouched


def test_plain_wait_step_edits_its_duration_through_the_same_spin(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_plain_wait_step(800)))
    dialog.step_list.setCurrentRow(0)
    assert dialog.timeout_spin.value() == 800

    dialog.timeout_spin.setValue(1200)

    assert dialog.controller.draft.steps[0].params == {"duration_ms": 1200}


def test_switching_between_steps_does_not_leak_a_timeout_into_the_neighbour(qtbot,
                                                                           tmp_path):
    """Programmatic setValue must not fire valueChanged: otherwise selecting a
    step would write the previous step's timeout into this one's params."""
    dialog, _ = _dialog(qtbot, tmp_path,
                        rule=_rule(_wait_step(timeout_ms=7000, name="first"),
                                   _wait_step(timeout_ms=3000, name="second")))

    dialog.step_list.setCurrentRow(0)
    dialog.step_list.setCurrentRow(1)
    dialog.step_list.setCurrentRow(0)

    assert dialog.controller.draft.steps[0].params["timeout_ms"] == 7000
    assert dialog.controller.draft.steps[1].params["timeout_ms"] == 3000


def test_widgets_that_do_not_apply_are_disabled_per_step_type(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path,
                        rule=_rule(_step(name="Click"), _wait_step(name="WaitImage"),
                                   _plain_wait_step()))

    dialog.step_list.setCurrentRow(0)
    assert (dialog.strategy_combo.isEnabled(), dialog.confidence_spin.isEnabled(),
            dialog.timeout_spin.isEnabled()) == (True, True, False)

    dialog.step_list.setCurrentRow(1)
    assert (dialog.strategy_combo.isEnabled(), dialog.confidence_spin.isEnabled(),
            dialog.timeout_spin.isEnabled()) == (False, True, True)

    dialog.step_list.setCurrentRow(2)
    assert (dialog.strategy_combo.isEnabled(), dialog.confidence_spin.isEnabled(),
            dialog.timeout_spin.isEnabled()) == (False, False, True)


def test_controls_come_back_after_a_successful_recapture(qtbot, tmp_path):
    """The wait disables the whole dialog. If anything on the completion path
    throws before _set_controls_enabled(True), the user is left staring at a
    dead dialog with Save greyed out and no way back except Esc."""
    import threading

    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    dialog.recapture_button.click()

    event = RawEvent(timestamp=0.0, kind="mouse_down", x=50, y=40, button="left")
    thread = threading.Thread(target=lambda: recorder.emit(event))
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: not dialog._awaiting_recapture, timeout=2000)

    assert dialog.field_panel.isEnabled() is True
    assert dialog.buttons.isEnabled() is True
    assert dialog.step_list.isEnabled() is True


def test_recapture_leaves_save_and_cancel_reachable_while_waiting(qtbot, tmp_path):
    """Pressing a button must never lock the user in: while the dialog waits
    for a click on the game, Cancel is the visible way back. Esc alone is not
    discoverable, and the prompt saying so used to be greyed out and hidden
    behind the game window."""
    dialog, _ = _dialog(qtbot, tmp_path)
    dialog.step_list.setCurrentRow(0)

    dialog.recapture_button.click()

    assert dialog._awaiting_recapture is True
    assert dialog.buttons.isEnabled() is True


def test_recapture_prompt_lives_outside_the_panel_it_disables(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path)
    dialog.step_list.setCurrentRow(0)

    dialog.recapture_button.click()

    assert dialog.field_panel.isAncestorOf(dialog.status_label) is False
    assert dialog.status_label.isEnabled() is True
    assert dialog.status_label.text().startswith("Click on the game window")


def test_dialog_stays_on_top_from_the_start(qtbot, tmp_path):
    """activate() raises the game over this dialog, and Windows refuses to let
    a background process take the foreground back, so without this flag the
    prompt is invisible exactly when it matters. The flag is set at
    construction and never toggled: changing it on a visible dialog hides it,
    which ends exec() and closes the editor."""
    dialog, _ = _dialog(qtbot, tmp_path)

    assert bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint) is True

    dialog.step_list.setCurrentRow(0)
    dialog.recapture_button.click()
    QTest.keyClick(dialog, Qt.Key_Escape)

    assert bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint) is True


def test_recapture_gives_up_after_the_timeout_instead_of_waiting_forever(qtbot,
                                                                        tmp_path,
                                                                        monkeypatch):
    from tiles_survive_automation import config

    monkeypatch.setattr(config, "RECAPTURE_TIMEOUT_MS", 50)
    dialog, _ = _dialog(qtbot, tmp_path)
    dialog.step_list.setCurrentRow(0)

    dialog.recapture_button.click()
    qtbot.waitUntil(lambda: not dialog._awaiting_recapture, timeout=2000)

    assert "timed out" in dialog.status_label.text().lower()
    assert dialog.field_panel.isEnabled() is True
    assert dialog.buttons.isEnabled() is True


def test_saving_while_a_recapture_is_pending_stops_the_recorder(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    dialog.recapture_button.click()

    dialog._on_save_clicked()

    assert dialog._awaiting_recapture is False
    assert recorder._on_event is None  # listener released, not left hooked


def test_starting_a_recapture_does_not_close_the_visible_dialog(qtbot, tmp_path):
    """setWindowFlag() hides a visible widget, and hiding a QDialog inside
    exec() ends its modal loop -- pressing Recapture closed the editor and
    threw the draft away. The tests above never caught it because a dialog
    that was never shown cannot be hidden."""
    dialog, _ = _dialog(qtbot, tmp_path)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.step_list.setCurrentRow(0)

    dialog.recapture_button.click()

    assert dialog.isVisible() is True
    assert dialog._awaiting_recapture is True
