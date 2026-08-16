class FakeInputController:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.held_buttons: set[str] = set()
        self.held_keys: set[str] = set()

    def click(self, x: int, y: int, button: str = "left") -> None:
        self.calls.append(("click", x, y, button))

    def double_click(self, x: int, y: int) -> None:
        self.calls.append(("double_click", x, y))

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int,
              duration_ms: int) -> None:
        self.calls.append(("drag", from_x, from_y, to_x, to_y, duration_ms))

    def scroll(self, x: int, y: int, delta: int) -> None:
        self.calls.append(("scroll", x, y, delta))

    def key_press(self, key: str) -> None:
        self.calls.append(("key_press", key))

    def hotkey(self, keys: list[str]) -> None:
        self.calls.append(("hotkey", tuple(keys)))

    def press_and_hold(self, button: str) -> None:
        self.held_buttons.add(button)
        self.calls.append(("press_and_hold", button))

    def press_and_hold_key(self, key: str) -> None:
        self.held_keys.add(key)
        self.calls.append(("press_and_hold_key", key))

    def release_all(self) -> None:
        self.held_buttons.clear()
        self.held_keys.clear()
        self.calls.append(("release_all",))
