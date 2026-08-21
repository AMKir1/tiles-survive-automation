from pathlib import Path

import cv2
import numpy as np


def write_image(path: Path, image: np.ndarray) -> None:
    """cv2.imwrite silently returns False (no exception) on Windows when the
    path contains non-ASCII characters, instead of raising -- so a Cyrillic
    username/repo path would drop every template/screenshot with no visible
    error. imencode + Path.write_bytes goes through Python's own Unicode-safe
    file APIs instead of OpenCV's platform file I/O, and we check the result
    explicitly so a real encoding failure raises instead of failing silently.
    """
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"cv2.imencode failed while writing {path}")
    path.write_bytes(encoded.tobytes())
