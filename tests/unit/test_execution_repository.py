from tiles_survive_automation.storage.database import connect
from tiles_survive_automation.storage.execution_repository import ExecutionRepository


def test_start_finish_and_log_step_round_trip():
    conn = connect(":memory:")
    repo = ExecutionRepository(conn)

    execution_id = repo.start_execution(target_type="RULE", target_id=1)
    repo.log_step(execution_id, rule_id=1, rule_step_id=1, description="Click -> Alliance",
                   matched_template="click_1.png", confidence=0.94, x=842, y=612,
                   result="SUCCESS", error_message=None)
    repo.finish_execution(execution_id, status="SUCCESS", error_message=None)

    execution = conn.execute("SELECT * FROM Execution WHERE id=?", (execution_id,)).fetchone()
    steps = conn.execute("SELECT * FROM ExecutionStep WHERE execution_id=?",
                          (execution_id,)).fetchall()

    assert execution["status"] == "SUCCESS"
    assert execution["finished_at"] is not None
    assert len(steps) == 1
    assert steps[0]["confidence"] == 0.94
