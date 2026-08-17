import logging
from pathlib import Path

_LOGGER_NAME = "tiles_survive_automation.execution"


class _RuleNameFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "rule_name"):
            record.rule_name = "-"
        return True


def get_execution_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if not any(isinstance(f, _RuleNameFilter) for f in logger.filters):
        logger.addFilter(_RuleNameFilter())

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter("%(asctime)s [%(rule_name)s] %(message)s",
                                   datefmt="%H:%M:%S")

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
