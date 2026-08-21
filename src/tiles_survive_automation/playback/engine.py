import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from tiles_survive_automation import config
from tiles_survive_automation.capture.ports import ScreenCapture
from tiles_survive_automation.input.ports import InputController
from tiles_survive_automation.playback.state import PlaybackContext
from tiles_survive_automation.playback.strategies import resolve_relative_point
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.vision.template_matcher import TemplateMatcher
from tiles_survive_automation.window.ports import WindowManager


@dataclass
class StepFailure:
    """A step that could not be carried out, with the reason to show the user.

    Was a bare `None`, which forced run() to invent one fixed message for every
    kind of failure -- wrong as soon as a wait can time out for its own reason.
    """

    message: str


class PlaybackEngine:
    def __init__(self, window_manager: WindowManager, screen_capture: ScreenCapture,
                 input_controller: InputController, execution_repository: ExecutionRepository,
                 logger: logging.Logger, templates_dir: Path) -> None:
        self._window_manager = window_manager
        self._screen_capture = screen_capture
        self._input_controller = input_controller
        self._execution_repository = execution_repository
        self._logger = logger
        self._templates_dir = templates_dir
        self._matcher = TemplateMatcher()
        self._abort_event = threading.Event()

    def abort(self) -> None:
        self._abort_event.set()

    def reset(self) -> None:
        """Clear a previously-set abort flag so a fresh run() isn't a one-shot latch.

        Must be called by the caller (PlaybackController.run_async) BEFORE spawning
        a new run, not from inside run() itself -- run() intentionally honors an
        abort() that happened before it started (see test_abort_before_run_stops_immediately).
        """
        self._abort_event.clear()

    def run(self, rule: Rule, hwnd: int) -> PlaybackContext:
        context = PlaybackContext()
        execution_id = self._execution_repository.start_execution("RULE", rule.id or 0)

        if self._abort_event.is_set():
            context.start()
            context.abort()
            self._execution_repository.finish_execution(execution_id, "STOPPED", None)
            return context

        context.start()
        self._window_manager.activate(hwnd)

        for step in [s for s in rule.steps if s.enabled]:
            if self._abort_event.is_set():
                context.abort()
                self._input_controller.release_all()
                self._execution_repository.finish_execution(execution_id, "STOPPED", None)
                return context

            try:
                outcome = self._execute_step(step, hwnd)
            except Exception as e:
                message = f"step '{step.name}' raised an exception: {e}"
                self._input_controller.release_all()
                self._logger.exception(message, extra={"rule_name": rule.name})
                context.fail(message)
                self._execution_repository.finish_execution(execution_id, "FAILED", message)
                return context

            if isinstance(outcome, StepFailure):
                message = outcome.message
                self._logger.error(message, extra={"rule_name": rule.name})
                self._execution_repository.log_step(
                    execution_id, rule.id or 0, step.id or 0, step.name, None, None,
                    None, None, "FAILED", message,
                )
                context.fail(message)
                self._execution_repository.finish_execution(execution_id, "FAILED", message)
                return context

            x, y, matched_template, confidence, description = outcome
            self._logger.info(description, extra={"rule_name": rule.name})
            self._execution_repository.log_step(
                execution_id, rule.id or 0, step.id or 0, step.name, matched_template,
                confidence, x, y, "SUCCESS", None,
            )

        # The in-loop check only catches an abort raised before the NEXT step,
        # so an abort during the last step (a long Wait or WaitForImage is where
        # F9 actually lands) used to fall through and report COMPLETED.
        if self._abort_event.is_set():
            context.abort()
            self._input_controller.release_all()
            self._execution_repository.finish_execution(execution_id, "STOPPED", None)
            return context

        context.complete()
        self._execution_repository.finish_execution(execution_id, "SUCCESS", None)
        return context

    def _execute_step(self, step: RuleStep, hwnd: int):
        left, top, width, height = self._window_manager.get_client_rect(hwnd)

        if step.step_type == StepType.WAIT:
            # Use the abort event as the timeout gate (instead of time.sleep) so a
            # multi-second Wait is interrupted immediately by F9, not just at the
            # start of the next loop iteration.
            self._abort_event.wait(step.params["duration_ms"] / 1000)
            return (None, None, None, None, f"Wait {step.params['duration_ms']}ms")

        if step.step_type == StepType.KEY_PRESS:
            self._input_controller.key_press(step.params["key"])
            return (None, None, None, None, f"KeyPress {step.params['key']}")

        if step.step_type in (StepType.WAIT_FOR_IMAGE,
                              StepType.WAIT_IMAGE_DISAPPEAR):
            return self._wait_for_image(step, (left, top, width, height))

        frame = self._screen_capture.grab((left, top, width, height))

        if step.step_type == StepType.DRAG:
            from_point = self._resolve_point(step, frame, width, height,
                                               "from_relative_x", "from_relative_y")
            if from_point is None:
                return StepFailure(
                    f"step '{step.name}' could not be resolved by any strategy")
            to_point = resolve_relative_point(step.params, "to_relative_x",
                                                "to_relative_y", width, height)
            if to_point is None:
                return StepFailure(
                    f"step '{step.name}' could not be resolved by any strategy")
            from_x, from_y, matched_template, confidence = from_point
            to_x, to_y = to_point
            duration_ms = step.params.get("duration_ms", 200)
            abs_from_x, abs_from_y = left + from_x, top + from_y
            abs_to_x, abs_to_y = left + to_x, top + to_y
            self._logger.info(
                f"About to drag from ({abs_from_x!r}:{type(abs_from_x).__name__}, "
                f"{abs_from_y!r}:{type(abs_from_y).__name__}) to "
                f"({abs_to_x!r}:{type(abs_to_x).__name__}, "
                f"{abs_to_y!r}:{type(abs_to_y).__name__}) duration_ms={duration_ms!r}"
            )
            self._input_controller.drag(abs_from_x, abs_from_y, abs_to_x, abs_to_y, duration_ms)
            return (from_x, from_y, matched_template, confidence,
                    f"Drag from x={abs_from_x} y={abs_from_y} to x={abs_to_x} y={abs_to_y}")

        point = self._resolve_point(step, frame, width, height, "relative_x", "relative_y")
        if point is None:
            return StepFailure(
                f"step '{step.name}' could not be resolved by any strategy")
        x, y, matched_template, confidence = point
        abs_x, abs_y = left + x, top + y

        self._logger.info(
            f"About to {step.step_type.value} at ({abs_x!r}:{type(abs_x).__name__}, "
            f"{abs_y!r}:{type(abs_y).__name__})"
        )

        if step.step_type == StepType.RIGHT_CLICK:
            self._input_controller.click(abs_x, abs_y, button="right")
        elif step.step_type == StepType.DOUBLE_CLICK:
            self._input_controller.double_click(abs_x, abs_y)
        elif step.step_type == StepType.SCROLL:
            self._input_controller.scroll(abs_x, abs_y, step.params.get("delta", 0))
        else:
            self._input_controller.click(abs_x, abs_y)

        return (x, y, matched_template, confidence,
                f"Click x={abs_x} y={abs_y}")

    def _wait_for_image(self, step: RuleStep, rect: tuple[int, int, int, int]):
        """Poll the screen until the step's template is present (WaitForImage)
        or gone (WaitImageDisappear), or until the timeout runs out.

        The gap between polls goes through the abort event rather than
        time.sleep so F9 cuts a 10-second wait short instead of being noticed
        only once the wait expires.
        """
        if not step.template_path:
            return StepFailure(f"step '{step.name}' has no template - use "
                               f"Recapture in the Rule Editor first")
        template_path = self._templates_dir / step.template_path
        template = cv2.imread(str(template_path))
        if template is None:
            return StepFailure(f"step '{step.name}' template file is missing or "
                               f"unreadable: {template_path}")
        want_visible = step.step_type == StepType.WAIT_FOR_IMAGE
        timeout_ms = step.params.get("timeout_ms", config.WAIT_FOR_IMAGE_TIMEOUT_MS)
        poll_s = step.params.get("poll_interval_ms",
                                 config.WAIT_POLL_INTERVAL_MS) / 1000
        started = time.monotonic()
        deadline = started + timeout_ms / 1000

        while True:
            frame = self._screen_capture.grab(rect)
            match = self._matcher.find(frame, template, step.confidence_threshold)
            elapsed_ms = round((time.monotonic() - started) * 1000)

            if (match is not None) == want_visible:
                if want_visible:
                    return (*match.center, step.template_path, match.confidence,
                            f"WaitForImage matched after {elapsed_ms}ms "
                            f"(confidence={match.confidence:.2f})")
                return (None, None, None, None,
                        f"WaitImageDisappear satisfied after {elapsed_ms}ms")

            if time.monotonic() >= deadline:
                waited_for = "appear" if want_visible else "disappear"
                return StepFailure(
                    f"step '{step.name}' timed out after {timeout_ms}ms waiting "
                    f"for the image to {waited_for}")

            if self._abort_event.wait(poll_s):
                # Not a failure: the top of run()'s loop turns a set abort event
                # into STOPPED. Same shape as the plain Wait branch.
                return (None, None, None, None,
                        f"{step.step_type.value} aborted after {elapsed_ms}ms")

    def _resolve_point(self, step: RuleStep, frame, width: int, height: int,
                         x_key: str, y_key: str):
        if step.strategy != StrategyType.RELATIVE_ONLY and step.template_path:
            template = cv2.imread(str(self._templates_dir / step.template_path))
            if template is not None:
                match = self._matcher.find(frame, template, step.confidence_threshold)
                if match is not None:
                    return (*match.center, step.template_path, match.confidence)

        if step.strategy != StrategyType.VISUAL_ONLY:
            center = resolve_relative_point(step.params, x_key, y_key, width, height)
            if center is not None:
                return (*center, None, None)

        return None
