# MVP2 / Rule Editor, волна 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Диалог редактирования Rule (`RuleEditorDialog`) со списком шагов, позволяющий переставлять (Up/Down), удалять шаги и править на выбранном шаге name/enabled/delay_after_ms/confidence_threshold/strategy, с явным Save/Cancel — без изменения схемы БД и без изменения `RuleRepository`.

**Architecture:** `RuleEditorController` — чистый Python (без PySide6), держит `Rule`-черновик (`copy.deepcopy` исходного `Rule`) и выполняет над ним синхронные in-memory операции; ничего не пишет в БД до явного `save()`. `RuleEditorDialog` — тонкий Qt-слой поверх контроллера: список шагов слева, панель полей выбранного шага справа, Save/Cancel снизу. `MainWindow` получает кнопку Edit рядом с Rename/Delete.

**Tech Stack:** Python 3.12+, PySide6, pytest, pytest-qt (уже в проекте).

**Spec:** `docs/specs/2026-08-18-mvp2-rule-editor-wave1-design.md`

## Global Constraints

- Ни `rules/models.py`, ни `storage/rule_repository.py` не меняются — все нужные поля у `RuleStep` уже есть.
- `RuleEditorController` не импортирует PySide6.
- Черновик — `copy.deepcopy` исходного `Rule`; ни одна операция контроллера (`move_up`/`move_down`/`delete_step`/`update_step`) не обращается к `rule_repository` — только `save()` делает это, и делает ровно один раз.
- После `move_up`/`move_down`/`delete_step` `order_index` всех оставшихся шагов пересчитывается по позиции в списке (0..N-1).
- `move_up`/`move_down` на границах списка (первый/последний индекс) — no-op, без исключений.
- Тесты `MainWindow`-уровня используют реальный `RuleRepository(connect(":memory:"))`, как уже принято в `test_main_window_smoke.py` (не моки БД). Тесты контроллера используют лёгкий fake-repository (записывает вызовы `save()`), чтобы точно проверить количество и момент записи.
- Вне рамок этой волны — не трогать: preview screenshot/template, смена template, test step, run-from-step, `WaitForImage`/`WaitImageDisappear`, Debug Mode, добавление новых шагов.

---

## Файловая карта

```
src/tiles_survive_automation/
  ui/
    controllers/
      rule_editor_controller.py     # новый
    dialogs/
      __init__.py                   # новый, пустой
      rule_editor_dialog.py         # новый
    main_window.py                  # изменяется: кнопка Edit + _on_edit_clicked
tests/
  unit/
    test_rule_editor_controller.py  # новый
    test_main_window_smoke.py       # изменяется: тесты кнопки Edit
docs/
  manual-testing/
    mvp2-rule-editor-wave1-checklist.md   # новый
```

---

### Task 1: `RuleEditorController`

**Files:**
- Create: `src/tiles_survive_automation/ui/controllers/rule_editor_controller.py`
- Test: `tests/unit/test_rule_editor_controller.py`

**Interfaces:**
- Consumes: `tiles_survive_automation.rules.models.{Rule, RuleStep, StepType, StrategyType}`; `tiles_survive_automation.storage.rule_repository.RuleRepository` (только контракт `save(rule: Rule) -> Rule`, в тестах подменяется fake-объектом с тем же методом).
- Produces: `RuleEditorController(rule: Rule, rule_repository) -> RuleEditorController` с:
  - `.draft -> Rule` (property, текущее состояние черновика)
  - `.move_up(index: int) -> None`
  - `.move_down(index: int) -> None`
  - `.delete_step(index: int) -> None`
  - `.update_step(index: int, **fields) -> None`
  - `.save() -> Rule`

- [ ] **Step 1: Написать тест**

