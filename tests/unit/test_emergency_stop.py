from tiles_survive_automation.input.emergency_stop import EmergencyStop
from tiles_survive_automation.input.fake_input import FakeInputController


def test_trigger_releases_all_held_input_and_calls_callback():
    controller = FakeInputController()
    controller.press_and_hold("left")
    triggered = []

    stop = EmergencyStop(controller, on_trigger=lambda: triggered.append(True))
    stop._trigger()

    assert controller.held_buttons == set()
    assert triggered == [True]


def test_trigger_is_safe_to_call_multiple_times():
    controller = FakeInputController()
    triggered = []
    stop = EmergencyStop(controller, on_trigger=lambda: triggered.append(True))

    stop._trigger()
    stop._trigger()

    assert triggered == [True, True]
