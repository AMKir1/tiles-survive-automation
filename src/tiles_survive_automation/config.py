from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
LOGS_DIR = DATA_DIR / "logs"
DATABASE_PATH = DATA_DIR / "database.db"

EMERGENCY_STOP_KEY = "f9"
DEFAULT_CONFIDENCE_THRESHOLD = 0.85
WAIT_FOR_IMAGE_TIMEOUT_MS = 10000
WAIT_POLL_INTERVAL_MS = 250
RECAPTURE_TIMEOUT_MS = 30000
DRAG_DISTANCE_THRESHOLD_PX = 6
WAIT_GAP_THRESHOLD_MS = 300
DOUBLE_CLICK_INTERVAL_MS = 400


def ensure_data_dirs() -> None:
    for directory in (DATA_DIR, TEMPLATES_DIR, SCREENSHOTS_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
