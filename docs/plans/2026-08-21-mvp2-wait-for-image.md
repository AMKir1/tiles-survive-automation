# MVP2 / WaitForImage и WaitImageDisappear — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Научить `PlaybackEngine` исполнять шаги `WaitForImage` и `WaitImageDisappear` (ожидание визуального условия вместо фиксированной паузы) и дать пользователю создавать их в Rule Editor кнопкой Add step.

**Architecture:** Ветка ожидания добавляется в `_execute_step` рядом с `WAIT`/`KEY_PRESS`, до общего `grab` — у неё собственный цикл опроса экрана с паузой через `abort_event.wait()`, чтобы F9 прерывал ожидание немедленно. Контракт провала шага меняется с `None` на `StepFailure(message)`, чтобы таймаут сообщал свою причину, а не чужую. Шаблон для ожидания привязывается уже существующей кнопкой Recapture (волна 2) — Add step картинку не запрашивает.

**Tech Stack:** Python 3.12+, PySide6, OpenCV, pytest, pytest-qt (`qtbot`) — всё уже в проекте.

**Spec:** `docs/specs/2026-08-21-mvp2-wait-for-image-design.md`

## Global Constraints

- Схема БД и миграции **не меняются**. Новые шаги укладываются в существующие колонки `RuleStep`.
- `RuleBuilder` не трогается: запись событий такие шаги не порождает и не должна.
- `strategy` у шагов ожидания всегда `VISUAL_ONLY` (колонка `NOT NULL`, значение осмысленно недоступно для правки в UI).
- Таймаут **валит прогон** (`FAILED`), а не пропускает шаг. Настраиваемого `on_timeout` в этом цикле нет.
- Пауза между опросами — только через `self._abort_event.wait(...)`, никогда `time.sleep`, иначе F9 не прервёт ожидание.
- `RuleEditorController` и `AddStepDialog.build_step` не импортируют PySide6-виджеты в логику вставки шага; PySide6 разрешён только в `ui/dialogs/` и `ui/main_window.py`.
- Все тесты гоняются на fake-реализациях, без Win32 и без живой игры.
- Команда тестов: `uv run pytest -q`. Если `uv` нет в PATH — `.venv/Scripts/python.exe -m pytest -q`.

---

## Файловая карта

```
src/tiles_survive_automation/
  config.py                          # изменяется: дефолты таймаута и интервала опроса
  playback/
    engine.py                        # изменяется: StepFailure + ветка ожидания
  ui/
    controllers/
      rule_editor_controller.py      # изменяется: + add_step()
    dialogs/
      add_step_dialog.py             # новый: выбор типа + длительность
      rule_editor_dialog.py          # изменяется: кнопка Add step, спинбокс Timeout, гашение виджетов
tests/unit/
  test_playback_engine.py            # изменяется: контракт StepFailure, все сценарии ожидания
  test_rule_editor_controller.py     # изменяется: + тесты add_step
  test_add_step_dialog.py            # новый
  test_rule_editor_dialog.py         # изменяется: Add step и панель полей
docs/manual-testing/
  mvp2-wait-for-image-checklist.md   # новый
```

---

### Task 1: `StepFailure` — контракт провала шага

**Files:**
- Modify: `src/tiles_survive_automation/playback/engine.py`
- Modify: `tests/unit/test_playback_engine.py`

**Interfaces:**
- Produces: `playback.engine.StepFailure` — `@dataclass` с полем `message: str`. `_execute_step` возвращает либо кортеж из 5 элементов (успех), либо `StepFailure`. Используется всеми задачами 2–5.

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `tests/unit/test_playback_engine.py`:

```python
def test_unresolvable_step_reports_failure_through_step_failure(tmp_path):
    """The failure contract is an object with a message, not a bare None: a
    wait that times out must be able to report its own reason instead of
    inheriting 'could not be resolved by any strategy'."""
    from tiles_survive_automation.playback.engine import StepFailure

    frame = np.full((100, 100, 3), 10, dtype=np.uint8)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    step = _step(StepType.CLICK_IMAGE, {}, template_path=None,
                 strategy=StrategyType.RELATIVE_ONLY)
    engine, _ = _engine(frame, templates_dir, tmp_path)

    outcome = engine._execute_step(step, hwnd=1)

    assert isinstance(outcome, StepFailure)
    assert outcome.message == "step 'Step' could not be resolved by any strategy"
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_playback_engine.py -v -k step_failure`
Expected: FAIL с `ImportError: cannot import name 'StepFailure'`

- [ ] **Step 3: Объявить `StepFailure` и перевести на него провалы**

В `src/tiles_survive_automation/playback/engine.py` добавить импорт `from dataclasses import dataclass` и объявить перед классом `PlaybackEngine`:

```python
@dataclass
class StepFailure:
    """A step that could not be carried out, with the reason to show the user.

    Was a bare `None`, which forced run() to invent one fixed message for every
    kind of failure -- wrong as soon as a wait can time out for its own reason.
    """

    message: str
```

В `_execute_step` заменить три возврата провала (`engine.py:114`, `:118`, `:136` — оба `return None` внутри ветки `DRAG` и `return None` после `_resolve_point` для остальных шагов) на:

```python
            return StepFailure(
                f"step '{step.name}' could not be resolved by any strategy")
```

Внутренний `return None` в `_resolve_point` (последняя строка метода) **не трогать** — это его собственный контракт «точка не разрешилась», его разбирают вызывающие.

