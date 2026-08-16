import numpy as np

from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.models import RawEvent
from tiles_survive_automation.recorder.recording_session import RecordingSession
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo


class ScriptedRecorder:
    """Fake InputRecorder that replays a fixed list of RawEvent on start()."""

    def __init__(self, events: list[RawEvent]) -> None:
        self._events = events
        self._paused = False

    def start(self, on_event) -> None:
        self._on_event = on_event

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        pass

    def emit_all(self) -> None:
        for event in self._events:
            if not self._paused:
                self._on_event(event)


def _session(events, tmp_path):
    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 200, 100))
    window_manager = FakeWindowManager([window])
    frame = np.full((100, 200, 3), 50, dtype=np.uint8)
    capture = FakeScreenCapture(frame)
    recorder = ScriptedRecorder(events)

    session = RecordingSession(
        window_manager=window_manager, screen_capture=capture,
        input_recorder=recorder, templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
    )
    return session, recorder


def test_click_inside_window_produces_recorded_step_with_template(tmp_path):
    events = [
        RawEvent(timestamp=0.0, kind="mouse_down", x=50, y=40, button="left"),
        RawEvent(timestamp=0.1, kind="mouse_up", x=50, y=40, button="left"),
    ]
    session, recorder = _session(events, tmp_path)

    session.start(hwnd=1)
    recorder.emit_all()
    steps = session.stop()

    assert [s.event.kind for s in steps] == ["mouse_down", "mouse_up"]
    assert steps[0].relative_x == 0.25  # 50 / 200
    assert steps[0].relative_y == 0.4   # 40 / 100
    assert steps[0].template_path is not None
    assert (tmp_path / "templates" / steps[0].template_path).exists()


def test_click_outside_client_rect_is_dropped(tmp_path):
    events = [
        RawEvent(timestamp=0.0, kind="mouse_down", x=500, y=500, button="left"),
    ]
    session, recorder = _session(events, tmp_path)

    session.start(hwnd=1)
    recorder.emit_all()
    steps = session.stop()

    assert steps == []


def test_pause_drops_events_until_resume(tmp_path):
    events = [RawEvent(timestamp=0.0, kind="mouse_down", x=10, y=10, button="left")]
    session, recorder = _session(events, tmp_path)

    session.start(hwnd=1)
    session.pause()
    recorder.emit_all()
    steps = session.stop()

    assert steps == []
