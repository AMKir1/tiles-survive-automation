# MVP2 / Rule Editor, волна 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в `RuleEditorDialog` четыре недостающие фичи Rule Editor из родительской спеки: preview screenshot/template выбранного шага, recapture template (живая перезапись через реальный клик по игре), test step (dry-run матч без клика) и run-from-step (Play начиная с выбранного шага до конца).

**Architecture:** Все четыре фичи — новые методы/виджеты в уже существующих `RuleEditorController`/`RuleEditorDialog`. Диалог получает дополнительные зависимости (`window_manager`, `screen_capture`, `input_recorder`, `playback_controller`, `templates_dir`, `screenshots_dir`, `hwnd`) через конструктор, `MainWindow` их туда пробрасывает. Recapture и test-step переиспользуют существующие чистые (без PySide6) компоненты — `capture_template`/`write_image` (выносятся из `RecordingSession` в общие модули) и `TemplateMatcher`. Run-from-step переиспользует **тот же** `PlaybackEngine`/`PlaybackController`, что и `MainWindow` — не создаёт новый, чтобы F9 (`EmergencyStop`) продолжал прерывать run-from-step.

**Tech Stack:** Python 3.12+, PySide6, pytest, pytest-qt (`qtbot`) — уже в проекте.

**Spec:** `docs/specs/2026-08-19-mvp2-rule-editor-wave2-design.md`

## Global Constraints

- `RuleEditorController`, `recorder/image_io.py`, `recorder/template_capture.py` не импортируют PySide6 — только `RuleEditorDialog` может.
- `RuleEditorDialog` переиспользует `MainWindow`'s единственный `PlaybackEngine`/`PlaybackController` (передаётся в конструктор), а не создаёт новый — иначе F9 не прерывает run-from-step (см. спеку, раздел 2).
- `hwnd` передаётся диалогу один раз при создании (диалог модальный — окно игры не меняется, пока диалог открыт).
- Recapture пишет template/screenshot PNG на диск сразу в момент клика, не в момент Save диалога; если пользователь потом жмёт Cancel — файл остаётся неиспользуемым на диске (осознанно принятое ограничение, как и в волне 1).
- Recapture НЕ выполняет клик по игре — только фиксирует координату и делает снимок. Test step НЕ выполняет клик — только матчинг.
- Все новые тесты в `tests/unit/test_rule_editor_dialog.py` используют fake-реализации (`FakeWindowManager`, `FakeScreenCapture`, локальный `ScriptedRecorder`, `FakeInputController`) — реальный Win32 не задействуется. Тесты `RuleRepository`-уровня используют реальный `RuleRepository(connect(":memory:"))`, как уже принято в проекте (не моки БД).
- Вне рамок этой волны — не трогать: `WaitForImage`/`WaitImageDisappear`, Debug Mode, добавление новых шагов в Rule.

---

## Файловая карта

```
src/tiles_survive_automation/
  recorder/
    image_io.py                     # новый: write_image()
    template_capture.py             # новый: capture_template()
    recording_session.py            # изменяется: использует image_io/template_capture
  ui/
    controllers/
      rule_editor_controller.py     # изменяется: + draft_from()
    dialogs/
      rule_editor_dialog.py         # изменяется: + preview/recapture/test/run-from-step
    main_window.py                  # изменяется: пробрасывает новые зависимости в диалог
tests/
  unit/
    test_image_io.py                # новый (перенесённые из test_recording_session.py тесты)
    test_template_capture.py        # новый
    test_recording_session.py       # изменяется: импорт из новых модулей
    test_rule_editor_controller.py  # изменяется: + тесты draft_from
    test_rule_editor_dialog.py      # новый: все Qt-тесты диалога (перенос + новые)
    test_main_window_smoke.py       # изменяется: обновлённая сигнатура RuleEditorDialog
docs/
  manual-testing/
    mvp2-rule-editor-wave2-checklist.md  # новый
```

---

### Task 1: Вынести `write_image`/`capture_template` в общие модули

**Files:**
- Create: `src/tiles_survive_automation/recorder/image_io.py`
- Create: `src/tiles_survive_automation/recorder/template_capture.py`
- Modify: `src/tiles_survive_automation/recorder/recording_session.py`
- Create: `tests/unit/test_image_io.py`
- Create: `tests/unit/test_template_capture.py`
- Modify: `tests/unit/test_recording_session.py`

**Interfaces:**
- Produces: `image_io.write_image(path: Path, image: np.ndarray) -> None`, `template_capture.capture_template(frame: np.ndarray, client_x: int, client_y: int, half_size: int = 30) -> np.ndarray`, `template_capture.TEMPLATE_HALF_SIZE = 30`.

- [ ] **Step 1: Написать падающий тест для `write_image`**

Создать `tests/unit/test_image_io.py`:

```python
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
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_image_io.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'tiles_survive_automation.recorder.image_io'`

- [ ] **Step 3: Реализовать `image_io.py`**

```python
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
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_image_io.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Написать падающие тесты для `capture_template`**

Создать `tests/unit/test_template_capture.py`:

```python
import numpy as np

from tiles_survive_automation.recorder.template_capture import capture_template


def test_crops_square_region_around_point():
    frame = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100, 100, 3)

    template = capture_template(frame, client_x=50, client_y=50, half_size=10)

    assert template.shape == (20, 20, 3)
    assert np.array_equal(template, frame[40:60, 40:60])