В `run()` заменить проверку (`engine.py:72`):

```python
            if outcome is None:
                message = f"step '{step.name}' could not be resolved by any strategy"
```

на:

```python
            if isinstance(outcome, StepFailure):
                message = outcome.message
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_playback_engine.py -v`
Expected: все PASS, включая существующий `test_stops_and_fails_when_no_strategy_resolves` — текст сообщения для обычных шагов не изменился.

- [ ] **Step 5: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/playback/engine.py tests/unit/test_playback_engine.py
git commit -m "refactor: report step failures as StepFailure with their own message"
```

---

### Task 2: `WaitForImage` — совпадение и таймаут

**Files:**
- Modify: `src/tiles_survive_automation/config.py`
- Modify: `src/tiles_survive_automation/playback/engine.py`
- Modify: `tests/unit/test_playback_engine.py`

**Interfaces:**
- Consumes: `StepFailure` (Task 1).
- Produces: `config.WAIT_FOR_IMAGE_TIMEOUT_MS = 10000`, `config.WAIT_POLL_INTERVAL_MS = 250`; `PlaybackEngine._wait_for_image(step, rect)` — возвращает кортеж из 5 элементов либо `StepFailure`. Используется задачами 3–5 и (константы) задачей 7.

- [ ] **Step 1: Написать падающие тесты**

Сначала расширить существующий хелпер `_engine` в `tests/unit/test_playback_engine.py`, чтобы тест мог подставить свой захват экрана. Заменить его сигнатуру и тело:

```python
def _engine(frame, templates_dir, tmp_path, capture=None):
    window = WindowInfo(hwnd=1, title="Tiles Survive", client_rect=(0, 0, 100, 100))
    window_manager = FakeWindowManager([window])
    capture = capture if capture is not None else FakeScreenCapture(frame)
    input_controller = FakeInputController()
    repo = ExecutionRepository(connect(":memory:"))
    logger = get_execution_logger(tmp_path / "execution.log")

    engine = PlaybackEngine(window_manager, capture, input_controller, repo, logger,
                              templates_dir=templates_dir)
    return engine, input_controller
