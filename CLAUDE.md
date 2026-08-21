# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Команды

```bash
uv sync                                    # зависимости (venv в .venv)
uv run python -m tiles_survive_automation.app   # запустить GUI
uv run pytest -q                           # весь набор тестов
uv run pytest tests/unit/test_playback_engine.py -q          # один файл
uv run pytest tests/unit/test_playback_engine.py -k abort -v # один тест
```

Если `uv` не в PATH (так бывает на этой машине) — то же самое через интерпретатор venv:
`.venv/Scripts/python.exe -m pytest -q`.

**Игру запускают от администратора, поэтому приложение тоже нужно запускать
элевированным** — иначе Windows UIPI молча выбрасывает весь синтезированный
ввод (`SendInput` при этом возвращает успех, курсор не двигается), и тот же
запрет глушит низкоуровневый хук записи. Для запуска есть `run-as-admin.cmd`
в корне репозитория. Замер на живом окне: запрошенное смещение курсора на
442 px дало 0 px без единой ошибки.

Линтера и форматтера в проекте нет — стиль поддерживается вручную по образцу
соседнего кода.

## Что это

Windows-приложение для записи, редактирования и воспроизведения действий в игре
Tiles Survive. Работа **только через экран** (screenshot + OpenCV template
matching) и обычный пользовательский ввод (SendInput/pynput). Чтение памяти
процесса, DLL injection, перехват трафика и обход античита — вне рамок проекта
по решению в дизайн-спеке; не предлагать такие подходы.

## Архитектура

Слои и правило зависимостей (`docs/specs/2026-08-17-...-design.md`, раздел 4):

```
ui → recorder / playback / rules → window / capture / input / vision / storage
```

Нижние модули не знают о верхних и **не импортируют PySide6**. Контроллеры в
`ui/controllers/` — тоже чистый Python поверх Qt-сигналов; PySide6 разрешён в
`ui/main_window.py`, `ui/dialogs/` и в самих контроллерах только ради
`QObject`/`Signal`/`QTimer`.

Всё, что трогает Win32, спрятано за портами (`window`, `capture`, `input`):
у каждого порта есть `win32_*`/`mss_*` реализация и `fake_*` для тестов,
выбор — в `factory.py` по `platform.system()`. Благодаря этому весь набор
тестов гоняется без живой игры и без Windows-специфики. **Новый код, трогающий
ОС, обязан идти этим же путём: порт + fake + фабрика.**

`recorder` и `playback` крутятся в своих `threading.Thread`; в Qt их результаты
попадают через `queue`/`QTimer`-поллинг в `ui/controllers/`, а не прямым
вызовом виджетов из чужого потока.

## Ключевые инварианты

- **Один `PlaybackEngine`/`PlaybackController` на приложение.** `EmergencyStop`
  (F9) привязывается колбэком к конкретному экземпляру один раз в
  `MainWindow.__init__`. Если создать второй движок (например, для диалога),
  F9 перестанет прерывать его выполнение. `RuleEditorDialog` поэтому получает
  тот же экземпляр через конструктор.
- **Прервать выполнение можно двумя способами:** F9 и ручной клик ЛКМ
  (`win32_manual_click_watcher`). Watcher обязан игнорировать синтетические
  клики самого бота — иначе Play прерывает сам себя.
- **Картинки на диск пишутся только через `recorder/image_io.write_image`.**
  `cv2.imwrite` на Windows молча возвращает False при не-ASCII пути (кириллица
  в имени пользователя) и теряет файл без ошибки. То же ограничение действует
  на чтении: `cv2.imread` вернёт `None` — вызывающий код обязан это проверять.
- **Шаблоны раскладываются по `<session_id>/`**, а не по `<rule_id>`: у каждой
  записи свой `uuid4().hex[:8]`, поэтому файлы разных записей не коллизируют.
  `template_path` в БД хранится вместе с этим префиксом, относительно
  `templates_dir`.
- **SQLite в WAL-режиме**, единственный писатель. UI читает, playback/recorder
  пишут через свои repository. ORM нет — сырой SQL в `storage/`, схема в
  `storage/schema.sql`.
- **Стратегии шага:** visual (template matching) → relative-координаты →
  остановка с ошибкой. `VISUAL_THEN_RELATIVE` по умолчанию; провал визуального
  поиска при нём — это не провал шага, а переход к Strategy 2.

## Процесс работы

Каждая фича проходит цикл: **дизайн-спека → implementation plan → реализация по
TDD → ручной чек-лист на Windows**. Соответственно `docs/specs/`, `docs/plans/`,
`docs/manual-testing/`, имена файлов с датой. План разбит на задачи с
чекбоксами и пишет тесты до кода — при исполнении следовать ему по шагам, а не
писать «в целом то же самое».

Ручные чек-листы существуют потому, что часть рисков (DPI, foreground lock,
тайминги SendInput, реальный клик по игре) принципиально не проверяется
fake-реализациями. Не считать фичу готовой, пока чек-лист не отмечен пройденным.

## Состояние

Готово: этап 0, MVP1 (Record → Save → Play, F9, DPI, прерывание кликом),
плюс сверх спеки — Schedule (повтор батчами), Rename/Delete. MVP2 Rule Editor:
волна 1 (reorder/delete/rename/enabled/delay/confidence/strategy) и волна 2
(preview, recapture, test step, run-from-step).

Не сделано: `WaitForImage`/`WaitImageDisappear` (типы объявлены в `StepType` и
колонка `verification_json` есть в схеме, но `PlaybackEngine` их не исполняет,
а `RuleBuilder` не создаёт), Debug Mode, весь MVP3 — модуль `scenarios/`
отсутствует, хотя таблицы `Scenario`/`ScenarioRule` в схеме уже описаны;
истории `Execution` нет в UI, хотя `ExecutionRepository` её пишет.
`StepType.HOTKEY` объявлен, но не создаётся билдером и не исполняется движком.
