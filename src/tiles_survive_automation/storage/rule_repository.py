import sqlite3
from datetime import datetime, timezone

from tiles_survive_automation.rules.models import Rule, RuleStep


class RuleRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, rule: Rule) -> Rule:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            if rule.id is None:
                cursor = self._conn.execute(
                    "INSERT INTO Rule (name, description, window_title_hint, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (rule.name, rule.description, rule.window_title_hint, now, now),
                )
                rule_id = cursor.lastrowid
            else:
                rule_id = rule.id
                self._conn.execute(
                    "UPDATE Rule SET name=?, description=?, window_title_hint=?, "
                    "updated_at=? WHERE id=?",
                    (rule.name, rule.description, rule.window_title_hint, now, rule_id),
                )
                self._conn.execute("DELETE FROM RuleStep WHERE rule_id=?", (rule_id,))

            saved_steps: list[RuleStep] = []
            for index, step in enumerate(rule.steps):
                row = step.to_row()
                cursor = self._conn.execute(
                    "INSERT INTO RuleStep (rule_id, order_index, step_type, name, "
                    "enabled, params_json, template_path, confidence_threshold, "
                    "strategy, verification_json, screenshot_path, delay_after_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rule_id, index, row["step_type"], row["name"], row["enabled"],
                        row["params_json"], row["template_path"],
                        row["confidence_threshold"], row["strategy"],
                        row["verification_json"], row["screenshot_path"],
                        row["delay_after_ms"],
                    ),
                )
                saved_steps.append(replace_id(step, cursor.lastrowid, index))

        return Rule(id=rule_id, name=rule.name, description=rule.description,
                    window_title_hint=rule.window_title_hint, steps=saved_steps)

    def get(self, rule_id: int) -> Rule | None:
        row = self._conn.execute(
            "SELECT * FROM Rule WHERE id=?", (rule_id,)
        ).fetchone()
        if row is None:
            return None

        step_rows = self._conn.execute(
            "SELECT * FROM RuleStep WHERE rule_id=? ORDER BY order_index",
            (rule_id,),
        ).fetchall()
        steps = [RuleStep.from_row(dict(r)) for r in step_rows]

        return Rule(id=row["id"], name=row["name"], description=row["description"],
                    window_title_hint=row["window_title_hint"], steps=steps)

    def list_all(self) -> list[Rule]:
        ids = [r["id"] for r in self._conn.execute("SELECT id FROM Rule")]
        return [self.get(rule_id) for rule_id in ids]

    def delete(self, rule_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM Rule WHERE id=?", (rule_id,))


def replace_id(step: RuleStep, new_id: int, new_order_index: int) -> RuleStep:
    from dataclasses import replace as dataclass_replace

    return dataclass_replace(step, id=new_id, order_index=new_order_index)