```

Затем добавить в конец файла:

```python
class SequenceCapture:
    """FakeScreenCapture hands out one frame forever; a wait that only succeeds
    after a few polls needs the screen to change between grabs. The last frame
    repeats once the sequence runs out."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.grabs = 0

    def grab(self, rect):
        self.grabs += 1
        frame = self._frames.pop(0) if len(self._frames) > 1 else self._frames[0]
        return frame.copy()


def _wait_image_step(step_type, template_path="marker.png", timeout_ms=1000,
                     poll_interval_ms=10, confidence_threshold=0.9):
    return _step(step_type,
                 {"timeout_ms": timeout_ms, "poll_interval_ms": poll_interval_ms},
                 template_path=template_path,
                 confidence_threshold=confidence_threshold,
                 strategy=StrategyType.VISUAL_ONLY, name="Wait for panel")


def _templates_with_marker(tmp_path):
    """Returns (templates_dir, marker, blank_frame, frame_with_marker)."""
    import cv2

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    marker = np.full((10, 10, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(templates_dir / "marker.png"), marker)

    blank = np.full((100, 100, 3), 10, dtype=np.uint8)
    visible = blank.copy()
    visible[20:30, 20:30] = marker
    return templates_dir, marker, blank, visible


def test_wait_for_image_succeeds_when_template_is_already_on_screen(tmp_path):
    templates_dir, _, _, visible = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(visible, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == []  # a wait never clicks


def test_wait_for_image_polls_until_the_template_shows_up(tmp_path):
    templates_dir, _, blank, visible = _templates_with_marker(tmp_path)
    capture = SequenceCapture([blank, blank, visible])
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path, capture=capture)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert capture.grabs == 3


def test_wait_for_image_fails_with_its_own_message_on_timeout(tmp_path):
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, timeout_ms=100, poll_interval_ms=10)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "timed out after 100ms" in context.error_message
    assert "Wait for panel" in context.error_message
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_playback_engine.py -v -k wait_for_image`
Expected: FAIL — шаг проваливается с `could not be resolved by any strategy`, потому что ветка ожидания ещё не написана и шаг доходит до `_resolve_point`.

- [ ] **Step 3: Добавить дефолты в `config.py`**

В `src/tiles_survive_automation/config.py` после `DEFAULT_CONFIDENCE_THRESHOLD` добавить:

```python
WAIT_FOR_IMAGE_TIMEOUT_MS = 10000
WAIT_POLL_INTERVAL_MS = 250
```

- [ ] **Step 4: Реализовать ветку ожидания**

В `src/tiles_survive_automation/playback/engine.py` добавить в начало файла `import time` (рядом с `import logging`, `import threading`) и `from tiles_survive_automation import config`.

В `_execute_step` сразу после ветки `KEY_PRESS` и **до** строки `frame = self._screen_capture.grab(...)` вставить:

```python
        if step.step_type in (StepType.WAIT_FOR_IMAGE, StepType.WAIT_IMAGE_DISAPPEAR):
            return self._wait_for_image(step, (left, top, width, height))
```

Добавить метод в класс (сразу после `_execute_step`, перед `_resolve_point`):

```python
    def _wait_for_image(self, step: RuleStep, rect: tuple[int, int, int, int]):
        """Poll the screen until the step's template is present (WaitForImage)
        or gone (WaitImageDisappear), or until the timeout runs out.

        The gap between polls goes through the abort event rather than
        time.sleep so F9 cuts a 10-second wait short instead of being noticed
        only once the wait expires.
        """
        template = cv2.imread(str(self._templates_dir / step.template_path))
        want_visible = step.step_type == StepType.WAIT_FOR_IMAGE
        timeout_ms = step.params.get("timeout_ms", config.WAIT_FOR_IMAGE_TIMEOUT_MS)
        poll_s = step.params.get("poll_interval_ms",
                                  config.WAIT_POLL_INTERVAL_MS) / 1000
        started = time.monotonic()
        deadline = started + timeout_ms / 1000

        while True:
            frame = self._screen_capture.grab(rect)
            match = self._matcher.find(frame, template, step.confidence_threshold)
            elapsed_ms = round((time.monotonic() - started) * 1000)

            if (match is not None) == want_visible:
                if want_visible:
                    return (*match.center, step.template_path, match.confidence,
                            f"WaitForImage matched after {elapsed_ms}ms "
                            f"(confidence={match.confidence:.2f})")
                return (None, None, None, None,
                        f"WaitImageDisappear satisfied after {elapsed_ms}ms")

            if time.monotonic() >= deadline:
                waited_for = "appear" if want_visible else "disappear"
                return StepFailure(
                    f"step '{step.name}' timed out after {timeout_ms}ms waiting "
                    f"for the image to {waited_for}")

            if self._abort_event.wait(poll_s):
                # Not a failure: the top of run()'s loop turns a set abort event
                # into STOPPED. Same shape as the plain Wait branch.
                return (None, None, None, None,
                        f"{step.step_type.value} aborted after {elapsed_ms}ms")
```

Условие проверяется до дедлайна, поэтому даже при `timeout_ms=0` экран опрашивается ровно один раз.

- [ ] **Step 5: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_playback_engine.py -v -k wait_for_image`
Expected: PASS (3 passed)

- [ ] **Step 6: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 7: Commit**

```bash
git add src/tiles_survive_automation/config.py \
        src/tiles_survive_automation/playback/engine.py \
        tests/unit/test_playback_engine.py
git commit -m "feat: execute WaitForImage steps with a polling screen check"
```

---

### Task 3: F9 прерывает ожидание

**Files:**
- Modify: `tests/unit/test_playback_engine.py`

**Interfaces:**
- Consumes: `PlaybackEngine._wait_for_image` (Task 2), `PlaybackEngine.abort()` (существует).
- Produces: ничего нового — задача доказывает поведение, уже заложенное в Task 2, и защищает его от регрессии.

- [ ] **Step 1: Написать тест**

Добавить в конец `tests/unit/test_playback_engine.py`:

```python
class AbortingCapture:
    """Fires engine.abort() from inside a grab, so the abort lands mid-wait
    without a thread and without wall-clock timing in the test."""

    def __init__(self, frame, abort_on_grab):
        self._frame = frame
        self._abort_on_grab = abort_on_grab
        self.engine = None
        self.grabs = 0

    def grab(self, rect):
        self.grabs += 1
        if self.grabs >= self._abort_on_grab:
            self.engine.abort()
        return self._frame.copy()


def test_abort_during_a_wait_stops_the_run_instead_of_waiting_out_the_timeout(tmp_path):
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    capture = AbortingCapture(blank, abort_on_grab=2)
    # A timeout long enough that reaching it would hang the test: the run may
    # only end this quickly because the abort cut the wait short.
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, timeout_ms=60000,
                            poll_interval_ms=10)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path, capture=capture)
    capture.engine = engine

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.STOPPED
    assert context.error_message is None  # aborted, not failed
    assert capture.grabs == 2
```

- [ ] **Step 2: Запустить**

Run: `uv run pytest tests/unit/test_playback_engine.py -v -k abort_during_a_wait`
Expected: PASS — реализация из Task 2 уже это обеспечивает. Если тест падает по таймауту, значит пауза между опросами сделана через `time.sleep`, а не через `self._abort_event.wait()` — вернуться к Task 2 Step 4.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_playback_engine.py
git commit -m "test: pin down that F9 cuts a running wait short"
```

---

### Task 4: `WaitImageDisappear`

**Files:**
- Modify: `tests/unit/test_playback_engine.py`

**Interfaces:**
- Consumes: `PlaybackEngine._wait_for_image` (Task 2).
- Produces: ничего нового — зеркальная ветка уже написана в Task 2 через флаг `want_visible`; задача закрывает её тестами.

- [ ] **Step 1: Написать тесты**

Добавить в конец `tests/unit/test_playback_engine.py`:

```python
def test_wait_image_disappear_succeeds_when_the_template_is_already_gone(tmp_path):
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_IMAGE_DISAPPEAR)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, input_controller = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert input_controller.calls == []


def test_wait_image_disappear_polls_until_the_template_goes_away(tmp_path):
    templates_dir, _, blank, visible = _templates_with_marker(tmp_path)
    capture = SequenceCapture([visible, visible, blank])
    step = _wait_image_step(StepType.WAIT_IMAGE_DISAPPEAR)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path, capture=capture)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.COMPLETED
    assert capture.grabs == 3


def test_wait_image_disappear_fails_when_the_template_stays_on_screen(tmp_path):
    templates_dir, _, _, visible = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_IMAGE_DISAPPEAR, timeout_ms=100,
                            poll_interval_ms=10)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(visible, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "waiting for the image to disappear" in context.error_message
```

- [ ] **Step 2: Запустить**

Run: `uv run pytest tests/unit/test_playback_engine.py -v -k disappear`
Expected: PASS (3 passed)

- [ ] **Step 3: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_playback_engine.py
git commit -m "test: cover WaitImageDisappear appear/poll/timeout paths"
```

---

### Task 5: Внятные отказы для шага без шаблона и с битым файлом

**Files:**
- Modify: `src/tiles_survive_automation/playback/engine.py`
- Modify: `tests/unit/test_playback_engine.py`

**Interfaces:**
- Consumes: `StepFailure` (Task 1), `_wait_for_image` (Task 2).
- Produces: ничего нового наружу.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_playback_engine.py`:

```python
def test_wait_step_without_a_template_says_to_use_recapture(tmp_path):
    """Add step creates the step without a picture on purpose -- the user
    attaches it with Recapture afterwards. Forgetting that must produce advice,
    not a cv2 crash or a pointless full-length timeout."""
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, template_path=None,
                            timeout_ms=60000)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "has no template" in context.error_message
    assert "Recapture" in context.error_message


def test_wait_step_with_an_unreadable_template_file_says_so(tmp_path):
    """cv2.imread returns None for a missing or non-ASCII path instead of
    raising, so an unreadable template must be reported, not treated as
    'image not on screen yet'."""
    templates_dir, _, blank, _ = _templates_with_marker(tmp_path)
    (templates_dir / "broken.png").write_bytes(b"not a png")
    step = _wait_image_step(StepType.WAIT_FOR_IMAGE, template_path="broken.png",
                            timeout_ms=60000)
    rule = Rule(id=1, name="R", description=None, window_title_hint=None, steps=[step])
    engine, _ = _engine(blank, templates_dir, tmp_path)

    context = engine.run(rule, hwnd=1)

    assert context.state == PlaybackState.FAILED
    assert "unreadable" in context.error_message
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_playback_engine.py -v -k "no_template or unreadable"`
Expected: FAIL — первый тест падает с `TypeError` внутри `cv2.imread` (путь собирается из `None`), второй виснет до таймаута и не содержит нужного текста.

- [ ] **Step 3: Добавить проверки перед циклом**

В `_wait_for_image` заменить первую строку

```python
        template = cv2.imread(str(self._templates_dir / step.template_path))
```

на:

```python
        if not step.template_path:
            return StepFailure(f"step '{step.name}' has no template - use "
                               f"Recapture in the Rule Editor first")
        template_path = self._templates_dir / step.template_path
        template = cv2.imread(str(template_path))
        if template is None:
            return StepFailure(f"step '{step.name}' template file is missing or "
                               f"unreadable: {template_path}")
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_playback_engine.py -v`
Expected: все PASS

- [ ] **Step 5: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/playback/engine.py tests/unit/test_playback_engine.py
git commit -m "feat: explain a wait step with a missing or unreadable template"
```

---

### Task 6: `RuleEditorController.add_step`

**Files:**
- Modify: `src/tiles_survive_automation/ui/controllers/rule_editor_controller.py`
- Modify: `tests/unit/test_rule_editor_controller.py`

**Interfaces:**
- Consumes: `self._draft`, `self._reindex()` (существуют).
- Produces: `RuleEditorController.add_step(step: RuleStep, after_index: int | None = None) -> None` — вставляет шаг после указанного индекса (в конец при `None`) и пересчитывает `order_index`. Используется задачей 7.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_rule_editor_controller.py`:

```python
def test_add_step_inserts_after_the_given_index_and_reindexes():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.add_step(_step(None, 99, "NEW"), after_index=0)

    assert [s.name for s in controller.draft.steps] == ["A", "NEW", "B", "C"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1, 2, 3]


def test_add_step_without_an_index_appends_to_the_end():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.add_step(_step(None, 99, "NEW"))

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C", "NEW"]
    assert [s.order_index for s in controller.draft.steps] == [0, 1, 2, 3]


def test_add_step_after_the_last_index_appends():
    controller = RuleEditorController(_rule(), FakeRuleRepository())

    controller.add_step(_step(None, 99, "NEW"), after_index=2)

    assert [s.name for s in controller.draft.steps] == ["A", "B", "C", "NEW"]


def test_add_step_into_an_empty_draft_produces_a_single_step():
    controller = RuleEditorController(_rule(), FakeRuleRepository())
    for _ in range(3):
        controller.delete_step(0)

    controller.add_step(_step(None, 99, "NEW"))

    assert [s.name for s in controller.draft.steps] == ["NEW"]
    assert controller.draft.steps[0].order_index == 0


def test_add_step_does_not_write_to_the_repository():
    repository = FakeRuleRepository()
    controller = RuleEditorController(_rule(), repository)

    controller.add_step(_step(None, 99, "NEW"))

    assert repository.save_calls == []
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v -k add_step`
Expected: FAIL с `AttributeError: 'RuleEditorController' object has no attribute 'add_step'`

- [ ] **Step 3: Реализовать `add_step`**

В `src/tiles_survive_automation/ui/controllers/rule_editor_controller.py` добавить метод после `update_step` и перед `draft_from`:

```python
    def add_step(self, step: RuleStep, after_index: int | None = None) -> None:
        position = len(self._draft.steps) if after_index is None else after_index + 1
        self._draft.steps.insert(position, step)
        self._reindex()
```

`RuleStep` в этом файле ещё не импортирован — заменить существующую строку
`from tiles_survive_automation.rules.models import Rule` на:

```python
from tiles_survive_automation.rules.models import Rule, RuleStep
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_controller.py -v`
Expected: все PASS

- [ ] **Step 5: Commit**

```bash
git add src/tiles_survive_automation/ui/controllers/rule_editor_controller.py \
        tests/unit/test_rule_editor_controller.py
git commit -m "feat: add RuleEditorController.add_step"
```

---

### Task 7: `AddStepDialog`

**Files:**
- Create: `src/tiles_survive_automation/ui/dialogs/add_step_dialog.py`
- Create: `tests/unit/test_add_step_dialog.py`

**Interfaces:**
- Consumes: `config.WAIT_FOR_IMAGE_TIMEOUT_MS`, `config.WAIT_POLL_INTERVAL_MS`, `config.DEFAULT_CONFIDENCE_THRESHOLD` (Task 2 и существующие).
- Produces: `AddStepDialog(parent=None)` с атрибутами `type_combo: QComboBox`, `duration_spin: QSpinBox`, `duration_label: QLabel` и методом `build_step() -> RuleStep`. Используется задачей 8.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_add_step_dialog.py`:

```python
from tiles_survive_automation.rules.models import StepType, StrategyType
from tiles_survive_automation.ui.dialogs.add_step_dialog import AddStepDialog


def _dialog(qtbot):
    dialog = AddStepDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_offers_exactly_the_three_step_types_a_user_can_add(qtbot):
    dialog = _dialog(qtbot)

    types = [dialog.type_combo.itemData(i) for i in range(dialog.type_combo.count())]

    assert types == [StepType.WAIT_FOR_IMAGE, StepType.WAIT_IMAGE_DISAPPEAR,
                     StepType.WAIT]


def test_builds_a_wait_for_image_step_with_timeout_and_poll_interval(qtbot):
    dialog = _dialog(qtbot)
    dialog.type_combo.setCurrentIndex(
        dialog.type_combo.findData(StepType.WAIT_FOR_IMAGE))
    dialog.duration_spin.setValue(4000)

    step = dialog.build_step()

    assert step.step_type == StepType.WAIT_FOR_IMAGE
    assert step.params["timeout_ms"] == 4000
    assert step.params["poll_interval_ms"] > 0
    assert step.template_path is None       # attached later via Recapture
    assert step.strategy == StrategyType.VISUAL_ONLY
    assert step.enabled is True
    assert step.id is None


def test_builds_a_plain_wait_step_with_a_duration(qtbot):
    dialog = _dialog(qtbot)
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(StepType.WAIT))
    dialog.duration_spin.setValue(1500)

    step = dialog.build_step()

    assert step.step_type == StepType.WAIT
    assert step.params == {"duration_ms": 1500}


def test_duration_label_follows_the_selected_type(qtbot):
    dialog = _dialog(qtbot)

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(StepType.WAIT))
    assert "Duration" in dialog.duration_label.text()

    dialog.type_combo.setCurrentIndex(
        dialog.type_combo.findData(StepType.WAIT_IMAGE_DISAPPEAR))
    assert "Timeout" in dialog.duration_label.text()


def test_generated_name_describes_the_step_type(qtbot):
    dialog = _dialog(qtbot)
    dialog.type_combo.setCurrentIndex(
        dialog.type_combo.findData(StepType.WAIT_IMAGE_DISAPPEAR))

    assert dialog.build_step().name == "WaitImageDisappear"
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_add_step_dialog.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'tiles_survive_automation.ui.dialogs.add_step_dialog'`

- [ ] **Step 3: Реализовать диалог**

Создать `src/tiles_survive_automation/ui/dialogs/add_step_dialog.py`:

```python
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from tiles_survive_automation import config
from tiles_survive_automation.rules.models import RuleStep, StepType, StrategyType

ADDABLE_STEP_TYPES = (StepType.WAIT_FOR_IMAGE, StepType.WAIT_IMAGE_DISAPPEAR,
                      StepType.WAIT)


class AddStepDialog(QDialog):
    """Picks the type and the duration of a new step. Deliberately does not ask
    for a template: the picture is attached afterwards with the Rule Editor's
    Recapture button, which already knows how to wait for a click on the game.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add step")

        self.type_combo = QComboBox()
        for step_type in ADDABLE_STEP_TYPES:
            self.type_combo.addItem(step_type.value, userData=step_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 600_000)
        self.duration_spin.setSingleStep(100)
        self.duration_spin.setValue(config.WAIT_FOR_IMAGE_TIMEOUT_MS)

        self.duration_label = QLabel("Timeout (ms)")

        form = QFormLayout()
        form.addRow("Type", self.type_combo)
        form.addRow(self.duration_label, self.duration_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout()
        outer.addLayout(form)
        outer.addWidget(buttons)
        self.setLayout(outer)

    def _selected_type(self) -> StepType:
        return StepType(self.type_combo.currentData())

    def _on_type_changed(self, index: int) -> None:
        if index < 0:
            return
        is_plain_wait = self._selected_type() == StepType.WAIT
        self.duration_label.setText("Duration (ms)" if is_plain_wait
                                     else "Timeout (ms)")

    def build_step(self) -> RuleStep:
        step_type = self._selected_type()
        value = self.duration_spin.value()
        if step_type == StepType.WAIT:
            params = {"duration_ms": value}
        else:
            params = {"timeout_ms": value,
                      "poll_interval_ms": config.WAIT_POLL_INTERVAL_MS}
        return RuleStep(
            id=None, order_index=0, step_type=step_type, name=step_type.value,
            enabled=True, params=params, template_path=None,
            confidence_threshold=config.DEFAULT_CONFIDENCE_THRESHOLD,
            strategy=StrategyType.VISUAL_ONLY, verification=None,
            screenshot_path=None, delay_after_ms=0,
        )
```

`order_index=0` — заглушка: реальное значение проставит `RuleEditorController.add_step` через `_reindex()`.

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_add_step_dialog.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/add_step_dialog.py \
        tests/unit/test_add_step_dialog.py
git commit -m "feat: add AddStepDialog for wait steps"
```

---

### Task 8: Кнопка Add step в Rule Editor

**Files:**
- Modify: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `tests/unit/test_rule_editor_dialog.py`

**Interfaces:**
- Consumes: `RuleEditorController.add_step` (Task 6), `AddStepDialog` (Task 7).
- Produces: `RuleEditorDialog.add_step_button: QPushButton`, `RuleEditorDialog._on_add_step_clicked()`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_rule_editor_dialog.py`:

```python
from tiles_survive_automation.ui.dialogs.add_step_dialog import AddStepDialog


def _accept_add_step_dialog(monkeypatch, step_type, value):
    """Drives AddStepDialog without a modal loop: fills its widgets and reports
    Accepted, the same way the existing MainWindow tests drive RuleEditorDialog."""
    def fake_exec(dialog):
        dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(step_type))
        dialog.duration_spin.setValue(value)
        return QDialog.Accepted

    monkeypatch.setattr(AddStepDialog, "exec", fake_exec)


