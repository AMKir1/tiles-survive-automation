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
        result = cv2.matchTemplate(frame, template, cv2.TM_SQDIFF_NORMED)
        min_val, _, min_loc, _ = cv2.minMaxLoc(result)

        # Convert dissimilarity to similarity (1 - dissimilarity)
        # min_val ranges from 0 (perfect match) to 1 (no match)
        # confidence ranges from 1 (perfect match) to 0 (no match)
        confidence = 1.0 - min_val

        if confidence < confidence_threshold:
            return None

        height, width = template.shape[:2]
        return MatchResult(x=min_loc[0], y=min_loc[1], width=width, height=height,
                            confidence=float(confidence))
