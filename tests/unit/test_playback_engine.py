import numpy as np
import pytest

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.fake_input import FakeInputController
from tiles_survive_automation.playback.engine import PlaybackEngine
from tiles_survive_automation.playback.state import PlaybackState
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo


def _engine(frame, templates_dir, tmp_path):
    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 100, 100))
    window_manager = FakeWindowManager([window])
    capture = FakeScreenCapture(frame)
    input_controller = FakeInputController()
    repo = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    engine = PlaybackEngine(window_manager, capture, input_controller, repo, logger,
                              templates_dir=templates_dir)
    return engine, input_controller


def _step(step_type, params, template_path=None, confidence_threshold=0.9,
          strategy=StrategyType.VISUAL_THEN_RELATIVE, name="Step"):
    return RuleStep(id=1, order_index=0, step_type=step_type, name=name, enabled=True,
                     params=params, template_path=template_path,
                     confidence_threshold=confidence_threshold, strategy=strategy,
                     verification=None, screenshot_path=None, delay_after_ms=0)


def _click_step(template_path, confidence_threshold=0.9, strategy=StrategyType.VISUAL_THEN_RELATIVE):
    return _step(StepType.CLICK_IMAGE, {"relative_x": 0.5, "relative_y": 0.5},
                 template_path=template_path, confidence_threshold=confidence_threshold,
                 strategy=strategy, name="Click")


def test_visual_match_clicks_matched_center(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    marker = np.full((10, 10, 3), 200, dtype=np.uint8)
    frame[20:30, 20:30] = marker
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    import cv2
    cv2.imwrite(str(templates_dir / "marker.png"), marker)

    step = _click_step("marker.png")
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("click", 25, 25, "left")]


def test_falls_back_to_relative_when_template_not_found(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    import cv2
    absent_marker = np.full((10, 10, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(templates_dir / "marker.png"), absent_marker)

    step = _click_step("marker.png")
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("click", 50, 50, "left")]


def test_stops_and_fails_when_no_strategy_resolves(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.CLICK_IMAGE, {}, template_path=None,
                 strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert input_controller.calls == []


def test_abort_before_run_stops_immediately(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _click_step(template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None,
                steps=[step, step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    engine.abort()
    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.STOPPED
    assert input_controller.calls == []


def test_right_click_step_uses_right_button(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.RIGHT_CLICK, {"relative_x": 0.2, "relative_y": 0.3},
                 template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("click", 20, 30, "right")]


def test_double_click_step_calls_double_click(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.DOUBLE_CLICK, {"relative_x": 0.4, "relative_y": 0.4},
                 template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("double_click", 40, 40)]


def test_scroll_step_passes_delta_from_params(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.SCROLL, {"relative_x": 0.5, "relative_y": 0.5, "delta": -3},
                 template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("scroll", 50, 50, -3)]


def test_key_press_step_does_not_resolve_coordinates(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.KEY_PRESS, {"key": "a"}, template_path=None,
                 strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("key_press", "a")]


def test_wait_step_does_not_call_input_controller(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.WAIT, {"duration_ms": 5}, template_path=None,
                 strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == []


def test_drag_step_resolves_from_and_to_points_relatively(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _step(StepType.DRAG, {
        "from_relative_x": 0.1, "from_relative_y": 0.1,
        "to_relative_x": 0.8, "to_relative_y": 0.8, "duration_ms": 150,
    }, template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("drag", 10, 10, 80, 80, 150)]


class _AbortOnFirstClickInputController(FakeInputController):
    """Subclass of FakeInputController that aborts the engine on first click."""

    def __init__(self, engine):
        super().__init__()
        self._engine = engine
        self._click_count = 0

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._click_count += 1
        if self._click_count == 1:
            # Trigger abort on first click (simulating F9 pressed mid-step)
            self._engine.abort()
        super().click(x, y, button)


def test_abort_mid_run_calls_release_all_and_stops(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    # Create a rule with 2 click steps so there's a second step to be interrupted
    step1 = _click_step(template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    step2 = _click_step(template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None,
                steps=[step1, step2])

    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 100, 100))
    window_manager = FakeWindowManager([window])
    capture = FakeScreenCapture(frame)
    repo = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    engine = PlaybackEngine(window_manager, capture, None, repo, logger,
                            templates_dir=templates_dir)
    # Wire the custom input controller that aborts on first click
    input_controller = _AbortOnFirstClickInputController(engine)
    engine._input_controller = input_controller

    context = engine.run(rule, hwnd=1)

    # Assert the abort path was taken mid-loop
    assert context.state == PlaybackState.STOPPED
    # release_all() should have been called when abort was detected
    assert ("release_all",) in input_controller.calls
    # Only one click should have happened (step 1); step 2 was never executed
    click_calls = [c for c in input_controller.calls if c[0] == "click"]
    assert len(click_calls) == 1
