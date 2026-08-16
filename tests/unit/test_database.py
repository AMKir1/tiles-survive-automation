# tests/unit/test_database.py
from tiles_survive_automation.storage import database


def test_connect_creates_all_mvp1_tables():
    conn = database.connect(":memory:")

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    assert {"Rule", "RuleStep", "Execution", "ExecutionStep"} <= tables


def test_connect_enables_foreign_keys():
    conn = database.connect(":memory:")

    (fk_enabled,) = conn.execute("PRAGMA foreign_keys").fetchone()

    assert fk_enabled == 1