def test_clamps_to_frame_bounds_near_top_left_corner():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    template = capture_template(frame, client_x=2, client_y=3, half_size=10)

    assert template.shape == (13, 12, 3)  # y: 0..13, x: 0..12


def test_clamps_to_frame_bounds_near_bottom_right_corner():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    template = capture_template(frame, client_x=98, client_y=97, half_size=10)

    assert template.shape == (13, 12, 3)  # y: 87..100, x: 88..100


def test_default_half_size_matches_recording_session_convention():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)

    template = capture_template(frame, client_x=100, client_y=100)

    assert template.shape == (60, 60, 3)  # 2 * TEMPLATE_HALF_SIZE (30)
```

- [ ] **Step 6: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_template_capture.py -v`
Expected: FAIL с `ModuleNotFoundError`

- [ ] **Step 7: Реализовать `template_capture.py`**

```python
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
```

- [ ] **Step 8: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_template_capture.py -v`
Expected: PASS (4 passed)

- [ ] **Step 9: Отрефакторить `recording_session.py` на использование новых модулей**

В `src/tiles_survive_automation/recorder/recording_session.py`:
- Удалить `import cv2`, константу `TEMPLATE_HALF_SIZE = 30` и функцию `_write_image` (строки 1-26 текущего файла).
- Добавить:
  ```python
  from tiles_survive_automation.recorder.image_io import write_image
  from tiles_survive_automation.recorder.template_capture import capture_template
  ```
- В `_capture_click` заменить:
  ```python
  _write_image(screenshot_dir / screenshot_name, frame)
  ```
  на
  ```python
  write_image(screenshot_dir / screenshot_name, frame)
  ```
  и заменить блок
  ```python
  x0 = max(0, client_x - TEMPLATE_HALF_SIZE)
  y0 = max(0, client_y - TEMPLATE_HALF_SIZE)
  x1 = min(width, client_x + TEMPLATE_HALF_SIZE)
  y1 = min(height, client_y + TEMPLATE_HALF_SIZE)
  template = frame[y0:y1, x0:x1]
  ```
  на
  ```python
  template = capture_template(frame, client_x, client_y)
  ```
  и
  ```python
  _write_image(template_dir / template_name, template)
  ```
  на
  ```python
  write_image(template_dir / template_name, template)
  ```

- [ ] **Step 10: Обновить `test_recording_session.py`**

Заменить импорт:
```python
from tiles_survive_automation.recorder.recording_session import (
    RecordingSession,
    _write_image,
)
```
на
```python
from tiles_survive_automation.recorder.recording_session import RecordingSession
```
Удалить из файла тесты `test_write_image_handles_non_ascii_directory` и `test_write_image_raises_loudly_when_encoding_fails` (перенесены в `test_image_io.py` на Step 1) — теперь они не нужны здесь и ссылаются на удалённый импорт.

- [ ] **Step 11: Прогнать весь набор тестов, убедиться, что регрессий нет**

Run: `uv run pytest tests/unit/test_recording_session.py tests/unit/test_image_io.py tests/unit/test_template_capture.py -v`
Expected: все PASS

- [ ] **Step 12: Commit**

```bash
git add src/tiles_survive_automation/recorder/image_io.py \
        src/tiles_survive_automation/recorder/template_capture.py \
        src/tiles_survive_automation/recorder/recording_session.py \
        tests/unit/test_image_io.py tests/unit/test_template_capture.py \
        tests/unit/test_recording_session.py
git commit -m "refactor: extract write_image/capture_template for reuse by Rule Editor recapture"
```

---

### Task 2: `RuleEditorController.draft_from(index)`

**Files:**
- Modify: `src/tiles_survive_automation/ui/controllers/rule_editor_controller.py`
- Modify: `tests/unit/test_rule_editor_controller.py`

**Interfaces:**
- Consumes: `RuleEditorController.__init__(rule, rule_repository)`, `self._draft: Rule` (уже существует).
- Produces: `RuleEditorController.draft_from(index: int) -> Rule` — используется в Task 6 (`RuleEditorDialog._on_run_from_here_clicked`).

- [ ] **Step 1: Написать падающие тесты**

В `tests/unit/test_rule_editor_controller.py` добавить в конец файла:

```python
def test_draft_from_returns_rule_with_steps_from_index_onward():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    sliced = controller.draft_from(1)

    assert [s.name for s in sliced.steps] == ["B", "C"]
    assert sliced.id == controller.draft.id
    assert sliced.name == controller.draft.name


def test_draft_from_index_zero_returns_all_steps():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    sliced = controller.draft_from(0)

    assert [s.name for s in sliced.steps] == ["A", "B", "C"]


def test_draft_from_index_past_end_returns_empty_steps():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    sliced = controller.draft_from(10)

    assert sliced.steps == []


def test_draft_from_does_not_mutate_original_draft():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.draft_from(1)

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C"]
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v -k draft_from`
Expected: FAIL с `AttributeError: 'RuleEditorController' object has no attribute 'draft_from'`

- [ ] **Step 3: Реализовать `draft_from`**

В `src/tiles_survive_automation/ui/controllers/rule_editor_controller.py` добавить метод (после `update_step`, перед `save`):

```python
    def draft_from(self, index: int) -> Rule:
        return replace(self._draft, steps=list(self._draft.steps[index:]))
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v -k draft_from`
Expected: PASS (4 passed)

- [ ] **Step 5: Прогнать весь файл тестов контроллера**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/ui/controllers/rule_editor_controller.py \
        tests/unit/test_rule_editor_controller.py
git commit -m "feat: add RuleEditorController.draft_from for run-from-step"
```

