from tiles_survive_automation.input.fake_input import FakeInputController


def test_click_is_recorded():
    controller = FakeInputController()

    controller.click(10, 20, button="left")

    assert controller.calls == [("click", 10, 20, "left")]


def test_drag_marks_button_held_until_completion_recorded():
    controller = FakeInputController()

    controller.drag(0, 0, 50, 50, duration_ms=100)

    assert ("drag", 0, 0, 50, 50, 100) in controller.calls
    assert controller.held_buttons == set()


def test_press_and_hold_tracks_held_button():
    controller = FakeInputController()

    controller.press_and_hold("left")

    assert "left" in controller.held_buttons


def test_release_all_clears_held_buttons_and_keys():
    controller = FakeInputController()
    controller.press_and_hold("left")
    controller.press_and_hold_key("shift")

    controller.release_all()

    assert controller.held_buttons == set()
    assert controller.held_keys == set()
    assert ("release_all",) in controller.calls
