# Tiles Survive Automation — дизайн-спецификация

Дата: 2026-08-17

## 1. Цель

Windows desktop-приложение для записи, редактирования и воспроизведения
пользовательских действий в игре Tiles Survive (официальный Windows-клиент).
Пользователь записывает последовательность действий как **Rule**, редактирует
её, объединяет несколько Rule в **Scenario** и запускает Rule/Scenario
повторно. Работа только через экран (screenshot + OpenCV template matching)
и обычный пользовательский ввод (SendInput/pynput) — без чтения памяти
процесса, DLL injection, перехвата трафика и обхода античита.

## 2. Платформа разработки vs платформа выполнения

Приложение целиком Windows-specific в рантайме (pywin32, SendInput/HWND),
но разрабатывается на macOS. Чтобы это не блокировало разработку:

- Всё, что трогает Win32 API, скрыто за портами (Protocol/ABC) в модулях
  `window`, `capture`, `input`.
- Каждый порт имеет `win32_*` реализацию (реальная, работает только на
  Windows) и `fake_*` реализацию (для unit-тестов и разработки на Mac —
  эмулирует окно/скриншоты/ввод без обращения к ОС).
- Фабрика (`factory.py` в каждом модуле) выбирает реализацию по
  `platform.system() == "Windows"`, либо реализация передаётся явно через DI
  в тестах.
- `pyproject.toml` помечает Windows-only зависимости (`pywin32`,
  `pydirectinput`) через `environment markers` (`sys_platform == 'win32'`),
  чтобы `uv sync` не падал на macOS.
- Реальная валидация Win32-специфики (DPI, foreground lock, тайминги
  SendInput) возможна только на Windows-машине — это отдельный шаг проверки
  на каждом этапе (см. раздел 8), не подменяется unit-тестами на fake.

## 3. Технологии

- Python 3.12+, менеджер зависимостей и venv — **uv**.
- PySide6 — GUI.
- OpenCV (`opencv-python`) — template matching.
- MSS — screenshot клиентской области окна (Windows realtime capture).
- pywin32 — HWND, client area, activate/foreground, DPI awareness (только
  Windows).
- pynput — запись mouse/keyboard событий и глобальный F9-хук.
- SendInput через pywin32 (`win32api.SendInput`), обёрнутый в свой
  `InputController` — вместо стороннего pydirectinput, чтобы не тащить лишнюю
  зависимость под тонкий враппер вокруг того же самого API; если понадобится
  — можно подключить `pydirectinput` как альтернативную реализацию порта.
- SQLite (`sqlite3` из stdlib) — правила, шаги, сценарии, история выполнения.
  Без ORM: DAO/repository классы поверх сырого SQL, схема и миграции в
  `storage/schema.sql` + `storage/migrations/`.

## 4. Архитектура: модули и зависимости

```
tiles-survive-automation/
  pyproject.toml
  data/
    database.db
    templates/<rule_id>/<step_id>.png
    screenshots/
    logs/
  docs/specs/
  src/tiles_survive_automation/
    app.py            # entry point, сборка зависимостей (DI без фреймворка)
    config.py          # пути к data/, EMERGENCY_STOP_KEY='f9', дефолтный confidence
    window/              # WindowManager: port + win32_impl + fake_impl + factory
    capture/              # ScreenCapture: port + mss_impl + fake_impl + factory
    input/                  # InputRecorder(pynput)/InputController(SendInput) порты + impl + emergency_stop.py
    recorder/                 # RecordingSession — очередь событий, БЕЗ импорта PySide6
    vision/                     # TemplateMatcher (OpenCV), MatchResult
    rules/                       # Rule, RuleStep, StepType — доменные модели + RuleBuilder
    scenarios/                    # Scenario, ScenarioRule — доменные модели
    playback/                      # PlaybackEngine (state machine), ScenarioRunner, strategies.py
    storage/                        # sqlite3 DAO, schema.sql, миграции, пути к ассетам
    app_logging/                     # структурные логи выполнения
    ui/                                # PySide6: MainWindow, RuleEditor, ScenarioEditor, DebugPanel,
                                        # controllers/ — мост «поток recorder/playback → Qt-сигналы»
  tests/
    unit/
    fakes/
```

Правило зависимостей: `ui` → `recorder`/`playback`/`rules`/`scenarios` →
`window`/`capture`/`input`/`vision`/`storage`. Нижние модули не знают о
верхних и не импортируют PySide6. `recorder` и `playback` — чистый Python,
запускаются в собственных `threading.Thread`; GUI получает обновления через
`queue.Queue`, который тонкий адаптер в `ui/controllers/` опрашивает через
`QTimer` и транслирует в Qt-сигналы.

## 5. Сущности и SQLite-схема

