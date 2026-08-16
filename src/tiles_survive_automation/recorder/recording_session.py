from dataclasses import dataclass
from pathlib import Path

import cv2

from tiles_survive_automation.capture.ports import ScreenCapture
from tiles_survive_automation.input.models import RawEvent
from tiles_survive_automation.input.ports import InputRecorder
from tiles_survive_automation.window.ports import WindowManager

TEMPLATE_HALF_SIZE = 30


@dataclass
class RecordedStep:
    event: RawEvent
    relative_x: float | None
    relative_y: float | None
    template_path: str | None
    screenshot_path: str | None


class RecordingSession:
    def __init__(self, window_manager: WindowManager, screen_capture: ScreenCapture,
                 input_recorder: InputRecorder, templates_dir: Path,
                 screenshots_dir: Path) -> None:
        self._window_manager = window_manager
        self._screen_capture = screen_capture
        self._input_recorder = input_recorder
        self._templates_dir = templates_dir
        self._screenshots_dir = screenshots_dir
        self._hwnd: int | None = None
        self._steps: list[RecordedStep] = []
        self._click_index = 0

    def start(self, hwnd: int) -> None:
        self._hwnd = hwnd
        self._steps = []
        self._click_index = 0
        self._input_recorder.start(on_event=self._on_event)

    def pause(self) -> None:
        self._input_recorder.pause()

    def resume(self) -> None:
        self._input_recorder.resume()

    def stop(self) -> list[RecordedStep]:
        self._input_recorder.stop()
        return self._steps

    def _on_event(self, event: RawEvent) -> None:
        if event.x is None or event.y is None:
            self._steps.append(RecordedStep(event=event, relative_x=None,
                                              relative_y=None, template_path=None,
                                              screenshot_path=None))
            return

        left, top, width, height = self._window_manager.get_client_rect(self._hwnd)
        client_x, client_y = event.x - left, event.y - top
        if not (0 <= client_x < width and 0 <= client_y < height):
            return

        relative_x, relative_y = client_x / width, client_y / height
        template_path, screenshot_path = None, None

        if event.kind == "mouse_down":
            template_path, screenshot_path = self._capture_click(
                left, top, width, height, client_x, client_y,
            )

        relative_event = RawEvent(timestamp=event.timestamp, kind=event.kind,
                                   x=client_x, y=client_y, button=event.button,
                                   key=event.key, scroll_dx=event.scroll_dx,
                                   scroll_dy=event.scroll_dy)
        self._steps.append(RecordedStep(event=relative_event, relative_x=relative_x,
                                          relative_y=relative_y,
                                          template_path=template_path,
                                          screenshot_path=screenshot_path))

    def _capture_click(self, left, top, width, height, client_x, client_y):
        self._click_index += 1
        frame = self._screen_capture.grab((left, top, width, height))

        screenshot_dir = self._screenshots_dir
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_name = f"click_{self._click_index}.png"
        cv2.imwrite(str(screenshot_dir / screenshot_name), frame)

        x0 = max(0, client_x - TEMPLATE_HALF_SIZE)
        y0 = max(0, client_y - TEMPLATE_HALF_SIZE)
        x1 = min(width, client_x + TEMPLATE_HALF_SIZE)
        y1 = min(height, client_y + TEMPLATE_HALF_SIZE)
        template = frame[y0:y1, x0:x1]

        self._templates_dir.mkdir(parents=True, exist_ok=True)
        template_name = f"click_{self._click_index}.png"
        cv2.imwrite(str(self._templates_dir / template_name), template)

        return template_name, str(screenshot_dir / screenshot_name)