---

### Task 3: Расширить конструктор `RuleEditorDialog`, пробросить зависимости из `MainWindow`, добавить preview

**Files:**
- Modify: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `src/tiles_survive_automation/ui/main_window.py`
- Create: `tests/unit/test_rule_editor_dialog.py`
- Modify: `tests/unit/test_main_window_smoke.py`

**Interfaces:**
- Consumes: `RuleEditorController.draft_from` (Task 2), `image_io.write_image` (Task 1, используется тестами).
- Produces: `RuleEditorDialog.__init__(rule, rule_repository, window_manager, screen_capture, input_recorder, playback_controller, templates_dir, screenshots_dir, hwnd, parent=None)`; атрибуты `self._window_manager`, `self._screen_capture`, `self._input_recorder`, `self._playback_controller`, `self._templates_dir: Path`, `self._screenshots_dir: Path`, `self._hwnd`, `self.screenshot_preview: QLabel`, `self.template_preview: QLabel`, `self.status_label: QLabel`, `self.step_actions_layout: QHBoxLayout` (пустой контейнер для кнопок Task 4/5/6), `self.buttons: QDialogButtonBox` (переименован из локальной переменной). Используется в Task 4, 5, 6.

Это единственная задача, меняющая сигнатуру конструктора — Task 4/5/6 только добавляют кнопки/методы поверх неё.

- [ ] **Step 1: Создать `tests/unit/test_rule_editor_dialog.py` с общими фикстурами и первым падающим тестом**

```python
from pathlib import Path

import numpy as np

from tiles_survive_automation.capture.fake_capture import FakeScreenCapture
from tiles_survive_automation.recorder.image_io import write_image
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog
from tiles_survive_automation.window.fake_window_manager import FakeWindowManager
from tiles_survive_automation.window.ports import WindowInfo

HWND = 1


class ScriptedRecorder:
    """Fake InputRecorder whose on_event callback can be driven manually via emit()."""

    def __init__(self) -> None:
        self._on_event = None

    def start(self, on_event) -> None:
        self._on_event = on_event

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        self._on_event = None

    def emit(self, event) -> None:
        assert self._on_event is not None, "recorder not started"
        self._on_event(event)


def _window_manager() -> FakeWindowManager:
    return FakeWindowManager(
        [WindowInfo(hwnd=HWND, title="Tiles Survive", client_rect=(0, 0, 200, 100))]
    )


def _screen_capture() -> FakeScreenCapture:
    frame = np.full((100, 200, 3), 50, dtype=np.uint8)
    return FakeScreenCapture(frame)


def _step(step_id=None, order_index=0, name="A", template_path=None,
          screenshot_path=None, strategy=StrategyType.RELATIVE_ONLY,
          confidence_threshold=0.9) -> RuleStep:
    return RuleStep(
        id=step_id, order_index=order_index, step_type=StepType.CLICK_IMAGE,
        name=name, enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
        template_path=template_path, confidence_threshold=confidence_threshold,
        strategy=strategy, verification=None,
        screenshot_path=screenshot_path, delay_after_ms=0,
    )


def _rule(*steps) -> Rule:
    return Rule(id=None, name="R", description=None, window_title_hint=None,
                steps=list(steps) or [_step()])


def _dialog(qtbot, tmp_path, rule=None, rule_repository=None, recorder=None,
            playback_controller=None, hwnd=HWND):
    rule_repository = rule_repository or RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(rule or _rule())
    dialog = RuleEditorDialog(
        saved_rule, rule_repository,
        window_manager=_window_manager(),
        screen_capture=_screen_capture(),
        input_recorder=recorder or ScriptedRecorder(),
        playback_controller=playback_controller,
        templates_dir=tmp_path / "templates",
        screenshots_dir=tmp_path / "screenshots",
        hwnd=hwnd,
    )
    qtbot.addWidget(dialog)
    return dialog, rule_repository


def test_dialog_shows_no_image_when_step_has_no_paths(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_step()))

    dialog.step_list.setCurrentRow(0)

    assert dialog.screenshot_preview.text() == "No image"
    assert dialog.template_preview.text() == "No image"


def test_dialog_shows_previews_when_step_has_paths(qtbot, tmp_path):
    screenshot_path = tmp_path / "shot.png"
    template_rel = "session/click_1.png"
    frame = np.full((10, 10, 3), 200, dtype=np.uint8)
    write_image(screenshot_path, frame)
    template_full = tmp_path / "templates" / template_rel
    template_full.parent.mkdir(parents=True, exist_ok=True)
    write_image(template_full, frame[:6, :6])

    step = _step(template_path=template_rel, screenshot_path=str(screenshot_path))
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))

    dialog.step_list.setCurrentRow(0)

    assert dialog.screenshot_preview.text() == ""
    assert not dialog.screenshot_preview.pixmap().isNull()
    assert dialog.template_preview.text() == ""
    assert not dialog.template_preview.pixmap().isNull()
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v`
Expected: FAIL — `TypeError: RuleEditorDialog.__init__() got an unexpected keyword argument 'window_manager'`

- [ ] **Step 3: Переписать `rule_editor_dialog.py` целиком**

