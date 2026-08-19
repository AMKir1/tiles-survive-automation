# MVP2 / Rule Editor, волна 2 — дизайн-спецификация

Дата: 2026-08-19

Родительские документы: `docs/specs/2026-08-17-tiles-survive-automation-design.md`,
раздел 8 (MVP 2), и `docs/specs/2026-08-18-mvp2-rule-editor-wave1-design.md`
(волна 1 — структурные правки шагов, уже реализована и провалидирована на
Windows).

## 1. Цель

Волна 2 закрывает оставшуюся часть Rule Editor из родительской спеки:
**preview screenshot/template, смена template через recapture, test step,
run-from-step**. Вне рамок — `WaitForImage`/`WaitImageDisappear` и Debug Mode
(отдельные куски MVP2), а также добавление новых шагов в Rule (в родительской
спеке не упоминается).

## 2. Архитектура и связи с существующим кодом

Все четыре фичи живут внутри уже существующих `RuleEditorDialog` +
`RuleEditorController`, но требуют протянуть в диалог зависимости, которых
там сейчас нет: `window_manager`, `screen_capture`, `input_recorder`,
`templates_dir`, `screenshots_dir`, текущий `hwnd` выбранного окна игры, и —
важно — **тот же экземпляр `PlaybackEngine`/`PlaybackController`, что
использует `MainWindow` для Play/Schedule**, а не новый.

Причина не создавать отдельный движок: `EmergencyStop` (F9) в
`MainWindow.__init__` подключён колбэком к конкретному
`PlaybackController.abort()`, заданному один раз при старте приложения. Если
у диалога будет свой `PlaybackController`, F9 не будет прерывать
run-from-step. Поскольку `RuleEditorDialog` открывается модально (`exec()`),
пока он открыт, кнопка Play в `MainWindow` недоступна — конкурентного
использования общего движка не возникает. Побочный эффект: сигнал `finished`
дойдёт и до обработчика `MainWindow`, поэтому строка о завершении
run-from-step появится и в главном логе — это осознанный выбор (лог честно
отражает произошедшее), не баг.

`MainWindow._on_edit_clicked` передаёт эти зависимости в конструктор
`RuleEditorDialog` вместе с уже существующими `rule`/`rule_repository`.

Новый чистый (без PySide6) модуль `recorder/template_capture.py` с функцией

```python
def capture_template(frame, client_x: int, client_y: int,
                      half_size: int = 30):
    ...  # возвращает вырезанный np.ndarray-фрагмент вокруг точки клика
```

Логика — та, что сейчас инлайн в `RecordingSession._capture_click`
(`recorder/recording_session.py:110-119`, `TEMPLATE_HALF_SIZE`). Она
выносится и переиспользуется и записью, и recapture-путём волны 2, чтобы не
дублировать crop-математику.

`RuleEditorController` получает новый метод:

```python
def draft_from(self, index: int) -> Rule:
    """Копия черновика, где steps — это draft.steps[index:]."""
```

Чистый Python, без побочных эффектов — юнит-тестируется отдельно от Qt.

## 3. UI и поведение

### 3.1 Preview (screenshot + template)

Под существующей панелью полей — два `QLabel` с `QPixmap`: слева полный
`step.screenshot_path`, справа — `step.template_path`, оба через
`setScaledContents`/`Qt.KeepAspectRatio` под размер панели. Обновляются в
`_on_step_selected`, как остальные поля. Если путь `None` (нет файла у шага
— например `Wait`/`KeyPress`/`Hotkey`, либо шаг ещё не проходил recapture) —
`QLabel` показывает текст `"No image"` вместо `QPixmap`. Чистый UI, новой
бизнес-логики нет.

### 3.2 Recapture template

Кнопка "Recapture" у выбранного шага. По клику:

1. Весь `field_panel` дизейблится, статусная строка вида "Click on the game
   window now… (Esc to cancel)".
2. `window_manager.activate(hwnd)`, затем `input_recorder.start(on_event=...)`.
3. `input_recorder` зовёт колбэк из не-Qt потока (как и при обычной записи) —
   наружу на Qt-поток маршалим через `QTimer.singleShot(0, ...)`, тот же
   паттерн, что уже используется в `PlaybackController._poll`.
4. Первый `mouse_down` с координатами внутри client rect игры (тот же фильтр,
   что в `RecordingSession._on_event` — событие вне client rect игнорируется,
   ожидание продолжается): `screen_capture.grab(client_rect)` +
   `capture_template(frame, client_x, client_y)`. Пишем оба PNG (полный
   скриншот и вырезанный template) в `screenshots_dir`/`templates_dir` под
   новым recapture-session-id (та же `uuid.uuid4().hex[:8]`-схема, что и у
   записи, чтобы не коллизировать с существующими файлами).
5. `controller.update_step(index, template_path=..., screenshot_path=...)`,
   `input_recorder.stop()`, панель возвращается в обычный режим, preview
   обновляется.

Esc во время ожидания или закрытие диалога — `input_recorder.stop()` без
изменений в draft.

