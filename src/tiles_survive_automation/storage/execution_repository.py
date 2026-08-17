import sqlite3
from datetime import datetime, timezone


class ExecutionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def start_execution(self, target_type: str, target_id: int) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO Execution (started_at, target_type, target_id, status) "
                "VALUES (?, ?, ?, ?)",
                (now, target_type, target_id, "RUNNING"),
            )
        return cursor.lastrowid

    def finish_execution(self, execution_id: int, status: str,
                           error_message: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                "UPDATE Execution SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, now, error_message, execution_id),
            )

    def log_step(self, execution_id: int, rule_id: int, rule_step_id: int,
                  description: str, matched_template: str | None,
                  confidence: float | None, x: int | None, y: int | None,
                  result: str, error_message: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO ExecutionStep (execution_id, rule_id, rule_step_id, "
                "timestamp, description, matched_template, confidence, x, y, result, "
                "error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (execution_id, rule_id, rule_step_id, now, description, matched_template,
                 confidence, x, y, result, error_message),
            )