Полное содержимое `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py` (заменяет весь текущий файл):

```python
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tiles_survive_automation.rules.models import StrategyType
from tiles_survive_automation.ui.controllers.rule_editor_controller import (
    RuleEditorController,
)

PREVIEW_SIZE = 160


class RuleEditorDialog(QDialog):
    def __init__(self, rule, rule_repository, window_manager, screen_capture,
                 input_recorder, playback_controller, templates_dir,
                 screenshots_dir, hwnd, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Rule — {rule.name}")
        self.controller = RuleEditorController(rule, rule_repository)
        self._window_manager = window_manager
        self._screen_capture = screen_capture
        self._input_recorder = input_recorder
        self._playback_controller = playback_controller
        self._templates_dir = Path(templates_dir)
        self._screenshots_dir = Path(screenshots_dir)
        self._hwnd = hwnd
        self._current_index: int | None = None
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(self._on_step_selected)

        up_button = QPushButton("Up")
        down_button = QPushButton("Down")
        delete_button = QPushButton("Delete")
        up_button.clicked.connect(self._on_up_clicked)
        down_button.clicked.connect(self._on_down_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)

        list_buttons = QHBoxLayout()
        for button in (up_button, down_button, delete_button):
            list_buttons.addWidget(button)

        left = QVBoxLayout()
        left.addWidget(self.step_list)
        left.addLayout(list_buttons)
        left_widget = QWidget()
        left_widget.setLayout(left)

        self.name_edit = QLineEdit()
        self.enabled_check = QCheckBox()
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 600_000)
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.01)
        self.strategy_combo = QComboBox()
        for strategy in StrategyType:
            self.strategy_combo.addItem(strategy.value, userData=strategy)

        self.name_edit.editingFinished.connect(
            lambda: self._on_field_changed("name", self.name_edit.text()))
        self.enabled_check.toggled.connect(
            lambda value: self._on_field_changed("enabled", value))
        self.delay_spin.valueChanged.connect(
            lambda value: self._on_field_changed("delay_after_ms", value))
        self.confidence_spin.valueChanged.connect(
            lambda value: self._on_field_changed("confidence_threshold", value))
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Enabled", self.enabled_check)
        form.addRow("Delay after (ms)", self.delay_spin)
        form.addRow("Confidence threshold", self.confidence_spin)
        form.addRow("Strategy", self.strategy_combo)

        self.screenshot_preview = QLabel("No image")
        self.screenshot_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.screenshot_preview.setAlignment(Qt.AlignCenter)
        self.template_preview = QLabel("No image")
        self.template_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.template_preview.setAlignment(Qt.AlignCenter)

        previews = QHBoxLayout()
        previews.addWidget(self.screenshot_preview)
        previews.addWidget(self.template_preview)

        self.status_label = QLabel("")

        # Populated by Recapture/Test/Run-from-here buttons (see rest of wave 2).
        self.step_actions_layout = QHBoxLayout()

        field_column = QVBoxLayout()
        field_column.addLayout(form)
        field_column.addLayout(previews)
        field_column.addLayout(self.step_actions_layout)
        field_column.addWidget(self.status_label)

        self.field_panel = QWidget()
        self.field_panel.setLayout(field_column)
        self.field_panel.setEnabled(False)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_save_clicked)
        self.buttons.rejected.connect(self.reject)

        split = QHBoxLayout()
        split.addWidget(left_widget)
        split.addWidget(self.field_panel)

        outer = QVBoxLayout()
        outer.addLayout(split)
        outer.addWidget(self.buttons)
        self.setLayout(outer)

    def _refresh_list(self) -> None:
        self.step_list.blockSignals(True)
        previous_row = self.step_list.currentRow()
        self.step_list.clear()
        for step in self.controller.draft.steps:
            self.step_list.addItem(f"{step.order_index}: {step.step_type.value} — {step.name}")
            if not step.enabled:
                self.step_list.item(self.step_list.count() - 1).setForeground(QColor(Qt.gray))
        self.step_list.blockSignals(False)

        row_count = self.step_list.count()
        if row_count == 0:
            self._current_index = None
            self.field_panel.setEnabled(False)
            return
        new_row = min(previous_row, row_count - 1) if previous_row >= 0 else 0
        self.step_list.setCurrentRow(new_row)

    def _on_step_selected(self, row: int) -> None:
        self._current_index = row if row >= 0 else None
        if self._current_index is None:
            self.field_panel.setEnabled(False)
            return
        self.field_panel.setEnabled(True)
        step = self.controller.draft.steps[self._current_index]
        for widget in (self.name_edit, self.enabled_check, self.delay_spin,
                       self.confidence_spin, self.strategy_combo):
            widget.blockSignals(True)
        self.name_edit.setText(step.name)
        self.enabled_check.setChecked(step.enabled)
        self.delay_spin.setValue(step.delay_after_ms)
        self.confidence_spin.setValue(step.confidence_threshold)
        self.strategy_combo.setCurrentIndex(self.strategy_combo.findData(step.strategy))
        for widget in (self.name_edit, self.enabled_check, self.delay_spin,
                       self.confidence_spin, self.strategy_combo):
            widget.blockSignals(False)
        self._refresh_previews(step)
        self.status_label.setText("")

    def _refresh_previews(self, step) -> None:
        self._set_preview(self.screenshot_preview,
                           Path(step.screenshot_path) if step.screenshot_path else None)
        self._set_preview(self.template_preview,
                           self._templates_dir / step.template_path
                           if step.template_path else None)

    def _set_preview(self, label: QLabel, path: Path | None) -> None:
        if path is None or not path.exists():
            label.setText("No image")
            return
        pixmap = QPixmap(str(path))
        label.setPixmap(pixmap.scaled(PREVIEW_SIZE, PREVIEW_SIZE, Qt.KeepAspectRatio))

    def _on_strategy_changed(self, index: int) -> None:
        if index < 0:
            return
        self._on_field_changed("strategy", StrategyType(self.strategy_combo.itemData(index)))

    def _on_field_changed(self, field: str, value) -> None:
        if self._current_index is None:
            return
        self.controller.update_step(self._current_index, **{field: value})
        if field in ("name", "enabled"):
            self._refresh_list()

    def _on_up_clicked(self) -> None:
        if self._current_index is None:
            return
        index = self._current_index
        self.controller.move_up(index)
        self._refresh_list()
        self.step_list.setCurrentRow(max(index - 1, 0))

    def _on_down_clicked(self) -> None:
        if self._current_index is None:
            return
        index = self._current_index
        self.controller.move_down(index)
        self._refresh_list()
        self.step_list.setCurrentRow(min(index + 1, self.step_list.count() - 1))

    def _on_delete_clicked(self) -> None:
        if self._current_index is None:
            return
        self.controller.delete_step(self._current_index)
        self._refresh_list()

    def _on_save_clicked(self) -> None:
        self.controller.save()
        self.accept()
```