```sql
Rule(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  window_title_hint TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)

RuleStep(
  id INTEGER PRIMARY KEY,
  rule_id INTEGER NOT NULL REFERENCES Rule(id) ON DELETE CASCADE,
  order_index INTEGER NOT NULL,
  step_type TEXT NOT NULL,   -- Click|DoubleClick|RightClick|Drag|Scroll|KeyPress|Hotkey|Wait|WaitForImage|ClickImage|WaitImageDisappear
  name TEXT NOT NULL,        -- отображаемое имя, напр. "Click -> Alliance"
  enabled INTEGER NOT NULL DEFAULT 1,
  params_json TEXT NOT NULL, -- см. ниже, набор полей зависит от step_type
  template_path TEXT,        -- относительный путь под data/templates/, если применимо
  confidence_threshold REAL NOT NULL DEFAULT 0.85,
  strategy TEXT NOT NULL DEFAULT 'VISUAL_THEN_RELATIVE', -- VISUAL_THEN_RELATIVE|VISUAL_ONLY|RELATIVE_ONLY
  verification_json TEXT,    -- {type: WaitForImage|WaitImageDisappear, template_path, timeout_ms}
  screenshot_path TEXT,      -- полный скриншот окна на момент записи (для отладки)
  delay_after_ms INTEGER NOT NULL DEFAULT 0
)

Scenario(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)

ScenarioRule(
  id INTEGER PRIMARY KEY,
  scenario_id INTEGER NOT NULL REFERENCES Scenario(id) ON DELETE CASCADE,
  rule_id INTEGER NOT NULL REFERENCES Rule(id),
  order_index INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  delay_before_ms INTEGER NOT NULL DEFAULT 0
)

Execution(
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  target_type TEXT NOT NULL, -- RULE|SCENARIO
  target_id INTEGER NOT NULL,
  status TEXT NOT NULL,      -- RUNNING|SUCCESS|FAILED|STOPPED
  error_message TEXT
)

ExecutionStep(
  id INTEGER PRIMARY KEY,
  execution_id INTEGER NOT NULL REFERENCES Execution(id) ON DELETE CASCADE,
  rule_id INTEGER NOT NULL,
  rule_step_id INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  description TEXT NOT NULL,
  matched_template TEXT,
  confidence REAL,
  x INTEGER,
  y INTEGER,
  result TEXT NOT NULL,      -- SUCCESS|FAILED|SKIPPED
  error_message TEXT
)
```

`params_json` по типам (примеры полей):
- `Click/DoubleClick/RightClick/ClickImage`: `{relative_x, relative_y}`
- `Drag`: `{from_relative_x, from_relative_y, to_relative_x, to_relative_y, duration_ms}`
- `Scroll`: `{relative_x, relative_y, delta}`
- `KeyPress`: `{key}`
- `Hotkey`: `{keys: [modifier..., key]}`
- `Wait`: `{duration_ms}`
- `WaitForImage/WaitImageDisappear`: `{template_path, timeout_ms}` (может
  дублироваться с `verification_json`, если используется как самостоятельный
  шаг, а не как проверка после другого шага)

Картинки (`template_path`, `screenshot_path`) — только пути, файлы физически
в `data/templates/<rule_id>/<step_id>.png` и `data/screenshots/`. BLOB в
SQLite не используется.

## 6. Поток Record → Save → Play

1. **Record**: `MainWindow` вызывает `RecordingSession.start(window_handle)`.
   Сессия поднимает `InputRecorder` (pynput) в отдельном потоке, слушает
   события, фильтрует события внутри окна самого приложения-рекордера. На
   каждый значимый клик — `ScreenCapture.grab(client_area)` непосредственно
   до клика, вырезание области вокруг точки клика как template, сохранение
   PNG на диск, добавление `RawEvent(timestamp, kind, x, y, key, ...)` в
   очередь. `Pause` временно останавливает обработку событий, `Stop`
   завершает сессию и возвращает список `RawEvent`.
2. **Save**: `RuleBuilder` конвертирует `RawEvent[]` в `Rule` + `RuleStep[]`
   (клик → `ClickImage` с относительными координатами как fallback, пауза
   между событиями сверх небольшого порога → `Wait`), сохраняет шаблоны в
   `data/templates/<rule_id>/`, персистит через `rules.repository` (SQLite).
   Пользователь называет Rule перед сохранением.
3. **Play**: `PlaybackEngine.run(rule)` активирует окно через
   `WindowManager.activate()`, для каждого включённого `RuleStep` по очереди:
   Strategy 1 (visual — `vision.TemplateMatcher.find(screenshot, template,
   confidence_threshold)`) → при неудаче и `strategy != VISUAL_ONLY` Strategy 2
   (relative coords: `x = relative_x * window_width`) → при неудаче Strategy 3
   (остановка, screenshot, запись ошибки в `Execution`/`ExecutionStep`,
   показ проблемного step пользователю). После действия — опциональная
   `verification` (`WaitForImage`/`WaitImageDisappear` с таймаутом). Каждый
   шаг логируется в `app_logging` и в `ExecutionStep`.
4. **Emergency Stop**: глобальный low-level F9-хук (pynput
   `keyboard.GlobalHotKeys` или `Listener`, работает независимо от фокуса
   окна) живёт всё время работы приложения. При срабатывании —
   `InputController.release_all()` (отпускает все зажатые кнопки/клавиши,
   которые `PlaybackEngine` централизованно трекает как currently-held) и
   `PlaybackEngine.abort()`, немедленно прерывая текущий Rule/Scenario.

