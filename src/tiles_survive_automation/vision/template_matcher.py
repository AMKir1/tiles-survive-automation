from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class MatchResult:
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


class TemplateMatcher:
    def find(self, frame: np.ndarray, template: np.ndarray,
             confidence_threshold: float) -> MatchResult | None:
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < confidence_threshold:
            return None

        height, width = template.shape[:2]
        return MatchResult(x=max_loc[0], y=max_loc[1], width=width, height=height,
                            confidence=float(max_val))