Реального клика по игре recapture не выполняет — только фиксирует точку и
делает снимок, как и обсуждалось (это "живая перезапись координаты", не
воспроизведение).

Файлы пишутся на диск сразу в момент клика, а не при `Save` диалога. Если
после recapture пользователь нажимает Cancel — новый PNG на диске остаётся
неиспользуемым. Осознанно принятое ограничение, тот же паттерн, что уже
задокументирован для волны 1 (осиротевшие файлы шагов при пересохранении/
удалении) — отдельный staging-механизм ради этого не строим (YAGNI).

### 3.3 Test step (dry-run)

Кнопка "Test" у выбранного шага. Активна только если у шага есть
`template_path` и `strategy != RELATIVE_ONLY` — иначе dimmed.

По клику — синхронно, без потока (единичный grab+match быстрый,
UI не блокируется заметно): `screen_capture.grab(client_rect)` +
`TemplateMatcher.find(frame, template, step.confidence_threshold)`.
Результат — в статусную строку: `"Match found: confidence=0.94 at (x, y)"`
либо `"No match found"`. Клик по игре не выполняется.

### 3.4 Run-from-step

Кнопка "Run from here" у выбранного шага. По клику:

1. Проверка `hwnd is not None` (та же проверка, что уже есть в `MainWindow`
   перед обычным Play — переиспользуется, а не дублируется).
2. `rule = controller.draft_from(current_index)`.
3. Все кнопки диалога (Recapture/Test/Run from here/Save/Cancel/Up/Down/
   Delete) дизейблятся на время выполнения — тот же реэнтрантность-guard,
   что уже есть в `MainWindow` для Play/Schedule.
4. `playback_controller.run_async(rule, hwnd)` — общий (не новый) экземпляр,
   см. раздел 2.
5. По сигналу `finished` — кнопки диалога снова включаются.

Выключенные (`enabled=False`) шаги в `draft_from(index)` естественным образом
пропускаются самим `PlaybackEngine.run()` (уже фильтрует `if s.enabled`),
дополнительной логики не нужно.

## 4. Тестирование

Юнит-тесты (без Qt, без Win32):

- `capture_template(frame, client_x, client_y, half_size)` —
  `recorder/template_capture.py`, на синтетических изображениях (границы
  кадра, точка у самого края). Дополнительно: `RecordingSession` переводится
  на вызов этой функции вместо инлайн-кода — существующие тесты
  `RecordingSession` должны продолжать проходить без изменений (чистый
  рефакторинг, не поведенческое изменение).
- `RuleEditorController.draft_from(index)` — индекс 0, последний индекс,
  индекс за пределами (граница), пустой список шагов; проверка, что исходный
  `draft.steps` не мутируется вызовом.

**Уточнение относительно волны 1:** в проекте уже используется `pytest-qt`
(`qtbot`) для тестирования `RuleEditorDialog` напрямую, с фейковыми
`window_manager`/`screen_capture`/`input_recorder`, без реального модального
`exec()` (см. `tests/unit/test_main_window_smoke.py:270-359` —
`test_changing_strategy_combo_survives_real_save`,
`test_editing_name_refreshes_step_list_row_without_reorder` и т.д., уже
существуют для волны 1). Формулировка "Qt-виджеты не покрыты автотестами" в
дизайне волны 1 была осторожнее, чем позволяет инфраструктура проекта.
Поэтому для волны 2 автотестами через `qtbot` + fake-реализации покрывается
всё, что не требует реального Win32/живой игры:

- Preview: выбор шага с/без `template_path`/`screenshot_path` — виден
  `QPixmap` либо текст `"No image"`.
- Recapture: клик по кнопке переводит диалог в режим ожидания; фейковый
  `input_recorder` эмитит `mouse_down` внутри client rect — `draft` шага
  получает новые `template_path`/`screenshot_path`, файлы появляются в
  `tmp_path`; событие вне client rect игнорируется; Esc отменяет ожидание
  без изменений в `draft`.
- Test step: `FakeScreenCapture` с известным кадром + синтетический
  template — статус показывает `"Match found: confidence=... at (...)"`;
  кадр без совпадения — `"No match found"`; кнопка dimmed для шага без
  `template_path` или со strategy `RELATIVE_ONLY`.
- Run-from-step: `playback_controller` (с `FakeInputController`) реально
  выполняет только `draft.steps[index:]`; кнопки диалога дизейблятся на
  время выполнения и включаются обратно по `finished`
  (`qtbot.waitSignal`, тот же паттерн, что уже используется в
  `test_main_window_smoke.py` для Play/Schedule).

Ручной Windows-чек-лист (`docs/manual-testing/mvp2-rule-editor-wave2-checklist.md`,
создаётся вместе с implementation plan) сокращается до того, что автотесты
принципиально не могут проверить: активация окна живой игры перед
recapture, реальный Win32-клик мышью по игре как источник координаты,
визуальная адекватность превью на настоящих скриншотах.

## 5. Вне рамок волны 2

Явно отложено на отдельные циклы: `WaitForImage`/`WaitImageDisappear`,
Debug Mode (обе — отдельные куски MVP2 по родительской спеке), добавление
новых шагов в Rule.