def test_add_step_inserts_the_chosen_step_after_the_selected_one(qtbot, tmp_path,
                                                                monkeypatch):
    steps = [_step(name="A", order_index=0), _step(name="B", order_index=1)]
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(*steps))
    dialog.step_list.setCurrentRow(0)
    _accept_add_step_dialog(monkeypatch, StepType.WAIT_FOR_IMAGE, 4000)

    dialog.add_step_button.click()

    names = [s.step_type.value for s in dialog.controller.draft.steps]
    assert names == ["ClickImage", "WaitForImage", "ClickImage"]
    assert dialog.controller.draft.steps[1].params["timeout_ms"] == 4000


def test_add_step_selects_the_new_step_so_recapture_targets_it(qtbot, tmp_path,
                                                               monkeypatch):
    steps = [_step(name="A", order_index=0), _step(name="B", order_index=1)]
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(*steps))
    dialog.step_list.setCurrentRow(0)
    _accept_add_step_dialog(monkeypatch, StepType.WAIT_FOR_IMAGE, 4000)

    dialog.add_step_button.click()

    assert dialog.step_list.currentRow() == 1
    assert dialog._current_index == 1


def test_add_step_cancelled_changes_nothing(qtbot, tmp_path, monkeypatch):
    dialog, _ = _dialog(qtbot, tmp_path)
    dialog.step_list.setCurrentRow(0)
    monkeypatch.setattr(AddStepDialog, "exec", lambda dialog: QDialog.Rejected)

    dialog.add_step_button.click()

    assert len(dialog.controller.draft.steps) == 1


