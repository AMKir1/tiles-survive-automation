from pathlib import Path

import numpy as np
import pytest

from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.input.models import RawEvent
from tiles_survive_automation.recorder.recording_session import (
    RecordingSession,
    _write_image,
)
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
    assert steps[0].screenshot_path is not None
    assert Path(steps[0].screenshot_path).exists()


def test_click_outside_client_rect_is_dropped(tmp_path):
    events = [
        RawEvent(timestamp=0.0, kind="mouse_down", x=500, y=500, button="left"),
    ]
    session, recorder = _session(events, tmp_path)

    session.start(hwnd=1)
    recorder.emit_all()
    steps = session.stop()

    assert steps == []


def test_two_recording_sessions_do_not_collide_on_template_paths(tmp_path):
    events = [
        RawEvent(timestamp=0.0, kind="mouse_down", x=50, y=40, button="left"),
        RawEvent(timestamp=0.1, kind="mouse_up", x=50, y=40, button="left"),
    ]

    session1, recorder1 = _session(events, tmp_path)
    session1.start(hwnd=1)
    recorder1.emit_all()
    steps1 = session1.stop()

    session2, recorder2 = _session(events, tmp_path)
    session2.start(hwnd=1)
    recorder2.emit_all()
    steps2 = session2.stop()

    template_path_1 = steps1[0].template_path
    template_path_2 = steps2[0].template_path

    assert template_path_1 != template_path_2
    assert (tmp_path / "templates" / template_path_1).exists()
    assert (tmp_path / "templates" / template_path_2).exists()


def test_write_image_handles_non_ascii_directory(tmp_path):
    frame = np.full((10, 10, 3), 128, dtype=np.uint8)
    target = tmp_path / "Андрей" / "click_1.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    _write_image(target, frame)

    assert target.exists()
    assert target.stat().st_size > 0


def test_write_image_raises_loudly_when_encoding_fails(tmp_path, monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "imencode", lambda ext, img: (False, None))
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    with pytest.raises(RuntimeError):
        _write_image(tmp_path / "click_1.png", frame)


def test_pause_drops_events_until_resume(tmp_path):
    events = [RawEvent(timestamp=0.0, kind="mouse_down", x=10, y=10, button="left")]
    session, recorder = _session(events, tmp_path)

    session.start(hwnd=1)
    session.pause()
    recorder.emit_all()
    steps = session.stop()

    assert steps == []
