"""Temporary diagnostic script — run via PyCharm's Run button.

Replicates the exact sequence PlaybackEngine.run() does inside its worker
thread: activate the game window, then immediately SetCursorPos to a
target point -- all from a background threading.Thread, to test whether
the failure is thread-context-dependent (main thread worked fine when
tested standalone; this reproduces the real call pattern).
"""
import threading
import time

import win32api

from tiles_survive_automation.window.factory import get_window_manager

TARGET_X, TARGET_Y = 955, 218


def on_main_thread():
    print("[main thread] trying SetCursorPos...")
    try:
        win32api.SetCursorPos((TARGET_X, TARGET_Y))
        print("[main thread] OK")
    except Exception as e:
        print("[main thread] FAILED:", repr(e))


def on_worker_thread_bare():
    print("[worker thread, no activation] trying SetCursorPos...")
    try:
        win32api.SetCursorPos((TARGET_X, TARGET_Y))
        print("[worker thread, no activation] OK")
    except Exception as e:
        print("[worker thread, no activation] FAILED:", repr(e))


def on_worker_thread_after_activate(hwnd):
    wm = get_window_manager()
    print(f"[worker thread, after activate] activating hwnd={hwnd}...")
    activated = wm.activate(hwnd)
    print(f"[worker thread, after activate] activate() returned {activated}")
    print("[worker thread, after activate] trying SetCursorPos immediately...")
    try:
        win32api.SetCursorPos((TARGET_X, TARGET_Y))
        print("[worker thread, after activate] OK")
    except Exception as e:
        print("[worker thread, after activate] FAILED:", repr(e))


if __name__ == "__main__":
    on_main_thread()
    time.sleep(0.3)

    t1 = threading.Thread(target=on_worker_thread_bare)
    t1.start()
    t1.join()
    time.sleep(0.3)

    wm = get_window_manager()
    windows = wm.list_windows()
    print(f"\nFound {len(windows)} windows:")
    for w in windows[:20]:
        print(f"  hwnd={w.hwnd} title={w.title!r}")

    if windows:
        # Prefer a window whose title looks like the game, else just use the first one.
        target = next((w for w in windows if "tile" in w.title.lower()), windows[0])
        print(f"\nUsing window: hwnd={target.hwnd} title={target.title!r}")
        t2 = threading.Thread(target=on_worker_thread_after_activate, args=(target.hwnd,))
        t2.start()
        t2.join()
    else:
        print("No windows found, skipping activate() test")
