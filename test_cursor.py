"""Temporary diagnostic script — run via PyCharm's Run button (or
`uv run python test_cursor.py`). Compares raw ctypes SetCursorPos against
win32api.SetCursorPos to isolate whether the pywin32 wrapper itself is
the source of the 'No error message is available' failure."""
import time
import ctypes
import win32api

result = ctypes.windll.user32.SetCursorPos(955, 218)
print("ctypes result:", result)

time.sleep(0.5)

try:
    win32api.SetCursorPos((955, 218))
    print("win32api: OK")
except Exception as e:
    print("win32api FAILED:", repr(e))
