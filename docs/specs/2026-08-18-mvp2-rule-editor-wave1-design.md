# MVP2 / Rule Editor, волна 1 — дизайн-спецификация

Дата: 2026-08-18

Родительский документ: `docs/specs/2026-08-17-tiles-survive-automation-design.md`,
раздел 8, MVP 2.

## 1. Цель

MVP2 по родительской спеке — это Rule Editor + `WaitForImage`/`WaitImageDisappear`
+ Debug Mode. Каждый из них проектируется и реализуется отдельным циклом.
Этот документ покрывает только первую волну Rule Editor: **структурные
правки уже существующих шагов Rule** — reorder, delete, delay, enable/disable,
rename, confidence threshold, strategy. Всё это — чистые правки полей, уже
присутствующих в модели `RuleStep` (`rules/models.py`); ни схема БД, ни
`RuleRepository` не меняются.

Вне рамок этого документа (вторая волна, отдельный цикл): preview
screenshot/template, смена template через recapture, test step, run-from-step,
добавление новых шагов (в родительской спеке не упоминается и не входит ни
в одну из волн).

## 2. Архитектура

Новый диалог `ui/dialogs/rule_editor_dialog.py` (`QDialog`) + новый контроллер
`ui/controllers/rule_editor_controller.py`. Соблюдается существующее правило
зависимостей (раздел 4 родительской спеки): контроллер не импортирует
PySide6, диалог — тонкий Qt-слой поверх контроллера, как
`ScheduleController`/`PlaybackController` в MVP1.

`RuleEditorController` при создании получает исходный `Rule` (из
`rule_repository.get(rule_id)`) и `rule_repository`, делает **глубокую копию**
(`copy.deepcopy`) в `self._draft: Rule` и работает только с ней до `save()`.

API контроллера:

```python
class RuleEditorController:
    def __init__(self, rule: Rule, rule_repository: RuleRepository) -> None: ...

    @property
    def draft(self) -> Rule: ...          # текущее состояние черновика

    def move_up(self, index: int) -> None: ...
    def move_down(self, index: int) -> None: ...
    def delete_step(self, index: int) -> None: ...
    def update_step(self, index: int, **fields) -> None: ...  # name, enabled,
                                                                 # delay_after_ms,
                                                                 # confidence_threshold,
                                                                 # strategy

    def save(self) -> Rule: ...           # rule_repository.save(draft) один раз
```

- `move_up`/`move_down` на границах списка (первый/последний индекс) — no-op,
  не бросают исключение.
- `delete_step` удаляет элемент из `draft.steps`; допускается опустошить
  список до нуля шагов — контроллер это не запрещает (playback пустого Rule —
  забота `PlaybackEngine`, не редактора).
- После любой из этих операций `order_index` всех оставшихся шагов
  пересчитывается по позиции в списке (0..N-1), чтобы порядок оставался
  консистентным независимо от того, сколько раз двигали/удаляли шаги до
  `save()`.
- `update_step` применяет `dataclasses.replace` к шагу по индексу, заменяя
  только переданные поля.
- `save()` вызывает `rule_repository.save(self._draft)` ровно один раз и
  возвращает то, что вернул repository (с проставленными id, как это уже
  делает `save()` для существующих Rule).

Диалог **не вызывает** `save()` сам по себе на каждое действие — только по
кнопке Save. Cancel закрывает диалог без обращения к `rule_repository`.

## 3. UI

В `MainWindow._build_ui()` рядом с существующими Rename/Delete (main_window.py:97-104)
добавляется кнопка **Edit**, включённая при выбранном Rule (по аналогии с
`_selected_rule()`). По клику создаётся `RuleEditorController` и открывается
`RuleEditorDialog` модально (`exec()`).

Диалог — `QDialog` с горизонтальным сплитом:

- Слева — `QListWidget` шагов черновика: одна строка на шаг,
  `"{order_index}: {step_type} — {name}"`, выключенные шаги отображаются
  серым текстом (`QListWidgetItem.setForeground`). Под списком — три кнопки:
  Up, Down, Delete, каждая работает над текущим выделенным индексом и сразу
  перерисовывает список (`refresh()` перечитывает `controller.draft.steps`).
- Справа — панель полей выбранного шага, обновляется при смене выделения:
  - `name` — `QLineEdit`
  - `enabled` — `QCheckBox`
  - `delay_after_ms` — `QSpinBox` (0..600000)
  - `confidence_threshold` — `QDoubleSpinBox` (0.0..1.0, шаг 0.01)
  - `strategy` — `QComboBox`, элементы — значения `StrategyType`
  - Правка любого поля сразу вызывает `controller.update_step(index, ...)`
    (черновик обновляется немедленно, в БД ничего не пишется).
- Внизу — Save/Cancel. Save вызывает `controller.save()`, закрывает диалог с
  `accept()`. Cancel — `reject()` без вызова контроллера.
- Если список шагов пуст (все удалены) — панель полей справа неактивна.

После закрытия диалога с `accept()` `MainWindow._refresh_rules()` вызывается
повторно (имя Rule не меняется этой волной, но паттерн уже есть у
Rename/Delete — держим единообразно).

## 4. Тестирование

Юнит-тесты на `RuleEditorController` (без Qt event loop, как
`test_schedule_controller.py`):

- `move_up`/`move_down` меняют порядок и пересчитывают `order_index`;
  no-op на границах.
- `delete_step` удаляет шаг и пересчитывает `order_index` оставшихся;
  корректно работает при удалении до пустого списка.
- `update_step` меняет только переданные поля, остальные не трогает.
- `save()` вызывает `rule_repository.save()` ровно один раз с финальным
  состоянием черновика; исходный Rule в repository не менялся до этого
  вызова (проверяется через fake/mock repository, как уже делается для
  `ScheduleController`).

Один smoke-тест в `test_main_window_smoke.py` (по образцу существующих
Rename/Delete-тестов): открыть Edit на Rule с несколькими шагами без
реального `exec()` диалога (тестируем контроллер, вызванный из обработчика
кнопки, а не модальный цикл Qt) — поменять поле, вызвать `save()`,
убедиться что `rule_repository.get()` вернул обновлённые данные.

## 5. Вне рамок волны 1

Явно отложено на отдельный цикл spec → plan → implementation:
preview screenshot/template, смена template (recapture), test step,
run-from-step, а также `WaitForImage`/`WaitImageDisappear` и Debug Mode
(отдельные куски MVP2 по родительской спеке).