## 7. Технические риски и как архитектура их закрывает

1. **DPI scaling** — обязательный вызов per-monitor DPI awareness при старте
   (`SetProcessDpiAwarenessContext`) в `win32_window_manager`/`app.py`, иначе
   координаты клика и скриншота расходятся на масштабированных экранах.
2. **Изменение размера окна игры** — relative-координаты пересчитываются от
   client area на момент воспроизведения; при сильном ресайзе template
   matching может не найтись из-за масштаба. MVP1 допускает, что размер окна
   не меняется между записью и воспроизведением; Debug Mode должен явно
   показывать, если размер разошёлся.
3. **Foreground/активация окна** — перед каждым Rule обязательна
   `SetForegroundWindow` + проверка успеха; Windows foreground lock может
   блокировать активацию из чужого процесса — нужен fallback (повторная
   попытка / понятная ошибка пользователю), реализуется в
   `win32_window_manager.activate()`.
4. **Emergency Stop должен работать даже когда фокус в игре** — низкоуровневый
   хук, а не Qt shortcut (уже заложено в дизайне, раздел 6.4).
5. **Централизованное отслеживание «зажатого» состояния** — `PlaybackEngine`
   должен знать, какая кнопка/клавиша сейчас удерживается (для Drag/hold), чтобы
   F9 мог гарантированно её отпустить независимо от того, в какой момент
   стратегии произошла остановка.
6. **SQLite при параллельной записи логов и чтении UI** — WAL-режим,
   единственный поток-владелец записи в БД (все записи из playback/recorder
   идут через один writer, UI читает).
7. **Тестирование Win32-специфики недоступно на macOS** — закрывается портами
   и fake-реализациями для unit-тестов; реальная валидация (foreground lock,
   DPI, тайминги SendInput) возможна только на Windows-машине — отдельный
   ручной шаг проверки на каждом этапе, не подменяется автотестами на fake.

## 8. Поэтапный план реализации

- **Этап 0 — скелет проекта.** `pyproject.toml` (uv, platform markers),
  структура пакетов из раздела 4, `config.py`, инициализация SQLite-схемы
  (`storage/schema.sql` + `database.py`), базовое логирование
  (`app_logging`). Критерий готовности: `uv run python -m
  tiles_survive_automation.app` стартует пустое GUI-окно на macOS с
  fake-реализациями.

- **MVP 1 — рабочий цикл Record → Save → Play.**
  - `window`: `WindowManager` порт, `win32_window_manager` (список окон,
    HWND, client area, activate, resize/move-aware), `fake_window_manager`.
  - `capture`: `ScreenCapture` порт, `mss_capture`, `fake_capture`.
  - `input`: `InputRecorder` (pynput) — клики/drag/wheel/keyboard с
    таймстампами, фильтрация событий внутри своего окна; `InputController`
    (SendInput через pywin32) — click/drag/scroll/key/hotkey;
    `emergency_stop.py` — глобальный F9-хук + `release_all()`.
  - `recorder`: `RecordingSession` (Record/Pause/Stop), сохранение
    screenshot+template на каждый клик.
  - `vision`: `TemplateMatcher` (`cv2.matchTemplate` + confidence).
  - `rules`: модели `Rule`/`RuleStep`, `RuleBuilder` (события → Rule),
    `repository` (SQLite DAO).
  - `playback`: `PlaybackEngine` — Strategy 1 (visual) → Strategy 2
    (relative) → Strategy 3 (stop+screenshot+error), без verification/этапов
    ожидания сложнее `Wait` (это MVP2).
  - `storage`: DAO для Rule/RuleStep.
  - `ui`: выбор окна игры, список правил, кнопки Record/Pause/Stop,
    диалог сохранения Rule, Play по кнопке, простой лог выполнения на экране.
  - Тесты: relative coordinates, сериализация Rule/RuleStep, template
    matching (на синтетических изображениях), playback state machine,
    emergency stop (release_all вызывается и отпускает трекнутые кнопки).
  - Критерий готовности: на Windows-машине пользователь может
    Record → выполнить действия в игре → Stop → Save → Play и увидеть
    повторение записанной последовательности.

- **MVP 2 — редактирование и надёжность.** Rule Editor (reorder / delete /
  delay / enable-disable / rename / preview screenshot & template / изменить
  template / confidence threshold / стратегия / test step / run-from-step);
  `WaitForImage`/`WaitImageDisappear` как verification и как
  самостоятельные step-типы; Debug Mode (текущий screenshot, bounding boxes
  найденных templates, confidence, mouse position, relative coords, текущий
  step, playback state).

- **MVP 3 — сценарии и история.** `scenarios` модуль (CRUD, reorder,
  enable/disable rule в сценарии, delay между правилами), `ScenarioRunner`
  (полный запуск / запуск с выбранного правила), история `Execution` в UI,
  retry для отдельного шага, автоматический screenshot при ошибке.

Подробный пошаговый implementation plan для Этапа 0 + MVP1 будет оформлен
отдельно через writing-plans после согласования этого документа.
