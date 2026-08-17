"""Temporary diagnostic script — run via PyCharm's Run button.

Writes everything to cursor_diag_output.txt (in addition to stdout) so
the output can just be committed and pushed without copy-pasting the
console text.

Replicates the exact sequence PlaybackEngine.run() does inside its worker
thread: activate the game window, then immediately SetCursorPos to a
target point -- all from a background threading.Thread, to test whether
the failure is thread-context-dependent (main thread worked fine when
tested standalone; this reproduces the real call pattern).
"""
import threading
import time
import traceback
from pathlib import Path

OUTPUT_FILE = Path(__file__).resolve().parent / "cursor_diag_output.txt"
_lines: list[str] = []


def log(*args) -> None:
    line = " ".join(str(a) for a in args)
    print(line)
    _lines.append(line)


def main() -> None:
    import win32api
    from tiles_survive_automation.window.factory import get_window_manager

    TARGET_X, TARGET_Y = 955, 218

    def on_main_thread():
        log("[main thread] trying SetCursorPos...")
        try:
            win32api.SetCursorPos((TARGET_X, TARGET_Y))
            log("[main thread] OK")
        except Exception as e:
            log("[main thread] FAILED:", repr(e))

    def on_worker_thread_bare():
        log("[worker thread, no activation] trying SetCursorPos...")
        try:
            win32api.SetCursorPos((TARGET_X, TARGET_Y))
            log("[worker thread, no activation] OK")
        except Exception as e:
            log("[worker thread, no activation] FAILED:", repr(e))

    def on_worker_thread_after_activate(hwnd):
        wm = get_window_manager()
        log(f"[worker thread, after activate] activating hwnd={hwnd}...")
        activated = wm.activate(hwnd)
        log(f"[worker thread, after activate] activate() returned {activated}")
        log("[worker thread, after activate] trying SetCursorPos immediately...")
        try:
            win32api.SetCursorPos((TARGET_X, TARGET_Y))
            log("[worker thread, after activate] OK")
        except Exception as e:
            log("[worker thread, after activate] FAILED:", repr(e))

    on_main_thread()
    time.sleep(0.3)

    t1 = threading.Thread(target=on_worker_thread_bare)
    t1.start()
    t1.join()
    time.sleep(0.3)

    wm = get_window_manager()
    windows = wm.list_windows()
    log(f"\nFound {len(windows)} windows:")
    for w in windows[:20]:
        log(f"  hwnd={w.hwnd} title={w.title!r}")

    if windows:
        target = next((w for w in windows if "tile" in w.title.lower()), windows[0])
        log(f"\nUsing window: hwnd={target.hwnd} title={target.title!r}")
        t2 = threading.Thread(target=on_worker_thread_after_activate, args=(target.hwnd,))
        t2.start()
        t2.join()
    else:
        log("No windows found, skipping activate() test")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("SCRIPT CRASHED:")
        log(traceback.format_exc())
    finally:
        OUTPUT_FILE.write_text("\n".join(_lines) + "\n", encoding="utf-8")
        print(f"\nOutput written to {OUTPUT_FILE}")
