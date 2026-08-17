"""Diagnostic script — run this on Windows: uv run python diagnose_drag.py

Prints exactly what coordinates get computed for a Drag step and tests
SetCursorPos with them directly, to find the real root cause behind
'SetCursorPos', 'No error message id available'.
"""
import sys

from tiles_survive_automation import config
from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.rule_repository import RuleRepository
from tiles_survive_automation.rules.models import StepType
from tiles_survive_automation.window.factory import get_window_manager
from tiles_survive_automation.playback.strategies import resolve_relative_point

conn = connect(config.DATABASE_PATH)
repo = RuleRepository(conn)
rules = repo.list_all()

drag_steps = []
for rule in rules:
    for step in rule.steps:
        if step.step_type == StepType.DRAG:
            drag_steps.append((rule, step))

if not drag_steps:
    print("No Drag steps found in any saved rule.")
    sys.exit(1)

print(f"Found {len(drag_steps)} Drag step(s).\n")

wm = get_window_manager()
print(f"WindowManager class: {type(wm).__name__}")
windows = wm.list_windows()
print(f"Windows found: {len(windows)}")
for w in windows[:15]:
    print(f"  hwnd={w.hwnd} title={w.title!r}")

if not windows:
    print("No windows found, cannot continue.")
    sys.exit(1)

# Use the first window whose title matches any rule's window_title_hint,
# else just the first window in the list.
target = windows[0]
for rule, _ in drag_steps:
    if rule.window_title_hint:
        for w in windows:
            if w.title == rule.window_title_hint:
                target = w
                break

hwnd = target.hwnd
print(f"\nUsing window: hwnd={hwnd} title={target.title!r}")

import win32gui
print(f"IsWindow: {win32gui.IsWindow(hwnd)}")
print(f"IsWindowVisible: {win32gui.IsWindowVisible(hwnd)}")
print(f"IsIconic (minimized): {win32gui.IsIconic(hwnd)}")
print(f"GetForegroundWindow before activate: {win32gui.GetForegroundWindow()}")

activated = wm.activate(hwnd)
print(f"activate() returned: {activated}")
print(f"GetForegroundWindow after activate: {win32gui.GetForegroundWindow()}")
print(f"IsIconic after activate: {win32gui.IsIconic(hwnd)}")

left, top, width, height = wm.get_client_rect(hwnd)
print(f"\nclient_rect: left={left} top={top} width={width} height={height}")
print(f"types: left={type(left).__name__} top={type(top).__name__} "
      f"width={type(width).__name__} height={type(height).__name__}")

for rule, step in drag_steps:
    print(f"\n--- Rule '{rule.name}' step '{step.name}' ---")
    print(f"params: {step.params}")
    for k, v in step.params.items():
        print(f"  {k}: {v!r} ({type(v).__name__})")

    from_point = resolve_relative_point(step.params, "from_relative_x", "from_relative_y", width, height)
    to_point = resolve_relative_point(step.params, "to_relative_x", "to_relative_y", width, height)
    print(f"resolved from_point (client-relative): {from_point}")
    print(f"resolved to_point (client-relative): {to_point}")

    if from_point is None or to_point is None:
        print("resolve_relative_point returned None — skipping SetCursorPos test")
        continue

    from_x, from_y = from_point
    to_x, to_y = to_point
    abs_from_x, abs_from_y = left + from_x, top + from_y
    abs_to_x, abs_to_y = left + to_x, top + to_y
    print(f"absolute from: ({abs_from_x}, {abs_from_y}) types: "
          f"({type(abs_from_x).__name__}, {type(abs_from_y).__name__})")
    print(f"absolute to: ({abs_to_x}, {abs_to_y}) types: "
          f"({type(abs_to_x).__name__}, {type(abs_to_y).__name__})")

    import win32api
    print("\nTrying win32api.SetCursorPos with a safe hardcoded point (500, 500)...")
    try:
        win32api.SetCursorPos((500, 500))
        print("  OK")
    except Exception as e:
        print(f"  FAILED: {e!r}")

    print(f"\nTrying win32api.SetCursorPos with resolved 'from' point ({abs_from_x}, {abs_from_y})...")
    try:
        win32api.SetCursorPos((abs_from_x, abs_from_y))
        print("  OK")
    except Exception as e:
        print(f"  FAILED: {e!r}")

    print(f"\nTrying win32api.SetCursorPos with resolved 'to' point ({abs_to_x}, {abs_to_y})...")
    try:
        win32api.SetCursorPos((abs_to_x, abs_to_y))
        print("  OK")
    except Exception as e:
        print(f"  FAILED: {e!r}")