- [ ] **Step 4: Обновить `main_window.py`**

В `__init__` (после `self._logger = logger`) добавить:

```python
        self._screen_capture = screen_capture
        self._input_recorder = input_recorder
        self._screenshots_dir = screenshots_dir
```

Заменить `_on_edit_clicked`:

```python
    def _on_edit_clicked(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        dialog = RuleEditorDialog(
            rule, self._rule_repository,
            window_manager=self._window_manager,
            screen_capture=self._screen_capture,
            input_recorder=self._input_recorder,
            playback_controller=self._playback_controller,
            templates_dir=self._templates_dir,
            screenshots_dir=self._screenshots_dir,
            hwnd=self._current_hwnd(),
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self._refresh_rules()
```

- [ ] **Step 5: Перенести и обновить два существующих прямых теста `RuleEditorDialog` из `test_main_window_smoke.py`**

В `tests/unit/test_main_window_smoke.py` удалить тесты `test_changing_strategy_combo_survives_real_save` и `test_editing_name_refreshes_step_list_row_without_reorder` (они переезжают в новый файл).

Добавить их в `tests/unit/test_rule_editor_dialog.py` (после тестов из Step 1), с обновлённой сигнатурой:

```python
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


def test_changing_strategy_combo_survives_real_save(qtbot, tmp_path):
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_rule(_step(strategy=StrategyType.RELATIVE_ONLY)))
    assert saved_rule.steps[0].strategy == StrategyType.RELATIVE_ONLY

    dialog, _ = _dialog(qtbot, tmp_path, rule=saved_rule, rule_repository=rule_repository)

    dialog.step_list.setCurrentRow(0)
    new_index = dialog.strategy_combo.findText(StrategyType.VISUAL_ONLY.value)
    assert new_index >= 0
    dialog.strategy_combo.setCurrentIndex(new_index)

    # Must not raise (pre-fix, this would AttributeError inside step.to_row()
    # because itemData() round-trips as a bare str, not a StrategyType).
    dialog._on_save_clicked()

    reloaded = rule_repository.get(saved_rule.id)
    assert reloaded.steps[0].strategy == StrategyType.VISUAL_ONLY
    assert isinstance(reloaded.steps[0].strategy, StrategyType)


def test_editing_name_refreshes_step_list_row_without_reorder(qtbot, tmp_path):
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_rule())

    dialog, _ = _dialog(qtbot, tmp_path, rule=saved_rule, rule_repository=rule_repository)

    dialog.step_list.setCurrentRow(0)
    dialog.name_edit.setText("Renamed Step")
    dialog.name_edit.editingFinished.emit()

    assert "Renamed Step" in dialog.step_list.item(0).text()
    assert dialog.controller.draft.steps[0].name == "Renamed Step"

    dialog.enabled_check.setChecked(False)

    assert dialog.step_list.item(0).foreground().color() == QColor(Qt.gray)
```

Обе теперь используют `_dialog()`/`_rule()`/`_step()` из этого файла вместо `_make_rule()` из `test_main_window_smoke.py` — добавить недостающие импорты (`RuleRepository`, `connect`, `StrategyType`) в начало `test_rule_editor_dialog.py`, если их там ещё нет после Step 1.

Оставшиеся два теста в `test_main_window_smoke.py` (`test_edit_button_saves_changes_made_in_the_dialog`, `test_edit_button_cancelled_leaves_rule_unchanged`) не трогать — они monkeypatch'ат `RuleEditorDialog.exec` напрямую и не зависят от нового конструктора.

- [ ] **Step 6: Запустить полный набор тестов**

Run: `uv run pytest tests/unit/ -v`
Expected: все PASS (включая переехавшие и новые тесты; `test_main_window_smoke.py` и `test_rule_editor_dialog.py` оба зелёные)