```python
# tests/unit/test_rule_editor_controller.py
from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType
from tiles_survive_automation.ui.controllers.rule_editor_controller import (
    RuleEditorController,
)


class FakeRuleRepository:
    def __init__(self) -> None:
        self.save_calls: list[Rule] = []

    def save(self, rule: Rule) -> Rule:
        self.save_calls.append(rule)
        return rule


def _step(step_id: int, order_index: int, name: str) -> RuleStep:
    return RuleStep(
        id=step_id, order_index=order_index, step_type=StepType.CLICK_IMAGE,
        name=name, enabled=True, params={"relative_x": 0.5, "relative_y": 0.5},
        template_path=None, confidence_threshold=0.9,
        strategy=StrategyType.RELATIVE_ONLY, verification=None,
        screenshot_path=None, delay_after_ms=0,
    )


def _rule() -> Rule:
    return Rule(
        id=1, name="R", description=None, window_title_hint=None,
        steps=[_step(1, 0, "A"), _step(2, 1, "B"), _step(3, 2, "C")],
    )


def test_move_up_swaps_with_previous_and_reindexes():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_up(1)  # B (index 1) <-> A (index 0)

    assert [s.name for s in controller.draft.steps] == ["B", "A", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1, 2]


def test_move_up_at_first_index_is_a_noop():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_up(0)

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C"]


def test_move_down_swaps_with_next_and_reindexes():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_down(0)  # A (index 0) <-> B (index 1)

    assert [s.name for s in controller.draft.steps] == ["B", "A", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1, 2]


def test_move_down_at_last_index_is_a_noop():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.move_down(2)

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C"]


def test_delete_step_removes_and_reindexes_remaining():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.delete_step(1)  # remove B

    assert [s.name for s in controller.draft.steps] == ["A", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1]


def test_delete_all_steps_leaves_empty_list():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.delete_step(0)
    controller.delete_step(0)
    controller.delete_step(0)

    assert controller.draft.steps == []


def test_update_step_replaces_only_given_fields():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.update_step(1, name="Renamed", enabled=False, delay_after_ms=500,
                            confidence_threshold=0.75, strategy=StrategyType.VISUAL_ONLY)

    step = controller.draft.steps[1]
    assert step.name == "Renamed"
    assert step.enabled is False
    assert step.delay_after_ms == 500
    assert step.confidence_threshold == 0.75
    assert step.strategy == StrategyType.VISUAL_ONLY
    assert step.id == 2
    assert step.order_index == 1
    assert step.step_type == StepType.CLICK_IMAGE


def test_no_repository_write_happens_before_save():
    repository = FakeRuleRepository()
    controller = RuleEditorController(_rule(), repository)

    controller.update_step(0, name="Changed")
    controller.delete_step(2)
    controller.move_down(0)

    assert repository.save_calls == []


def test_save_calls_repository_exactly_once_with_final_draft():
    repository = FakeRuleRepository()
    controller = RuleEditorController(_rule(), repository)

    controller.update_step(1, name="Renamed")

    controller.save()

    assert len(repository.save_calls) == 1
    saved = repository.save_calls[0]
    assert [s.name for s in saved.steps] == ["A", "Renamed", "C"]


def test_original_rule_object_passed_in_is_not_mutated():
    original = _rule()
    controller = RuleEditorController(original, FakeRuleRepository())

    controller.update_step(0, name="Changed")
    controller.delete_step(2)

    assert [s.name for s in original.steps] == ["A", "B", "C"]
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tiles_survive_automation.ui.controllers.rule_editor_controller'`.

- [ ] **Step 3: Реализовать `ui/controllers/rule_editor_controller.py`**

```python
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from tiles_survive_automation.rules.models import Rule


class RuleEditorController:
    def __init__(self, rule: Rule, rule_repository) -> None:
        self._draft = deepcopy(rule)
        self._rule_repository = rule_repository

    @property
    def draft(self) -> Rule:
        return self._draft

    def move_up(self, index: int) -> None:
        if index <= 0 or index >= len(self._draft.steps):
            return
        self._swap(index, index - 1)

    def move_down(self, index: int) -> None:
        if index < 0 or index >= len(self._draft.steps) - 1:
            return
        self._swap(index, index + 1)

    def delete_step(self, index: int) -> None:
        if index < 0 or index >= len(self._draft.steps):
            return
        del self._draft.steps[index]
        self._reindex()

    def update_step(self, index: int, **fields) -> None:
        step = self._draft.steps[index]
        self._draft.steps[index] = replace(step, **fields)

    def save(self) -> Rule:
        self._draft = self._rule_repository.save(self._draft)
        return self._draft

    def _swap(self, i: int, j: int) -> None:
        steps = self._draft.steps
        steps[i], steps[j] = steps[j], steps[i]
        self._reindex()

    def _reindex(self) -> None:
        for i, step in enumerate(self._draft.steps):
            self._draft.steps[i] = replace(step, order_index=i)
```

