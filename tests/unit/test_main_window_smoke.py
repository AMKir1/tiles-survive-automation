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