- [ ] **Step 7: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py \
        src/tiles_survive_automation/ui/main_window.py \
        tests/unit/test_rule_editor_dialog.py tests/unit/test_main_window_smoke.py
git commit -m "feat: wire Rule Editor dialog dependencies for wave2, add screenshot/template preview"
```

---

### Task 4: Recapture template

**Files:**
- Modify: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `tests/unit/test_rule_editor_dialog.py`

**Interfaces:**
- Consumes: `image_io.write_image`, `template_capture.capture_template` (Task 1); `self._window_manager.activate/get_client_rect`, `self._input_recorder.start/stop`, `self._screen_capture.grab` (уже в конструкторе с Task 3); `self.controller.update_step` (существует с волны 1).
- Produces: `self.recapture_button: QPushButton`, `self._awaiting_recapture: bool`, `self._cancel_recapture()` — не используется другими задачами напрямую, но `_set_controls_enabled` (см. ниже) переиспользуется в Task 6.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_rule_editor_dialog.py`:

```python
from tiles_survive_automation.input.models import RawEvent
from PySide6.QtTest import QTest


def test_recapture_updates_step_paths_on_click_inside_window(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)

    dialog.recapture_button.click()
    assert dialog._awaiting_recapture is True
    assert dialog.status_label.text().startswith("Click on the game window")

    recorder.emit(RawEvent(timestamp=0.0, kind="mouse_down", x=50, y=40, button="left"))
    qtbot.waitUntil(lambda: not dialog._awaiting_recapture, timeout=1000)

    step = dialog.controller.draft.steps[0]
    assert step.template_path is not None
    assert (tmp_path / "templates" / step.template_path).exists()
    assert step.screenshot_path is not None
    assert Path(step.screenshot_path).exists()
    assert dialog.status_label.text() == "Template recaptured."


def test_recapture_ignores_click_outside_client_rect(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    original_template_path = dialog.controller.draft.steps[0].template_path

    dialog.recapture_button.click()
    recorder.emit(RawEvent(timestamp=0.0, kind="mouse_down", x=5000, y=5000, button="left"))
    qtbot.wait(50)

    assert dialog._awaiting_recapture is True
    assert dialog.controller.draft.steps[0].template_path == original_template_path


def test_escape_cancels_recapture_without_changing_draft(qtbot, tmp_path):
    recorder = ScriptedRecorder()
    dialog, _ = _dialog(qtbot, tmp_path, recorder=recorder)
    dialog.step_list.setCurrentRow(0)
    original_template_path = dialog.controller.draft.steps[0].template_path

    dialog.recapture_button.click()
    QTest.keyClick(dialog, Qt.Key_Escape)

    assert dialog._awaiting_recapture is False
    assert dialog.controller.draft.steps[0].template_path == original_template_path
    assert dialog.status_label.text() == "Recapture cancelled."
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v -k recapture or escape`
Expected: FAIL — `AttributeError: 'RuleEditorDialog' object has no attribute 'recapture_button'`

- [ ] **Step 3: Реализовать recapture**

В `rule_editor_dialog.py` добавить импорты (в начало файла, рядом с существующими):

```python
import uuid

from PySide6.QtCore import QTimer

from tiles_survive_automation.recorder.image_io import write_image
from tiles_survive_automation.recorder.template_capture import capture_template
```

В `__init__`, после `self._current_index: int | None = None`, добавить:

```python
        self._awaiting_recapture = False
```

В `_build_ui`, сразу после `self.status_label = QLabel("")` и создания `self.step_actions_layout`, добавить кнопку:

```python
        self.recapture_button = QPushButton("Recapture")
        self.recapture_button.clicked.connect(self._on_recapture_clicked)
        self.step_actions_layout.addWidget(self.recapture_button)
```

(вставить строки создания кнопки после строки `self.step_actions_layout = QHBoxLayout()`, до `field_column = QVBoxLayout()`).

В конец класса (после `_on_save_clicked`) добавить:

```python
    def _on_recapture_clicked(self) -> None:
        if self._current_index is None or self._hwnd is None:
            return
        self._awaiting_recapture = True
        self._set_controls_enabled(False)
        self.status_label.setText("Click on the game window now… (Esc to cancel)")
        self._window_manager.activate(self._hwnd)
        self._recapture_session_id = uuid.uuid4().hex[:8]
        self._input_recorder.start(on_event=self._on_recapture_event)

    def _on_recapture_event(self, event) -> None:
        QTimer.singleShot(0, lambda: self._handle_recapture_event(event))

    def _handle_recapture_event(self, event) -> None:
        if not self._awaiting_recapture:
            return
        if event.kind != "mouse_down" or event.x is None or event.y is None:
            return
        left, top, width, height = self._window_manager.get_client_rect(self._hwnd)
        client_x, client_y = event.x - left, event.y - top
        if not (0 <= client_x < width and 0 <= client_y < height):
            return

        self._input_recorder.stop()
        frame = self._screen_capture.grab((left, top, width, height))

        screenshot_dir = self._screenshots_dir / self._recapture_session_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / "recapture.png"
        write_image(screenshot_path, frame)

        template = capture_template(frame, client_x, client_y)
        template_dir = self._templates_dir / self._recapture_session_id
        template_dir.mkdir(parents=True, exist_ok=True)
        write_image(template_dir / "recapture.png", template)

        self.controller.update_step(
            self._current_index,
            template_path=f"{self._recapture_session_id}/recapture.png",
            screenshot_path=str(screenshot_path),
        )
        self._awaiting_recapture = False
        self._on_step_selected(self._current_index)
        self.status_label.setText("Template recaptured.")
        self._set_controls_enabled(True)

    def _cancel_recapture(self) -> None:
        self._input_recorder.stop()
        self._awaiting_recapture = False
        self.status_label.setText("Recapture cancelled.")
        self._set_controls_enabled(True)

    def keyPressEvent(self, event) -> None:
        if self._awaiting_recapture and event.key() == Qt.Key_Escape:
            self._cancel_recapture()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._awaiting_recapture:
            self._input_recorder.stop()
        super().closeEvent(event)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.step_list.setEnabled(enabled)
        self.field_panel.setEnabled(enabled and self._current_index is not None)
        self.buttons.setEnabled(enabled)
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v`
Expected: все PASS

