import sys

from PySide6.QtWidgets import QApplication


def main() -> None:
    from tiles_survive_automation import config
    from tiles_survive_automation.app_logging.structured_logger import (
        get_execution_logger,
    )
    from tiles_survive_automation.capture.factory import get_screen_capture
    from tiles_survive_automation.storage.database import connect
    from tiles_survive_automation.storage.execution_repository import (
        ExecutionRepository,
    )
    from tiles_survive_automation.storage.rule_repository import RuleRepository
    from tiles_survive_automation.ui.main_window import MainWindow
    from tiles_survive_automation.window.factory import get_window_manager

    config.ensure_data_dirs()

    window_manager = get_window_manager()
    screen_capture = get_screen_capture()
    conn = connect(config.DATABASE_PATH)
    rule_repository = RuleRepository(conn)
    execution_repository = ExecutionRepository(conn)
    logger = get_execution_logger(config.LOGS_DIR / "execution.log")

    if sys.platform == "win32":
        from tiles_survive_automation.input.pynput_recorder import PynputRecorder
        from tiles_survive_automation.input.win32_input_controller import (
            Win32InputController,
        )

        input_recorder = PynputRecorder()
        input_controller = Win32InputController()
    else:
        from tiles_survive_automation.input.fake_input import FakeInputController

        class _NoOpRecorder:
            def start(self, on_event):
                pass

            def pause(self):
                pass

            def resume(self):
                pass

            def stop(self):
                return []

        input_recorder = _NoOpRecorder()
        input_controller = FakeInputController()

    app = QApplication(sys.argv)
    window = MainWindow(window_manager, screen_capture, input_recorder,
                          input_controller, rule_repository, execution_repository,
                          logger, config.TEMPLATES_DIR, config.SCREENSHOTS_DIR)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
