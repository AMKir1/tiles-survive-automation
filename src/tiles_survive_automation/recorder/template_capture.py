import numpy as np

TEMPLATE_HALF_SIZE = 30


def capture_template(frame: np.ndarray, client_x: int, client_y: int,
                     half_size: int = TEMPLATE_HALF_SIZE) -> np.ndarray:
    height, width = frame.shape[:2]
    x0 = max(0, client_x - half_size)
    y0 = max(0, client_y - half_size)
    x1 = min(width, client_x + half_size)
    y1 = min(height, client_y + half_size)
    return frame[y0:y1, x0:x1]