- [ ] **Step 5: Прогнать полный набор тестов**

Run: `uv run pytest tests/unit/ -v`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py \
        tests/unit/test_rule_editor_dialog.py
git commit -m "feat: add Recapture template to Rule Editor"
```

---

### Task 5: Test step (dry-run матч)

**Files:**
- Modify: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `tests/unit/test_rule_editor_dialog.py`

**Interfaces:**
- Consumes: `vision.template_matcher.TemplateMatcher.find(frame, template, confidence_threshold) -> MatchResult | None` (существует), `MatchResult.center -> (x, y)`, `MatchResult.confidence: float`.
- Produces: `self.test_button: QPushButton` — не используется другими задачами.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_rule_editor_dialog.py`:

```python
def test_test_button_disabled_when_step_has_no_template(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_step(template_path=None)))

    dialog.step_list.setCurrentRow(0)

    assert dialog.test_button.isEnabled() is False


def test_test_button_disabled_when_strategy_is_relative_only(qtbot, tmp_path):
    step = _step(template_path="session/click_1.png", strategy=StrategyType.RELATIVE_ONLY)
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))

    dialog.step_list.setCurrentRow(0)

    assert dialog.test_button.isEnabled() is False


def test_test_button_reports_match_found(qtbot, tmp_path):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[40:60, 80:100] = 255
    template = frame[40:60, 80:100].copy()

    template_rel = "session/click_1.png"
    template_full = tmp_path / "templates" / template_rel
    template_full.parent.mkdir(parents=True, exist_ok=True)
    write_image(template_full, template)

    step = _step(template_path=template_rel, strategy=StrategyType.VISUAL_ONLY)
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))
    dialog._screen_capture = FakeScreenCapture(frame)
    dialog.step_list.setCurrentRow(0)

    dialog.test_button.click()

    assert dialog.status_label.text().startswith("Match found: confidence=1.00")


def test_test_button_reports_no_match(qtbot, tmp_path):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    template = np.full((20, 20, 3), 255, dtype=np.uint8)

    template_rel = "session/click_1.png"
    template_full = tmp_path / "templates" / template_rel
    template_full.parent.mkdir(parents=True, exist_ok=True)
    write_image(template_full, template)

    step = _step(template_path=template_rel, strategy=StrategyType.VISUAL_ONLY,
                 confidence_threshold=0.99)
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))
    dialog._screen_capture = FakeScreenCapture(frame)
    dialog.step_list.setCurrentRow(0)

    dialog.test_button.click()

    assert dialog.status_label.text() == "No match found"
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v -k test_button`
Expected: FAIL — `AttributeError: 'RuleEditorDialog' object has no attribute 'test_button'`

- [ ] **Step 3: Реализовать test step**

В `rule_editor_dialog.py` добавить импорты:

```python
import cv2

from tiles_survive_automation.vision.template_matcher import TemplateMatcher
```

В `__init__`, после `self._awaiting_recapture = False`, добавить:

```python
        self._matcher = TemplateMatcher()
```

В `_build_ui`, сразу после блока создания `self.recapture_button` (Task 4), добавить:

```python
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._on_test_clicked)
        self.step_actions_layout.addWidget(self.test_button)
```

В `_on_step_selected`, после строки `self._refresh_previews(step)`, добавить:

```python
        can_test = bool(step.template_path) and step.strategy != StrategyType.RELATIVE_ONLY
        self.test_button.setEnabled(can_test)
```

Добавить метод (рядом с `_on_recapture_clicked`):

```python
    def _on_test_clicked(self) -> None:
        if self._current_index is None or self._hwnd is None:
            return
        step = self.controller.draft.steps[self._current_index]
        if not step.template_path:
            return
        left, top, width, height = self._window_manager.get_client_rect(self._hwnd)
        frame = self._screen_capture.grab((left, top, width, height))
        template = cv2.imread(str(self._templates_dir / step.template_path))
        if template is None:
            self.status_label.setText("Template file not found.")
            return
        match = self._matcher.find(frame, template, step.confidence_threshold)
        if match is None:
            self.status_label.setText("No match found")
            return
        x, y = match.center
        self.status_label.setText(
            f"Match found: confidence={match.confidence:.2f} at ({x}, {y})")
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v`
Expected: все PASS

- [ ] **Step 5: Прогнать полный набор тестов**

Run: `uv run pytest tests/unit/ -v`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py \
        tests/unit/test_rule_editor_dialog.py