def test_add_step_writes_nothing_to_the_repository_until_save(qtbot, tmp_path,
                                                              monkeypatch):
    rule_repository = RuleRepository(connect(":memory:"))
    saved_rule = rule_repository.save(_rule())
    dialog, _ = _dialog(qtbot, tmp_path, rule=saved_rule,
                        rule_repository=rule_repository)
    dialog.step_list.setCurrentRow(0)
    _accept_add_step_dialog(monkeypatch, StepType.WAIT, 1500)

    dialog.add_step_button.click()

    assert len(rule_repository.get(saved_rule.id).steps) == 1
    dialog._on_save_clicked()
    assert len(rule_repository.get(saved_rule.id).steps) == 2
```

Дополнить импорты в начале файла:

```python
from PySide6.QtWidgets import QDialog
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v -k add_step`
Expected: FAIL с `AttributeError: 'RuleEditorDialog' object has no attribute 'add_step_button'`

- [ ] **Step 3: Реализовать кнопку**

В `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py` дополнить импорт:

```python
from tiles_survive_automation.ui.dialogs.add_step_dialog import AddStepDialog
```

В `_build_ui` заменить блок с кнопками списка:

```python
        up_button = QPushButton("Up")
        down_button = QPushButton("Down")
        delete_button = QPushButton("Delete")
        up_button.clicked.connect(self._on_up_clicked)
        down_button.clicked.connect(self._on_down_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)

        list_buttons = QHBoxLayout()
        for button in (up_button, down_button, delete_button):
            list_buttons.addWidget(button)
