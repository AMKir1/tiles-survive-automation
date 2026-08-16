import sqlite3
from importlib import resources
from pathlib import Path


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
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