git commit -m "feat: add Test step dry-run match to Rule Editor"
```

---

### Task 6: Run-from-step + ручной чек-лист

**Files:**
- Modify: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `tests/unit/test_rule_editor_dialog.py`
- Create: `docs/manual-testing/mvp2-rule-editor-wave2-checklist.md`

**Interfaces:**
- Consumes: `self.controller.draft_from(index)` (Task 2), `self._playback_controller.run_async(rule, hwnd)` / `.finished: Signal` (существует, `ui/controllers/playback_controller.py`), `self._set_controls_enabled` (Task 4).
- Produces: `self.run_from_here_button: QPushButton` — конец волны 2, ничего дальше не потребляет.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/unit/test_rule_editor_dialog.py`:

```python
from tiles_survive_automation.app_logging.structured_logger import get_execution_logger
from tiles_survive_automation.input.fake_input import FakeInputController
from tiles_survive_automation.playback.engine import PlaybackEngine
from tiles_survive_automation.storage.execution_repository import ExecutionRepository
from tiles_survive_automation.ui.controllers.playback_controller import PlaybackController


def test_run_from_here_disabled_without_selection(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path)

    assert dialog.field_panel.isEnabled() is False  # no step selected yet


def test_run_from_here_executes_only_steps_from_selected_index(qtbot, tmp_path):
    input_controller = FakeInputController()
    engine = PlaybackEngine(
        _window_manager(), _screen_capture(), input_controller,
        ExecutionRepository(connect(":memory:")),
        get_execution_logger(tmp_path / "execution.log"), tmp_path / "templates",
    )
    controller = PlaybackController(engine)

    steps = [_step(name="A", order_index=0), _step(name="B", order_index=1),
             _step(name="C", order_index=2)]
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(*steps), playback_controller=controller)
    dialog.step_list.setCurrentRow(1)

    with qtbot.waitSignal(controller.finished, timeout=2000):
        dialog.run_from_here_button.click()
        assert dialog.step_list.isEnabled() is False

    assert dialog.step_list.isEnabled() is True
    assert len(input_controller.calls) == 2  # only steps B and C ran, not A
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v -k run_from_here`
Expected: FAIL — `AttributeError: 'RuleEditorDialog' object has no attribute 'run_from_here_button'`

- [ ] **Step 3: Реализовать run-from-step**

В `_build_ui`, сразу после блока `self.test_button` (Task 5), добавить:

```python
        self.run_from_here_button = QPushButton("Run from here")
        self.run_from_here_button.clicked.connect(self._on_run_from_here_clicked)
        self.step_actions_layout.addWidget(self.run_from_here_button)
```

Добавить методы (рядом с `_on_test_clicked`):

```python
    def _on_run_from_here_clicked(self) -> None:
        if self._current_index is None or self._hwnd is None:
            return
        rule = self.controller.draft_from(self._current_index)
        self._set_controls_enabled(False)
        self._playback_controller.finished.connect(self._on_run_from_here_finished)
        self._playback_controller.run_async(rule, self._hwnd)

    def _on_run_from_here_finished(self, context) -> None:
        self._playback_controller.finished.disconnect(self._on_run_from_here_finished)
        self._set_controls_enabled(True)
        self.status_label.setText(f"Run from here: {context.state.value}")
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v`
Expected: все PASS

- [ ] **Step 5: Прогнать полный набор тестов**

Run: `uv run pytest tests/unit/ -v`
Expected: все PASS, без skip кроме уже существующих Windows-only смоук-тестов

- [ ] **Step 6: Создать ручной чек-лист**

Создать `docs/manual-testing/mvp2-rule-editor-wave2-checklist.md`:

```markdown
# MVP2 / Rule Editor (волна 2) — ручная валидация на Windows

Выполняется на реальной Windows-машине, после того как автотесты
(`uv run pytest -q`) проходят. Автотесты (см.
`docs/specs/2026-08-19-mvp2-rule-editor-wave2-design.md`, раздел 4)
покрывают всю логику через qtbot + fake-реализации — здесь проверяется
только то, что принципиально требует реального Win32/живой игры.

1. Открыть Edit на Rule с несколькими шагами, у которых есть template —
   в панели справа видны превью скриншота и template, картинки выглядят
   осмысленно (не искажены, не пустые).
2. Нажать Recapture у шага — окно игры реально разворачивается на передний
   план (SetForegroundWindow), появляется статус "Click on the game window
   now…". Кликнуть по игре в новом месте — статус меняется на
   "Template recaptured.", превью справа обновляется на новую картинку.
   Убедиться, что реального клика/действия в самой игре recapture НЕ
   выполняет (только фиксирует точку).
3. Во время ожидания клика (после Recapture) нажать Esc — статус
   "Recapture cancelled.", template шага не меняется.
4. Нажать Test у шага с template — статус показывает Match found с
   confidence и координатами, если элемент реально виден на экране, или
   No match found, если элемента нет. Клик по игре при этом не происходит.
5. Нажать Run from here на среднем шаге Rule с 3+ шагами — воспроизводятся
   только шаги начиная с выбранного и до конца, более ранние шаги не
   выполняются. F9 во время выполнения прерывает run-from-step так же, как
   обычный Play.

Отметить каждый пункт как пройденный/непройденный с комментарием.
```

- [ ] **Step 7: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py \
        tests/unit/test_rule_editor_dialog.py \
        docs/manual-testing/mvp2-rule-editor-wave2-checklist.md
git commit -m "feat: add Run-from-step to Rule Editor, add wave2 manual checklist"
```
