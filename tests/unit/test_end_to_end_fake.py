import cv2
import numpy as np

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.fake_input import FakeInputController
from tiles_survive_automation.input.models import RawEvent
from tiles_survive_automation.playback.engine import PlaybackEngine
from tiles_survive_automation.playback.state import PlaybackState
from tiles_survive_automation.recorder.recording_session import RecordingSession
from tiles_survive_automation.rules.rule_builder import RuleBuilder
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo


class ScriptedRecorder:
    def __init__(self, events: list[RawEvent]) -> None:
        self._events = events

    def start(self, on_event) -> None:
        self._on_event = on_event

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def emit_all(self) -> None:
        for event in self._events:
            self._on_event(event)


def test_record_save_play_cycle_clicks_expected_coordinates(tmp_path):
    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 200, 100))
    window_manager = FakeWindowManager([window])

    frame = np.full((100, 200, 3), 30, dtype=np.uint8)
    marker = np.full((60, 60, 3), 220, dtype=np.uint8)
    frame[10:70, 40:100] = marker
    capture = FakeScreenCapture(frame)

    events = [
        RawEvent(timestamp=0.0, kind="mouse_down", x=70, y=40, button="left"),
        RawEvent(timestamp=0.05, kind="mouse_up", x=70, y=40, button="left"),
    ]
    recorder = ScriptedRecorder(events)

    templates_dir = tmp_path / "templates"
    screenshots_dir = tmp_path / "screenshots"
    session = RecordingSession(window_manager, capture, recorder, templates_dir,
                                 screenshots_dir)

    # Record
    session.start(hwnd=1)
    recorder.emit_all()
    recorded_steps = session.stop()

    # Save
    rule = RuleBuilder("Собрать ресурсы", window_title_hint="Tiles Survive").build(
        recorded_steps
    )
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(rule)
    loaded_rule = rule_repository.get(saved_rule.id)

    # Play
    input_controller = FakeInputController()
    execution_repository = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")
    engine = PlaybackEngine(window_manager, capture, input_controller,
                              execution_repository, logger, templates_dir)

    context = engine.run(loaded_rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == [("click", 70, 40, "left")]
