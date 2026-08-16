import time

import pytest

from tiles_survive_automation.input.pynput_recorder import PynputRecorder


@pytest.fixture
def recorder():
    """Fixture that provides a recorder and cleans up listeners after each test."""
    rec = PynputRecorder()
    yield rec
    try:
        rec.stop()
        # Give listeners time to shut down gracefully
        time.sleep(0.1)
    except Exception:
        # Ignore any exceptions during cleanup
        pass


def test_on_click_emits_mouse_down_then_mouse_up(recorder):
    events = []
    recorder.start(on_event=events.append)

    recorder._on_click(10, 20, "left_button_marker", True)   # pressed
    recorder._on_click(10, 20, "left_button_marker", False)  # released

    assert [e.kind for e in events] == ["mouse_down", "mouse_up"]
    assert events[0].x == 10 and events[0].y == 20


def test_on_scroll_emits_scroll_event_with_deltas(recorder):
    events = []
    recorder.start(on_event=events.append)

    recorder._on_scroll(30, 40, 0, -1)

    assert events[0].kind == "scroll"
    assert events[0].scroll_dx == 0
    assert events[0].scroll_dy == -1


def test_pause_suppresses_events_until_resume(recorder):
    events = []
    recorder.start(on_event=events.append)
    recorder.pause()

    recorder._on_click(1, 1, "left_button_marker", True)

    assert events == []

    recorder.resume()
    recorder._on_click(1, 1, "left_button_marker", True)

    assert len(events) == 1


def test_on_key_down_and_up_emit_key_events(recorder):
    events = []
    recorder.start(on_event=events.append)

    recorder._on_key_down("a")
    recorder._on_key_up("a")

    assert [e.kind for e in events] == ["key_down", "key_up"]
    assert events[0].key == "a"