```

на:

```python
        up_button = QPushButton("Up")
        down_button = QPushButton("Down")
        delete_button = QPushButton("Delete")
        self.add_step_button = QPushButton("Add step")
        up_button.clicked.connect(self._on_up_clicked)
        down_button.clicked.connect(self._on_down_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)
        self.add_step_button.clicked.connect(self._on_add_step_clicked)

        list_buttons = QHBoxLayout()
        for button in (up_button, down_button, delete_button, self.add_step_button):
            list_buttons.addWidget(button)
```

Добавить метод рядом с `_on_delete_clicked`:

```python
    def _on_add_step_clicked(self) -> None:
        dialog = AddStepDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.controller.add_step(dialog.build_step(), self._current_index)
        # The new step becomes current so the next thing the user reaches for --
        # Recapture, to give it a template -- lands on it.
        new_index = 0 if self._current_index is None else self._current_index + 1
        self._refresh_list()
        self.step_list.setCurrentRow(new_index)
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v`
Expected: все PASS

- [ ] **Step 5: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py \
        tests/unit/test_rule_editor_dialog.py
git commit -m "feat: add the Add step button to the Rule Editor"
```

---

### Task 9: Спинбокс Timeout и гашение виджетов по типу шага

**Files:**
- Modify: `src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py`
- Modify: `tests/unit/test_rule_editor_dialog.py`

