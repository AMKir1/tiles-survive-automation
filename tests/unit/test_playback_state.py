import pytest

from tiles_survive_automation.playback.state import PlaybackContext, PlaybackState


def test_initial_state_is_idle():
    context = PlaybackContext()

    assert context.state == PlaybackState.IDLE


def test_start_transitions_to_running():
    context = PlaybackContext()

    context.start()

    assert context.state == PlaybackState.RUNNING


def test_start_twice_raises():
    context = PlaybackContext()
    context.start()

    with pytest.raises(RuntimeError):
        context.start()


def test_complete_transitions_running_to_completed():
    context = PlaybackContext()
    context.start()

    context.complete()

    assert context.state == PlaybackState.COMPLETED


def test_fail_stores_error_message():
    context = PlaybackContext()
    context.start()

    context.fail("template not found")

    assert context.state == PlaybackState.FAILED
    assert context.error_message == "template not found"


def test_abort_from_running_sets_stopped():
    context = PlaybackContext()
    context.start()

    context.abort()

    assert context.state == PlaybackState.STOPPED


def test_abort_after_completed_raises():
    context = PlaybackContext()
    context.start()
    context.complete()

    with pytest.raises(RuntimeError):
        context.abort()
