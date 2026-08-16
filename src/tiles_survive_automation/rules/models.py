from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import Enum


class StepType(str, Enum):
    CLICK_IMAGE = "ClickImage"
    RIGHT_CLICK = "RightClick"
    DOUBLE_CLICK = "DoubleClick"
    DRAG = "Drag"
    SCROLL = "Scroll"
    KEY_PRESS = "KeyPress"
    HOTKEY = "Hotkey"
    WAIT = "Wait"
    WAIT_FOR_IMAGE = "WaitForImage"
    WAIT_IMAGE_DISAPPEAR = "WaitImageDisappear"


class StrategyType(str, Enum):
    VISUAL_THEN_RELATIVE = "VISUAL_THEN_RELATIVE"
    VISUAL_ONLY = "VISUAL_ONLY"
    RELATIVE_ONLY = "RELATIVE_ONLY"


@dataclass
class RuleStep:
    id: int | None
    order_index: int
    step_type: StepType
    name: str
    enabled: bool
    params: dict
    template_path: str | None
    confidence_threshold: float
    strategy: StrategyType
    verification: dict | None
    screenshot_path: str | None
    delay_after_ms: int

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "order_index": self.order_index,
            "step_type": self.step_type.value,
            "name": self.name,
            "enabled": int(self.enabled),
            "params_json": json.dumps(self.params),
            "template_path": self.template_path,
            "confidence_threshold": self.confidence_threshold,
            "strategy": self.strategy.value,
            "verification_json": (
                json.dumps(self.verification) if self.verification else None
            ),
            "screenshot_path": self.screenshot_path,
            "delay_after_ms": self.delay_after_ms,
        }

    @classmethod
    def from_row(cls, row: dict) -> "RuleStep":
        return cls(
            id=row["id"],
            order_index=row["order_index"],
            step_type=StepType(row["step_type"]),
            name=row["name"],
            enabled=bool(row["enabled"]),
            params=json.loads(row["params_json"]),
            template_path=row["template_path"],
            confidence_threshold=row["confidence_threshold"],
            strategy=StrategyType(row["strategy"]),
            verification=(
                json.loads(row["verification_json"])
                if row["verification_json"]
                else None
            ),
            screenshot_path=row["screenshot_path"],
            delay_after_ms=row["delay_after_ms"],
        )


@dataclass
class Rule:
    id: int | None
    name: str
    description: str | None
    window_title_hint: str | None
    steps: list[RuleStep] = field(default_factory=list)