**Interfaces:**
- Consumes: `RuleEditorController.update_step` (существует).
- Produces: `RuleEditorDialog.timeout_spin: QSpinBox`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_rule_editor_dialog.py`:

```python
def _wait_step(step_type=StepType.WAIT_FOR_IMAGE, timeout_ms=5000, name="W"):
    return RuleStep(
        id=None, order_index=0, step_type=step_type, name=name, enabled=True,
        params={"timeout_ms": timeout_ms, "poll_interval_ms": 250},
        template_path=None, confidence_threshold=0.9,
        strategy=StrategyType.VISUAL_ONLY, verification=None,
        screenshot_path=None, delay_after_ms=0,
    )


def test_timeout_spin_shows_the_timeout_of_a_wait_step(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_wait_step(timeout_ms=7000)))

    dialog.step_list.setCurrentRow(0)

    assert dialog.timeout_spin.isEnabled() is True
    assert dialog.timeout_spin.value() == 7000


def test_editing_the_timeout_writes_it_into_the_step_params(qtbot, tmp_path):
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(_wait_step(timeout_ms=7000)))
    dialog.step_list.setCurrentRow(0)

    dialog.timeout_spin.setValue(2500)

    params = dialog.controller.draft.steps[0].params
    assert params["timeout_ms"] == 2500
    assert params["poll_interval_ms"] == 250  # untouched


def test_plain_wait_step_edits_its_duration_through_the_same_spin(qtbot, tmp_path):
    step = RuleStep(
        id=None, order_index=0, step_type=StepType.WAIT, name="Pause", enabled=True,
        params={"duration_ms": 800}, template_path=None, confidence_threshold=0.9,
        strategy=StrategyType.VISUAL_ONLY, verification=None,
        screenshot_path=None, delay_after_ms=0,
    )
    dialog, _ = _dialog(qtbot, tmp_path, rule=_rule(step))
    dialog.step_list.setCurrentRow(0)
    assert dialog.timeout_spin.value() == 800

    dialog.timeout_spin.setValue(1200)

    assert dialog.controller.draft.steps[0].params == {"duration_ms": 1200}


def test_widgets_that_do_not_apply_are_disabled_per_step_type(qtbot, tmp_path):
    click_step = _step(name="Click")
    wait_image_step = _wait_step(name="WaitImage")
    plain_wait_step = RuleStep(
        id=None, order_index=0, step_type=StepType.WAIT, name="Pause", enabled=True,
        params={"duration_ms": 800}, template_path=None, confidence_threshold=0.9,
        strategy=StrategyType.VISUAL_ONLY, verification=None,
        screenshot_path=None, delay_after_ms=0,
    )
    dialog, _ = _dialog(qtbot, tmp_path,
                        rule=_rule(click_step, wait_image_step, plain_wait_step))

    dialog.step_list.setCurrentRow(0)
    assert (dialog.strategy_combo.isEnabled(), dialog.confidence_spin.isEnabled(),
            dialog.timeout_spin.isEnabled()) == (True, True, False)

    dialog.step_list.setCurrentRow(1)
    assert (dialog.strategy_combo.isEnabled(), dialog.confidence_spin.isEnabled(),
            dialog.timeout_spin.isEnabled()) == (False, True, True)

    dialog.step_list.setCurrentRow(2)
    assert (dialog.strategy_combo.isEnabled(), dialog.confidence_spin.isEnabled(),
            dialog.timeout_spin.isEnabled()) == (False, False, True)
```

Дополнить импорт моделей в начале файла, если `RuleStep` там ещё не импортирован — он уже есть в строке `from tiles_survive_automation.rules.models import Rule, RuleStep, StepType, StrategyType`.

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v -k "timeout or per_step_type"`
Expected: FAIL с `AttributeError: 'RuleEditorDialog' object has no attribute 'timeout_spin'`

- [ ] **Step 3: Добавить спинбокс и гашение**

В `_build_ui`, сразу после создания `self.strategy_combo` и его наполнения, добавить:

```python
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 600_000)
        self.timeout_spin.setSingleStep(100)
```

Рядом с остальными подключениями сигналов добавить:

```python
        self.timeout_spin.valueChanged.connect(self._on_timeout_changed)
```

В `form` добавить строку после `Strategy`:

```python
        form.addRow("Timeout / duration (ms)", self.timeout_spin)
```

В `_on_step_selected` добавить `self.timeout_spin` в **оба** кортежа
`blockSignals` и вставить установку значения сразу после
`self.strategy_combo.setCurrentIndex(...)`, то есть **внутри** заблокированного
участка:

```python
        self.timeout_spin.setValue(self._duration_of(step))
```

Порядок здесь принципиален: если поставить значение после разблокировки
сигналов, `valueChanged` сработает на программную установку и перезапишет
`params` соседнего шага при каждом переключении выделения.

