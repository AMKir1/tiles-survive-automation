from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tiles_survive_automation import config
from tiles_survive_automation.input.emergency_stop import EmergencyStop
from tiles_survive_automation.playback.engine import PlaybackEngine
from tiles_survive_automation.playback.state import PlaybackState
from tiles_survive_automation.recorder.recording_session import RecordingSession
from tiles_survive_automation.rules.rule_builder import RuleBuilder
from tiles_survive_automation.ui.controllers.playback_controller import (
    PlaybackController,
)
from tiles_survive_automation.ui.controllers.recorder_controller import (
    RecorderController,
)


class MainWindow(QMainWindow):
    def __init__(self, window_manager, screen_capture, input_recorder,
                 input_controller, rule_repository, execution_repository, logger,
                 templates_dir, screenshots_dir, start_emergency_stop: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Tiles Survive Automation")

        self._window_manager = window_manager
        self._rule_repository = rule_repository
        self._templates_dir = templates_dir
        self._logger = logger

        recording_session = RecordingSession(window_manager, screen_capture,
                                              input_recorder, templates_dir,
                                              screenshots_dir)
        self._recorder_controller = RecorderController(recording_session)
        self._recorder_controller.stopped.connect(self._on_recording_stopped)

        playback_engine = PlaybackEngine(window_manager, screen_capture,
                                           input_controller, execution_repository,
                                           logger, templates_dir)
        self._playback_controller = PlaybackController(playback_engine)
        self._playback_controller.finished.connect(self._on_playback_finished)

        # Wired to playback_controller.abort (not a no-op) so F9 actually
        # interrupts the currently running rule, per spec section 10.
        self._emergency_stop = EmergencyStop(input_controller,
                                              on_trigger=self._playback_controller.abort,
                                              hotkey=config.EMERGENCY_STOP_KEY)
        if start_emergency_stop:
            self._emergency_stop.start()

        self._pending_recorded_steps = []
        self._build_ui()
        self._refresh_windows()
        self._refresh_rules()

    def _build_ui(self) -> None:
        self.window_combo = QComboBox()
        self.rule_list = QListWidget()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        record_button = QPushButton("Record")
        pause_button = QPushButton("Pause")
        stop_button = QPushButton("Stop")
        play_button = QPushButton("Play")

        record_button.clicked.connect(self._on_record_clicked)
        pause_button.clicked.connect(self._recorder_controller.pause)
        stop_button.clicked.connect(self._recorder_controller.stop)
        play_button.clicked.connect(self._on_play_clicked)

        buttons = QHBoxLayout()
        for button in (record_button, pause_button, stop_button, play_button):
            buttons.addWidget(button)

        layout = QVBoxLayout()
        layout.addWidget(self.window_combo)
        layout.addLayout(buttons)
        layout.addWidget(self.rule_list)
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def _refresh_windows(self) -> None:
        self.window_combo.clear()
        for info in self._window_manager.list_windows():
            self.window_combo.addItem(info.title, userData=info.hwnd)

    def _refresh_rules(self) -> None:
        self.rule_list.clear()
        for rule in self._rule_repository.list_all():
            self.rule_list.addItem(rule.name)

    def _current_hwnd(self) -> int | None:
        return self.window_combo.currentData()

    def _on_record_clicked(self) -> None:
        hwnd = self._current_hwnd()
        if hwnd is not None:
            self._recorder_controller.start(hwnd)

    def _on_recording_stopped(self, steps) -> None:
        self._pending_recorded_steps = steps
        if not steps:
            return
        name, ok = QInputDialog.getText(self, "Save Rule", "Rule name:")
        if not ok or not name:
            return
        rule = RuleBuilder(name, window_title_hint=self.window_combo.currentText()).build(steps)
        self._rule_repository.save(rule)
        self._refresh_rules()

    def _on_play_clicked(self) -> None:
        hwnd = self._current_hwnd()
        selected = self.rule_list.currentRow()
        if hwnd is None or selected < 0:
            return
        rule = self._rule_repository.list_all()[selected]
        self._playback_controller.run_async(rule, hwnd)

    def _on_playback_finished(self, context) -> None:
        if context.state == PlaybackState.COMPLETED:
            self.log_view.appendPlainText("Rule completed")
        elif context.state == PlaybackState.FAILED:
            self.log_view.appendPlainText(f"Rule failed: {context.error_message}")
        else:
            self.log_view.appendPlainText("Rule stopped")
