"""A game running elevated silently swallows every SendInput from a normal-rights
process: SendInput reports success, the cursor never moves, and the run logs
clicks that never happened. The app must say so instead of looking dead."""

import numpy as np

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.fake_input import (
    FakeInputController,
    FakeManualClickWatcher,
    NoOpInputRecorder,
)
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.ui.main_window import MainWindow
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo


def _window(qtbot, tmp_path, accepts_input: bool):
    window_manager = FakeWindowManager(
        [WindowInfo(hwnd=1, title="TilesSurvive", client_rect=(0, 0, 800, 600))],
        accepts_synthetic_input=accepts_input,
    )
    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(Rule(
        id=None, name="R", description=None, window_title_hint=None,
        steps=[RuleStep(id=None, order_index=0, step_type=StepType.CLICK_IMAGE,
                        name="Click", enabled=True,
                        params={"relative_x": 0.5, "relative_y": 0.5},
                        template_path=None, confidence_threshold=0.9,
                        strategy=StrategyType.RELATIVE_ONLY, verification=None,
                        screenshot_path=None, delay_after_ms=0)],
    ))
    window = MainWindow(
        window_manager=window_manager,
        screen_capture=FakeScreenCapture(np.zeros((600, 800, 3), dtype="uint8")),
        input_recorder=NoOpInputRecorder(),
        input_controller=FakeInputController(),
        manual_click_watcher=FakeManualClickWatcher(),
        rule_repository=rule_repository,
        execution_repository=ExecutionRepository(connect(":memory:")),
        logger=get_execution_logger(tmp_path / "execution.log"),
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        start_emergency_stop=False,
        start_manual_click_watcher=False,
    )
    qtbot.addWidget(window)
    window._refresh_rules()
    window.rule_list.setCurrentRow(0)
    return window


def test_play_warns_when_the_game_window_cannot_receive_synthetic_input(qtbot, tmp_path):
    window = _window(qtbot, tmp_path, accepts_input=False)

    window._on_play_clicked()

    text = window.log_view.toPlainText()
    assert "administrator" in text.lower()
    assert "TilesSurvive" in text


def test_play_stays_quiet_when_the_game_window_accepts_input(qtbot, tmp_path):
    window = _window(qtbot, tmp_path, accepts_input=True)

    window._on_play_clicked()

    assert "administrator" not in window.log_view.toPlainText().lower()
