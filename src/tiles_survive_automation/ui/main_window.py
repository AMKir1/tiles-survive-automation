from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
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
from tiles_survive_automation.ui.controllers.manual_click_bridge import (
    ManualClickBridge,
)
from tiles_survive_automation.ui.controllers.playback_controller import (
    PlaybackController,
)
from tiles_survive_automation.ui.controllers.recorder_controller import (
    RecorderController,
)
from tiles_survive_automation.ui.controllers.schedule_controller import (
    ScheduleController,
)
from tiles_survive_automation.ui.dialogs.rule_editor_dialog import RuleEditorDialog


class MainWindow(QMainWindow):
    def __init__(self, window_manager, screen_capture, input_recorder,
                 input_controller, manual_click_watcher, rule_repository,
                 execution_repository, logger, templates_dir, screenshots_dir,
                 start_emergency_stop: bool = True,
                 start_manual_click_watcher: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Tiles Survive Automation")

        self._window_manager = window_manager
        self._rule_repository = rule_repository
        self._templates_dir = templates_dir
        self._logger = logger
        self._screen_capture = screen_capture
        self._input_recorder = input_recorder
        self._screenshots_dir = screenshots_dir

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

        self._schedule_controller = ScheduleController(self._playback_controller)
        self._schedule_controller.progress.connect(self._on_schedule_progress)
        self._schedule_controller.finished.connect(self._on_schedule_finished)

        # Wired to abort the current run AND halt any active schedule (not a
        # no-op) so F9 actually interrupts everything in flight, per spec
        # section 10 -- including a schedule sitting in its inter-batch pause,
        # where there's no in-progress run for abort() alone to catch.
        self._emergency_stop = EmergencyStop(input_controller,
                                              on_trigger=self._on_emergency_stop_triggered,
                                              hotkey=config.EMERGENCY_STOP_KEY)
        if start_emergency_stop:
            self._emergency_stop.start()

        # Lets the user reclaim control from a running Rule/Schedule by
        # clicking, not only via F9 -- the watcher ignores our own
        # synthetic clicks (see win32_manual_click_watcher.py). The watcher
        # callback may run on a raw background thread, so it's routed
        # through a Signal (safe from any thread) rather than calling
        # _on_manual_click_detected directly, which touches log_view.
        self._manual_click_watcher = manual_click_watcher
        self._manual_click_bridge = ManualClickBridge()
        self._manual_click_bridge.detected.connect(self._on_manual_click_detected)
        if start_manual_click_watcher:
            self._manual_click_watcher.start(self._manual_click_bridge.detected.emit)

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
        self._play_button = QPushButton("Play")
        self._schedule_button = QPushButton("Schedule")

        record_button.clicked.connect(self._on_record_clicked)
        pause_button.clicked.connect(self._recorder_controller.pause)
        stop_button.clicked.connect(self._recorder_controller.stop)
        self._play_button.clicked.connect(self._on_play_clicked)
        self._schedule_button.clicked.connect(self._on_schedule_clicked)

        buttons = QHBoxLayout()
        for button in (record_button, pause_button, stop_button, self._play_button,
                       self._schedule_button):
            buttons.addWidget(button)

        rename_button = QPushButton("Rename")
        delete_button = QPushButton("Delete")
        self._edit_button = QPushButton("Edit")
        rename_button.clicked.connect(self._on_rename_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)

        rule_buttons = QHBoxLayout()
        rule_buttons.addWidget(rename_button)
        rule_buttons.addWidget(delete_button)
        rule_buttons.addWidget(self._edit_button)

        # The window list is a snapshot taken at startup; with no way to
        # re-enumerate, restarting the game (or launching this app first) left
        # the combo pointing at a window that never was the game -- which
        # silently broke both Record and Play, with no visible reason.
        self._refresh_windows_button = QPushButton("Refresh windows")
        self._refresh_windows_button.clicked.connect(self._refresh_windows)

        window_row = QHBoxLayout()
        window_row.addWidget(self.window_combo, stretch=1)
        window_row.addWidget(self._refresh_windows_button)

        layout = QVBoxLayout()
        layout.addLayout(window_row)
        layout.addLayout(buttons)
        layout.addWidget(self.rule_list)
        layout.addLayout(rule_buttons)
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _refresh_windows(self) -> None:
        # Keep whatever the user picked: re-enumerating must not silently move
        # the selection to an unrelated window.
        previous_hwnd = self.window_combo.currentData()
        self.window_combo.clear()
        for info in self._window_manager.list_windows():
            self.window_combo.addItem(info.title, userData=info.hwnd)

        if previous_hwnd is not None:
            index = self.window_combo.findData(previous_hwnd)
            if index >= 0:
                self.window_combo.setCurrentIndex(index)

    def _refresh_rules(self) -> None:
        # Rebuilding the list resets currentRow to -1, which made _selected_rule()
        # return None and every subsequent Play/Schedule silently do nothing.
        previous_name = None
        if self.rule_list.currentRow() >= 0:
            previous_name = self.rule_list.currentItem().text()

        self.rule_list.clear()
        for rule in self._rule_repository.list_all():
            self.rule_list.addItem(rule.name)

        if previous_name is not None:
            matches = self.rule_list.findItems(previous_name, Qt.MatchExactly)
            if matches:
                self.rule_list.setCurrentRow(self.rule_list.row(matches[0]))

    def _current_hwnd(self) -> int | None:
        return self.window_combo.currentData()

    def _selected_rule(self):
        selected = self.rule_list.currentRow()
        if selected < 0:
            return None
        return self._rule_repository.list_all()[selected]

    def _require_target(self, hwnd, rule) -> bool:
        """Both Play and Schedule used to return silently when either half of
        the target was missing, which is indistinguishable from a dead button."""
        if hwnd is None:
            self._log("No game window selected - pick the game in the list above "
                      "(Refresh windows if it is not there).")
            return False
        if rule is None:
            self._log("No rule selected - click one in the list first.")
            return False
        return True

    def _set_running_buttons_enabled(self, enabled: bool) -> None:
        self._play_button.setEnabled(enabled)
        self._schedule_button.setEnabled(enabled)

    def _on_record_clicked(self) -> None:
        hwnd = self._current_hwnd()
        if hwnd is None:
            self._log("No game window selected - pick the game in the list above "
                      "(Refresh windows if it is not there).")
            return
        self._log(f"Recording into window: {self.window_combo.currentText()}")
        self._recorder_controller.start(hwnd)

    def _on_recording_stopped(self, steps) -> None:
        self._pending_recorded_steps = steps
        if not steps:
            # Every event outside the selected window's client rect is dropped,
            # so picking the wrong window yields zero steps and nothing to save.
            self._log(f"Recording stopped: 0 steps captured. Events are only kept "
                      f"inside the selected window "
                      f"({self.window_combo.currentText()!r}) - is that the game?")
            return
        name, ok = QInputDialog.getText(self, "Save Rule", "Rule name:")
        if not ok or not name:
            return
        rule = RuleBuilder(name, window_title_hint=self.window_combo.currentText()).build(steps)
        self._rule_repository.save(rule)
        self._refresh_rules()

    def _on_play_clicked(self) -> None:
        hwnd = self._current_hwnd()
        rule = self._selected_rule()
        if not self._require_target(hwnd, rule):
            return
        # Guard against re-entrancy: two overlapping Play/Schedule runs would
        # spawn two threads sharing one PlaybackEngine/_result_holder, and the
        # second run's `finished` would never fire since the QTimer poll
        # already stopped after the first result.
        self._set_running_buttons_enabled(False)
        self._playback_controller.run_async(rule, hwnd)

    def _on_playback_finished(self, context) -> None:
        if self._schedule_controller.is_active():
            # This run is part of an active schedule; ScheduleController's own
            # progress/finished signals handle logging and button state.
            return
        self._set_running_buttons_enabled(True)
        if context.state == PlaybackState.COMPLETED:
            self.log_view.appendPlainText("Rule completed")
        elif context.state == PlaybackState.FAILED:
            self.log_view.appendPlainText(f"Rule failed: {context.error_message}")
        else:
            self.log_view.appendPlainText("Rule stopped")

    def _on_schedule_clicked(self) -> None:
        hwnd = self._current_hwnd()
        rule = self._selected_rule()
        if not self._require_target(hwnd, rule):
            return

        total_runs, ok = QInputDialog.getInt(self, "Schedule", "Total runs:", 100, 1, 100000)
        if not ok:
            return
        batch_size, ok = QInputDialog.getInt(self, "Schedule", "Batch size:", 5, 1, total_runs)
        if not ok:
            return
        interval_minutes, ok = QInputDialog.getInt(
            self, "Schedule", "Pause between batches (minutes):", 2, 0, 1440)
        if not ok:
            return

        self._set_running_buttons_enabled(False)
        self._schedule_controller.start(rule, hwnd, total_runs, batch_size,
                                          interval_minutes * 60_000)

    def _on_schedule_progress(self, completed: int, total: int, batch_index: int,
                                batch_count: int) -> None:
        self.log_view.appendPlainText(
            f"Schedule: batch {batch_index}/{batch_count}, run {completed}/{total}")

    def _on_schedule_finished(self, reason: str) -> None:
        self._set_running_buttons_enabled(True)
        self.log_view.appendPlainText(f"Schedule {reason}")

    def _on_emergency_stop_triggered(self) -> None:
        self._playback_controller.abort()
        self._schedule_controller.stop()

    def _on_manual_click_detected(self) -> None:
        if self._play_button.isEnabled():
            return  # no Rule/Schedule currently running -- ignore
        self.log_view.appendPlainText("Manual click detected — run aborted")
        self._on_emergency_stop_triggered()

    def _on_rename_clicked(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        new_name, ok = QInputDialog.getText(self, "Rename Rule", "New name:", text=rule.name)
        if not ok or not new_name:
            return
        rule.name = new_name
        self._rule_repository.save(rule)
        self._refresh_rules()

    def _on_delete_clicked(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        confirm = QMessageBox.question(
            self, "Delete Rule", f"Delete rule '{rule.name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._rule_repository.delete(rule.id)
        self._refresh_rules()

    def _on_edit_clicked(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        dialog = RuleEditorDialog(
            rule, self._rule_repository,
            window_manager=self._window_manager,
            screen_capture=self._screen_capture,
            input_recorder=self._input_recorder,
            playback_controller=self._playback_controller,
            templates_dir=self._templates_dir,
            screenshots_dir=self._screenshots_dir,
            hwnd=self._current_hwnd(),
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self._refresh_rules()