- [ ] **Step 4: Запустить тесты**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v`
Expected: PASS (9 passed).

---

### Task 2: `RuleEditorDialog` + кнопка Edit в `MainWindow`

**Files:**
- Create: `src/tiles_survive_automation/ui/dialogs/__init__.py`
- Create: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `src/tiles_survive_automation/ui/main_window.py`
- Test: `tests/unit/test_main_window_smoke.py`

**Interfaces:**
- Consumes: `RuleEditorController` (Task 1); `tiles_survive_automation.rules.models.StrategyType`; существующие `MainWindow._selected_rule()` (main_window.py:130-134), `MainWindow._refresh_rules()` (main_window.py:122-125), `self._rule_repository`.
- Produces: `RuleEditorDialog(rule: Rule, rule_repository, parent=None) -> RuleEditorDialog` (QDialog) с публичным атрибутом `.controller: RuleEditorController` (нужен тестам для monkeypatch `exec`); `MainWindow._edit_button`, `MainWindow._on_edit_clicked() -> None`.

- [ ] **Step 1: Написать тест**

Добавить в конец `tests/unit/test_main_window_smoke.py`:

```python
def test_edit_button_saves_changes_made_in_the_dialog(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog

    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)
    window.rule_list.setCurrentRow(0)

    def fake_exec(self):
        self.controller.update_step(0, name="Renamed", enabled=False)
        self.controller.save()
        return QDialog.Accepted

    monkeypatch.setattr(RuleEditorDialog, "exec", fake_exec)

    window._on_edit_clicked()

    saved = rule_repository.list_all()[0]
    assert saved.steps[0].name == "Renamed"
    assert saved.steps[0].enabled is False