Гашение виджетов, наоборот, ставится после разблокировки — `setEnabled`
сигналов не шлёт. Сразу после `self.test_button.setEnabled(can_test)` добавить:

```python
        is_wait_image = step.step_type in (StepType.WAIT_FOR_IMAGE,
                                            StepType.WAIT_IMAGE_DISAPPEAR)
        is_plain_wait = step.step_type == StepType.WAIT
        self.timeout_spin.setEnabled(is_wait_image or is_plain_wait)
        self.confidence_spin.setEnabled(not is_plain_wait)
        self.strategy_combo.setEnabled(not (is_wait_image or is_plain_wait))
```

Сейчас в файле импортирован только `StrategyType` — заменить эту строку на:

```python
from tiles_survive_automation.rules.models import StepType, StrategyType
```

Добавить два метода рядом с `_on_field_changed`:

```python
    @staticmethod
    def _duration_key(step) -> str:
        return "duration_ms" if step.step_type == StepType.WAIT else "timeout_ms"

    def _duration_of(self, step) -> int:
        return int(step.params.get(self._duration_key(step), 0))

    def _on_timeout_changed(self, value: int) -> None:
        if self._current_index is None:
            return
        step = self.controller.draft.steps[self._current_index]
        # Replace the whole params dict: update_step swaps fields wholesale, so
        # the other keys (poll_interval_ms) have to be carried over by hand.
        self.controller.update_step(
            self._current_index,
            params={**step.params, self._duration_key(step): value})
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_rule_editor_dialog.py -v`
Expected: все PASS

- [ ] **Step 5: Прогнать весь набор**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 6: Commit**

```bash
git add src/tiles_survive_automation/ui/dialogs/rule_editor_dialog.py \
        tests/unit/test_rule_editor_dialog.py
git commit -m "feat: edit wait timeouts in the Rule Editor, hide fields that do not apply"
```

---

### Task 10: Ручной чек-лист и обновление документации

**Files:**
- Create: `docs/manual-testing/mvp2-wait-for-image-checklist.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: всё, реализованное задачами 1–9.
- Produces: ничего для кода.

- [ ] **Step 1: Создать чек-лист**

Создать `docs/manual-testing/mvp2-wait-for-image-checklist.md`:

```markdown
# MVP2 / WaitForImage и WaitImageDisappear — ручная валидация на Windows

Выполняется на реальной Windows-машине, после того как автотесты
(`uv run pytest -q`) проходят. Приложение должно быть запущено от имени
администратора (`run-as-admin.cmd`) — игра элевирована, иначе Windows
молча выбросит и ввод, и события хука.

Автотесты покрывают цикл опроса, таймаут и прерывание на fake-реализациях.
Здесь проверяется только то, что требует живой игры.

1. Открыть Edit на правиле, выделить шаг перед долгой загрузкой, нажать
   **Add step** → тип `WaitForImage`, таймаут 15000 → OK. Новый шаг появился
   сразу после выделенного и стал выделенным сам.
2. Нажать **Recapture** на новом шаге, кликнуть в игре по элементу, который
   появляется только после загрузки. Превью справа обновилось.
3. Нажать **Save**, затем **Play**. В логе выполнения должна появиться строка
   `WaitForImage matched after ...ms (confidence=...)`, и следующий шаг должен
   выполниться уже после появления элемента, а не вслепую.
4. Повторить с типом `WaitImageDisappear` на элементе, который исчезает
   (индикатор загрузки): в логе `WaitImageDisappear satisfied after ...ms`.
5. Поставить заведомо недостижимое условие (шаблон элемента, которого на
   экране не будет) с таймаутом 5000 и запустить Play — прогон должен
   остановиться со статусом FAILED и сообщением `timed out after 5000ms`,
   а не идти дальше вслепую.
6. Во время долгого ожидания нажать **F9** — ожидание должно прерваться
   немедленно, не досиживая таймаут.
7. Добавить шаг `WaitForImage` и **не** делать Recapture, нажать Play —
   внятное сообщение `has no template - use Recapture in the Rule Editor
   first`, без зависания на весь таймаут.

Отметить каждый пункт как пройденный/непройденный с комментарием.
```

- [ ] **Step 2: Обновить раздел «Состояние» в `CLAUDE.md`**

В `CLAUDE.md` в разделе «Состояние» перенести `WaitForImage`/`WaitImageDisappear` из «не сделано» в «готово»: убрать из абзаца «Не сделано» фрагмент про типы, объявленные в `StepType`, и дописать в абзац «Готово» предложение:

```
Шаги `WaitForImage`/`WaitImageDisappear` исполняются движком и создаются
кнопкой Add step в Rule Editor; шаблон к ним привязывается Recapture.
```

Абзац про неиспользуемую колонку `verification_json` **оставить** — verification как отдельный режим по-прежнему не сделан.

- [ ] **Step 3: Прогнать весь набор в последний раз**

Run: `uv run pytest -q`
Expected: все PASS

- [ ] **Step 4: Commit**

```bash
git add docs/manual-testing/mvp2-wait-for-image-checklist.md CLAUDE.md
git commit -m "docs: add wait-for-image manual checklist, update project state"
```

- [ ] **Step 5: Пройти чек-лист на живой игре**

Выполнить `docs/manual-testing/mvp2-wait-for-image-checklist.md` целиком и
отметить статус в шапке файла, как это сделано в чек-листах MVP1 и волн 1–2.
До этого момента фича не считается готовой.
