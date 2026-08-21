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


def _engine(frame, templates_dir, tmp_path, capture=None):
    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 100, 100))
    window_manager = FakeWindowManager([window])
    capture = capture if capture is not None else FakeScreenCapture(frame)
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


def test_reset_clears_abort_and_next_run_completes(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _click_step(template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(frame, templates_dir, tmp_path)

    engine.abort()
    aborted_context = engine.run(rule, hwnd=1)
    assert aborted_context.state == PlaybackState.STOPPED

    engine.reset()
    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("click", 50, 50, "left")]


class _RaisingInputController(FakeInputController):
    """Fake InputController whose click() raises, to exercise the C3 exception path."""

    def click(self, x: int, y: int, button: str = "left") -> None:
        raise RuntimeError("simulated failure")


def test_exception_during_step_marks_failed_and_releases_input(tmp_path):
    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()

    step = _click_step(template_path=None, strategy=StrategyType.RELATIVE_ONLY)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(frame, templates_dir, tmp_path)
    input_controller = _RaisingInputController()
    engine._input_controller = input_controller

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert context.error_message is not None
    assert ("release_all",) in input_controller.calls

    executions = engine._execution_repository._conn.execute(
        "SELECT status FROM Execution"
    ).fetchall()
    assert executions[-1]["status"] == "FAILED"


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


def test_unresolvable_step_reports_failure_through_step_failure(tmp_path):
    """The failure contract is an object with a message, not a bare None: a
    wait that times out must be able to report its own reason instead of
    inheriting 'could not be resolved by any strategy'."""
    from tiles_survive_automation.playback.engine import StepFailure

    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    step = _step(StepType.CLICK_IMAGE, {}, template_path=None,
                 strategy=StrategyType.RELATIVE_ONLY)
    engine, _ = _engine(frame, templates_dir, tmp_path)

    outcome = engine._execute_step(step, hwnd=1)

    assert isinstance(outcome, StepFailure)
    assert outcome.message == "step 'Step' could not be resolved by any strategy"


class SequenceCapture:
    """FakeScreenCapture hands out one frame forever; a wait that only succeeds
    after a few polls needs the screen to change between grabs. The last frame
    repeats once the sequence runs out."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.grabs = 0

    def grab(self, rect):
        self.grabs += 1
        frame = self._frames.pop(0) if len(self._frames) > 1 else self._frames[0]
        return frame.copy()


def _wait_image_step(step_type, template_path="marker.png", timeout_ms=1000,
                     poll_interval_ms=10, confidence_threshold=0.9):
    return _step(step_type,
                 {"timeout_ms": timeout_ms, "poll_interval_ms": poll_interval_ms},
                 template_path=template_path,
                 confidence_threshold=confidence_threshold,
                 strategy=StrategyType.VISUAL_ONLY, name="Wait for panel")


def _templates_with_marker(tmp_path):
    """Returns (templates_dir, marker, blank_frame, frame_with_marker)."""
    import cv2

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    marker = np.full((10, 10, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(templates_dir / "marker.png"), marker)

    blank = np.full((100, 100, 3), 10, dtype=np.uint8)
    visible = blank.copy()
    visible[20:30, 20:30] = marker
    return templates_dir, marker, blank, visible


def test_wait_for_image_succeeds_when_template_is_already_on_screen(tmp_path):
    templates_dir, _, _, visible = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(visible, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == []  # a wait never clicks


def test_wait_for_image_polls_until_the_template_shows_up(tmp_path):
    templates_dir, _, blank, visible = _templates_with_marker(tmp_path)
    capture = SequenceCapture([blank, blank, visible])
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path, capture=capture)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert capture.grabs == 3


def test_wait_for_image_fails_with_its_own_message_on_timeout(tmp_path):
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, timeout_ms=100, poll_interval_ms=10)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "timed out after 100ms" in context.error_message
    assert "Wait for panel" in context.error_message


class AbortingCapture:
    """Fires engine.abort() from inside a grab, so the abort lands mid-wait
    without a thread and without wall-clock timing in the test."""

    def __init__(self, frame, abort_on_grab):
        self._frame = frame
        self._abort_on_grab = abort_on_grab
        self.engine = None
        self.grabs = 0

    def grab(self, rect):
        self.grabs += 1
        if self.grabs >= self._abort_on_grab:
            self.engine.abort()
        return self._frame.copy()


def test_abort_during_a_wait_stops_the_run_instead_of_waiting_out_the_timeout(tmp_path):
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    capture = AbortingCapture(blank, abort_on_grab=2)
    # A timeout long enough that reaching it would hang the test: the run may
    # only end this quickly because the abort cut the wait short.
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, timeout_ms=60000,
                            poll_interval_ms=10)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path, capture=capture)
    capture.engine = engine

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.STOPPED
    assert context.error_message is None  # aborted, not failed
    assert capture.grabs == 2


def test_wait_image_disappear_succeeds_when_the_template_is_already_gone(tmp_path):
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_IMAGE_DISAPPEAR)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == []


def test_wait_image_disappear_polls_until_the_template_goes_away(tmp_path):
    templates_dir, _, blank, visible = _templates_with_marker(tmp_path)
    capture = SequenceCapture([visible, visible, blank])
    step = _wait_image_step(StepType.WAIT_IMAGE_DISAPPEAR)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path, capture=capture)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert capture.grabs == 3


def test_wait_image_disappear_fails_when_the_template_stays_on_screen(tmp_path):
    templates_dir, _, _, visible = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_IMAGE_DISAPPEAR, timeout_ms=100,
                            poll_interval_ms=10)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(visible, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "waiting for the image to disappear" in context.error_message


def test_wait_step_without_a_template_says_to_use_recapture(tmp_path):
    """Add step creates the step without a picture on purpose -- the user
    attaches it with Recapture afterwards. Forgetting that must produce advice,
    not a cv2 crash or a pointless full-length timeout."""
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, template_path=None,
                            timeout_ms=60000)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "has no template" in context.error_message
    assert "Recapture" in context.error_message


def test_wait_step_with_an_unreadable_template_file_says_so(tmp_path):
    """cv2.imread returns None for a missing or non-ASCII path instead of
    raising, so an unreadable template must be reported, not treated as
    'image not on screen yet'."""
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    (templates_dir / "broken.png").write_bytes(b"not a png")
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, template_path="broken.png",
                            timeout_ms=60000)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "unreadable" in context.error_message