def test_edit_button_cancelled_leaves_rule_unchanged(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog

    rule_repository = RuleRepository(connect(":memory:"))
    rule_repository.save(_make_rule("R"))
    window, rule_repository = _make_window(qtbot, tmp_path, rule_repository=rule_repository)
    window.rule_list.setCurrentRow(0)

    def fake_exec(self):
        self.controller.update_step(0, name="Should not persist")
        return QDialog.Rejected

    monkeypatch.setattr(RuleEditorDialog, "exec", fake_exec)

    window._on_edit_clicked()

    saved = rule_repository.list_all()[0]
    assert saved.steps[0].name == "Click"
```

Эти тесты подменяют `RuleEditorDialog.exec` (как уже подменяются `QInputDialog.getText`/`QMessageBox.question` в этом файле) — модальный цикл Qt не запускается, проверяется только контракт «Save зовёт controller.save() ровно один раз, Cancel — не зовёт вовсе», уже покрытый юнит-тестами Task 1 на уровне контроллера. Виджеты самого диалога (список шагов, панель полей, Up/Down/Delete) автотестами в этой волне не покрываются — это часть ручной Windows-проверки в Task 3.

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `uv run pytest tests/unit/test_main_window_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tiles_survive_automation.ui.dialogs'` (и `AttributeError: 'MainWindow' object has no attribute '_on_edit_clicked'`).

- [ ] **Step 3: Создать `ui/dialogs/__init__.py`**

Пустой файл.

- [ ] **Step 4: Реализовать `ui/dialogs/rule_editor_dialog.py`**

```python
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
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


class RuleEditorDialog(QDialog):
    def __init__(self, rule, rule_repository, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Rule — {rule.name}")
        self.controller = RuleEditorController(rule, rule_repository)
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
        self.strategy_combo.currentIndexChanged.connect(
            lambda index: self._on_field_changed(
                "strategy", self.strategy_combo.itemData(index)))

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Enabled", self.enabled_check)
        form.addRow("Delay after (ms)", self.delay_spin)
        form.addRow("Confidence threshold", self.confidence_spin)
        form.addRow("Strategy", self.strategy_combo)

        self.field_panel = QWidget()
        self.field_panel.setLayout(form)
        self.field_panel.setEnabled(False)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save_clicked)
        buttons.rejected.connect(self.reject)

        split = QHBoxLayout()
        split.addWidget(left_widget)
        split.addWidget(self.field_panel)

        outer = QVBoxLayout()
        outer.addLayout(split)
        outer.addWidget(buttons)
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

    def _on_field_changed(self, field: str, value) -> None:
        if self._current_index is None:
            return
        self.controller.update_step(self._current_index, **{field: value})

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

- [ ] **Step 5: Подключить кнопку Edit в `main_window.py`**

Заменить блок импорта из `PySide6.QtWidgets` (main_window.py:1-12):

```python
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
```

на:

```python
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
```

Добавить импорт рядом с остальными импортами `ui.controllers.*` (main_window.py:20-28):

```python
from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog
```

В `_build_ui()` — рядом с `rename_button`/`delete_button` (main_window.py:97-104), заменить:

```python
        rename_button = QPushButton("Rename")
        delete_button = QPushButton("Delete")
        rename_button.clicked.connect(self._on_rename_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)

        rule_buttons = QHBoxLayout()
        rule_buttons.addWidget(rename_button)
        rule_buttons.addWidget(delete_button)
```

на:

```python
        rename_button = QPushButton("Rename")
        delete_button = QPushButton("Delete")
        self._edit_button = QPushButton("Edit")
        rename_button.clicked.connect(self._on_rename_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)

        rule_buttons = QHBoxLayout()
        rule_buttons.addWidget(rename_button)
        rule_buttons.addWidget(delete_button)
        rule_buttons.addWidget(self._edit_button)
```

Добавить метод рядом с `_on_delete_clicked` (main_window.py:226-237):

```python
    def _on_edit_clicked(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        dialog = RuleEditorDialog(rule, self._rule_repository, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh_rules()
```

- [ ] **Step 6: Запустить тесты**

Run: `uv run pytest tests/unit/test_main_window_smoke.py -v`
Expected: PASS (все тесты файла, включая два новых).

- [ ] **Step 7: Прогнать весь набор тестов**

Run: `uv run pytest -q`
Expected: PASS (существующие 108 + 9 новых контроллерных + 2 новых smoke = 119 passed, 2 skipped).

---

### Task 3: Чек-лист ручной валидации на Windows

**Files:**
- Create: `docs/manual-testing/mvp2-rule-editor-wave1-checklist.md`

**Interfaces:** нет (документ, не код).

- [ ] **Step 1: Написать чек-лист**

```markdown
# MVP2 / Rule Editor (волна 1) — ручная валидация на Windows

Выполняется на реальной Windows-машине, после того как автотесты
(`uv run pytest -q`) проходят. Список шагов Rule Editor не покрыт
автотестами (см. `docs/plans/2026-08-18-mvp2-rule-editor-wave1.md`,
Task 2) — это единственная проверка самих Qt-виджетов диалога.

1. Записать Rule с 3+ шагами (см. пункт 3 чек-листа MVP1), нажать Edit —
   должно открыться модальное окно со списком всех шагов в правильном
   порядке.
2. Выбрать шаг — панель справа должна показать его текущие name/enabled/
   delay/confidence/strategy.
3. Поменять name и strategy у выбранного шага, выбрать другой шаг и
   вернуться обратно — правки должны сохраниться в черновике (проверка,
   что переключение выделения не откатывает несохранённые правки).
4. Переставить шаг кнопками Up/Down в начало и в конец списка — порядок в
   списке должен визуально соответствовать перестановке; на первом/
   последнем шаге кнопки не должны падать с ошибкой.
5. Удалить шаг — он должен пропасть из списка, у оставшихся шагов
   отображаемый порядковый номер должен сдвинуться.
6. Снять чекбокс Enabled у шага — строка в списке должна отобразиться
   отличным цветом (серым).
7. Нажать Save — диалог должен закрыться, Play на этом Rule должен
   выполнить именно изменённую (переставленную/отредактированную)
   последовательность шагов.
8. Открыть Edit повторно, внести правку, нажать Cancel — Rule должен
   остаться в точности таким, каким был до открытия диалога (перепроверить
   через повторный Play или повторное открытие Edit).

Отметить каждый пункт как пройденный/непройденный с комментарием.
```
