from tiles_survive_automation import config
from tiles_survive_automation.recorder.recording_session import RecordedStep
from tiles_survive_automation.rules.models import (
    Rule,
    RuleStep,
    StepType,
    StrategyType,
)

_DOUBLE_CLICK_DISTANCE = 20


class RuleBuilder:
    def __init__(self, rule_name: str, window_title_hint: str | None) -> None:
        self._rule_name = rule_name
        self._window_title_hint = window_title_hint

    def build(self, recorded: list[RecordedStep]) -> Rule:
        clicks = self._pair_mouse_events(recorded)
        merged = self._merge_double_clicks(clicks)
        steps_with_waits = self._insert_waits(merged)

        rule_steps = [
            self._to_rule_step(index, action)
            for index, action in enumerate(steps_with_waits)
        ]
        return Rule(id=None, name=self._rule_name, description=None,
                    window_title_hint=self._window_title_hint, steps=rule_steps)

    def _pair_mouse_events(self, recorded: list[RecordedStep]) -> list[dict]:
        actions: list[dict] = []
        pending_down: RecordedStep | None = None
        pending_key: RecordedStep | None = None

        for recorded_step in recorded:
            kind = recorded_step.event.kind
            if kind == "mouse_down":
                pending_down = recorded_step
            elif kind == "mouse_up" and pending_down is not None:
                actions.append(self._build_click_or_drag(pending_down, recorded_step))
                pending_down = None
            elif kind == "scroll":
                actions.append({
                    "type": StepType.SCROLL,
                    "timestamp": recorded_step.event.timestamp,
                    "end_timestamp": recorded_step.event.timestamp,
                    "name": "Scroll",
                    "template_path": None,
                    "params": {
                        "relative_x": recorded_step.relative_x,
                        "relative_y": recorded_step.relative_y,
                        "delta": recorded_step.event.scroll_dy,
                    },
                })
            elif kind == "key_down":
                pending_key = recorded_step
            elif kind == "key_up" and pending_key is not None:
                actions.append({
                    "type": StepType.KEY_PRESS,
                    "timestamp": pending_key.event.timestamp,
                    "end_timestamp": recorded_step.event.timestamp,
                    "name": f"KeyPress -> {pending_key.event.key}",
                    "template_path": None,
                    "params": {"key": pending_key.event.key},
                })
                pending_key = None

        return actions

    def _build_click_or_drag(self, down: RecordedStep, up: RecordedStep) -> dict:
        distance = max(abs(down.relative_x - up.relative_x),
                        abs(down.relative_y - up.relative_y))
        duration_ms = round((up.event.timestamp - down.event.timestamp) * 1000)

        if distance * 1000 > config.DRAG_DISTANCE_THRESHOLD_PX:
            return {
                "type": StepType.DRAG,
                "timestamp": down.event.timestamp,
                "end_timestamp": up.event.timestamp,
                "name": "Drag",
                "template_path": down.template_path,
                "params": {
                    "from_relative_x": down.relative_x, "from_relative_y": down.relative_y,
                    "to_relative_x": up.relative_x, "to_relative_y": up.relative_y,
                    "duration_ms": duration_ms,
                },
            }

        step_type = StepType.RIGHT_CLICK if down.event.button == "right" else StepType.CLICK_IMAGE
        name = "Right Click" if down.event.button == "right" else "Click"
        return {
            "type": step_type,
            "timestamp": down.event.timestamp,
            "end_timestamp": up.event.timestamp,
            "name": name,
            "template_path": down.template_path,
            "params": {"relative_x": down.relative_x, "relative_y": down.relative_y},
        }

    def _merge_double_clicks(self, actions: list[dict]) -> list[dict]:
        merged: list[dict] = []
        for action in actions:
            if (
                merged
                and action["type"] == StepType.CLICK_IMAGE
                and merged[-1]["type"] == StepType.CLICK_IMAGE
                and (action["timestamp"] - merged[-1]["timestamp"]) * 1000
                    <= config.DOUBLE_CLICK_INTERVAL_MS
            ):
                # Check if clicks are at the same location
                distance = max(
                    abs(action["params"]["relative_x"] - merged[-1]["params"]["relative_x"]),
                    abs(action["params"]["relative_y"] - merged[-1]["params"]["relative_y"])
                )
                if distance * 1000 <= _DOUBLE_CLICK_DISTANCE:
                    merged[-1] = {**merged[-1], "type": StepType.DOUBLE_CLICK,
                                   "name": "Double Click"}
                    continue
            merged.append(action)
        return merged

    def _insert_waits(self, actions: list[dict]) -> list[dict]:
        result: list[dict] = []
        previous_end = None
        for action in actions:
            if previous_end is not None:
                gap_ms = round((action["timestamp"] - previous_end) * 1000)
                if gap_ms > config.WAIT_GAP_THRESHOLD_MS:
                    result.append({
                        "type": StepType.WAIT, "timestamp": previous_end,
                        "name": "Wait", "template_path": None,
                        "params": {"duration_ms": gap_ms},
                    })
            result.append(action)
            previous_end = action.get("end_timestamp", action["timestamp"])
        return result

    def _to_rule_step(self, index: int, action: dict) -> RuleStep:
        step_type = action["type"]
        return RuleStep(
            id=None, order_index=index, step_type=step_type, name=action["name"],
            enabled=True, params=action["params"], template_path=action["template_path"],
            confidence_threshold=config.DEFAULT_CONFIDENCE_THRESHOLD,
            strategy=StrategyType.VISUAL_THEN_RELATIVE if action["template_path"]
                else StrategyType.RELATIVE_ONLY,
            verification=None, screenshot_path=None, delay_after_ms=0,
        )
