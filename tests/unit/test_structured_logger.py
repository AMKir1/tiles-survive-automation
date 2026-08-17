import logging

from tiles_survive_automation.app_logging.structured_logger import get_execution_logger


def test_logger_writes_formatted_line_to_file(tmp_path):
    log_file = tmp_path / "execution.log"
    logger = get_execution_logger(log_file)

    logger.info("Step 1 Alliance found confidence=0.94",
                extra={"rule_name": "Alliance Help"})
    for handler in logger.handlers:
        handler.flush()

    content = log_file.read_text()

    assert "[Alliance Help]" in content
    assert "Step 1 Alliance found confidence=0.94" in content


def test_get_execution_logger_returns_same_named_logger_without_duplicate_handlers(tmp_path):
    log_file = tmp_path / "execution.log"

    logger_a = get_execution_logger(log_file)
    logger_b = get_execution_logger(log_file)

    assert logger_a is logger_b
    assert len(logger_a.handlers) == 2  # file + console, not duplicated


def test_get_execution_logger_reconfigures_to_new_path_on_later_call(tmp_path):
    first_log_file = tmp_path / "first" / "execution.log"
    second_log_file = tmp_path / "second" / "execution.log"

    get_execution_logger(first_log_file)
    logger = get_execution_logger(second_log_file)

    logger.info("after reconfigure", extra={"rule_name": "R"})
    for handler in logger.handlers:
        handler.flush()

    assert "after reconfigure" in second_log_file.read_text()
    assert len(logger.handlers) == 2
