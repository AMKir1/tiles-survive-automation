import numpy as np
import pytest

from tiles_survive_automation.recorder.image_io import write_image


def test_write_image_handles_non_ascii_directory(tmp_path):
    frame = np.full((10, 10, 3), 128, dtype=np.uint8)
    target = tmp_path / "Андрей" / "click_1.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    write_image(target, frame)

    assert target.exists()
    assert target.stat().st_size > 0


def test_write_image_raises_loudly_when_encoding_fails(tmp_path, monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "imencode", lambda ext, img: (False, None))
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    with pytest.raises(RuntimeError):
        write_image(tmp_path / "click_1.png", frame)
