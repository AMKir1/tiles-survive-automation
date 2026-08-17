import sqlite3
from importlib import resources
from pathlib import Path


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    # check_same_thread=False: PlaybackController runs PlaybackEngine.run() (which
    # writes via ExecutionRepository) on a worker thread while this connection is
    # created on the Qt main thread. This is an MVP1-scoped pragmatic fix, not a
    # full connection-per-thread redesign -- acceptable because Task 20's Play
    # re-entrancy guard ensures only one playback runs at a time, so the app's
    # actual usage pattern serializes DB access in practice even though SQLite
    # itself won't enforce it.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    schema_sql = (
        resources.files("tiles_survive_automation.storage")
        .joinpath("schema.sql")
        .read_text()
    )
    conn.executescript(schema_sql)
    return conn
