import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tiles_survive_automation.recorder.image_io import write_image
from tiles_survive_automation.recorder.template_capture import capture_template
from tiles_survive_automation.rules.models import StrategyType
from tiles_survive_automation.ui.controllers.rule_editor_controller import (
    RuleEditorController,
)

PREVIEW_SIZE = 160


class RuleEditorDialog(QDialog):
    def __init__(self, rule, rule_repository, window_manager, screen_capture,
                 input_recorder, playback_controller, templates_dir,
                 screenshots_dir, hwnd, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Rule — {rule.name}")
        self.controller = RuleEditorController(rule, rule_repository)
        self._window_manager = window_manager
        self._screen_capture = screen_capture
        self._input_recorder = input_recorder
        self._playback_controller = playback_controller
        self._templates_dir = Path(templates_dir)
        self._screenshots_dir = Path(screenshots_dir)
        self._hwnd = hwnd
        self._current_index: int | None = None
        self._awaiting_recapture = False
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(self._on_step_selected)

        up_button = QPushButton("Up")
        down_button = QPushButton("Down")
        delete_button = QPushButton("Delete")
        up_button.clicked.connect(self._on_up_clicked)
        down_button.clicked.connect(self._on_down_clicked)
        delete_button.clicked.connect(self._on_delete_clicked)

        list_buttons = QHBoxLayout()
        for button in (up_button, down_button, delete_button):
            list_buttons.addWidget(button)

        left = QVBoxLayout()
        left.addWidget(self.step_list)
        left.addLayout(list_buttons)
        left_widget = QWidget()
        left_widget.setLayout(left)

        self.name_edit = QLineEdit()
        self.enabled_check = QCheckBox()
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 600_000)
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.01)
        self.strategy_combo = QComboBox()
        for strategy in StrategyType:
            self.strategy_combo.addItem(strategy.value, userData=strategy)

        self.name_edit.editingFinished.connect(
            lambda: self._on_field_changed("name", self.name_edit.text()))
        self.enabled_check.toggled.connect(
            lambda value: self._on_field_changed("enabled", value))
        self.delay_spin.valueChanged.connect(
            lambda value: self._on_field_changed("delay_after_ms", value))
        self.confidence_spin.valueChanged.connect(
            lambda value: self._on_field_changed("confidence_threshold", value))
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Enabled", self.enabled_check)
        form.addRow("Delay after (ms)", self.delay_spin)
        form.addRow("Confidence threshold", self.confidence_spin)
        form.addRow("Strategy", self.strategy_combo)

        self.screenshot_preview = QLabel("No image")
        self.screenshot_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.screenshot_preview.setAlignment(Qt.AlignCenter)
        self.template_preview = QLabel("No image")
        self.template_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.template_preview.setAlignment(Qt.AlignCenter)

        previews = QHBoxLayout()
        previews.addWidget(self.screenshot_preview)
        previews.addWidget(self.template_preview)

        self.status_label = QLabel("")

        self.step_actions_layout = QHBoxLayout()

        self.recapture_button = QPushButton("Recapture")
        self.recapture_button.clicked.connect(self._on_recapture_clicked)
        self.step_actions_layout.addWidget(self.recapture_button)

        field_column = QVBoxLayout()
        field_column.addLayout(form)
        field_column.addLayout(previews)
        field_column.addLayout(self.step_actions_layout)
        field_column.addWidget(self.status_label)

        self.field_panel = QWidget()
        self.field_panel.setLayout(field_column)
        self.field_panel.setEnabled(False)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_save_clicked)
        self.buttons.rejected.connect(self.reject)

        split = QHBoxLayout()
        split.addWidget(left_widget)
        split.addWidget(self.field_panel)

        outer = QVBoxLayout()
        outer.addLayout(split)
        outer.addWidget(self.buttons)
        self.setLayout(outer)

    def _refresh_list(self) -> None:
        self.step_list.blockSignals(True)
        previous_row = self.step_list.currentRow()
        self.step_list.clear()
        for step in self.controller.draft.steps:
            self.step_list.addItem(f"{step.order_index}: {step.step_type.value} — {step.name}")
            if not step.enabled:
                self.step_list.item(self.step_list.count() - 1).setForeground(QColor(Qt.gray))
        self.step_list.blockSignals(False)

        row_count = self.step_list.count()
        if row_count == 0:
            self._current_index = None
            self.field_panel.setEnabled(False)
            return
        new_row = min(previous_row, row_count - 1) if previous_row >= 0 else 0
        self.step_list.setCurrentRow(new_row)

    def _on_step_selected(self, row: int) -> None:
        self._current_index = row if row >= 0 else None
        if self._current_index is None:
            self.field_panel.setEnabled(False)
            return
        self.field_panel.setEnabled(True)
        step = self.controller.draft.steps[self._current_index]
        for widget in (self.name_edit, self.enabled_check, self.delay_spin,
                       self.confidence_spin, self.strategy_combo):
            widget.blockSignals(True)
        self.name_edit.setText(step.name)
        self.enabled_check.setChecked(step.enabled)
        self.delay_spin.setValue(step.delay_after_ms)
        self.confidence_spin.setValue(step.confidence_threshold)
        self.strategy_combo.setCurrentIndex(self.strategy_combo.findData(step.strategy))
        for widget in (self.name_edit, self.enabled_check, self.delay_spin,
                       self.confidence_spin, self.strategy_combo):
            widget.blockSignals(False)
        self._refresh_previews(step)
        self.status_label.setText("")

    def _refresh_previews(self, step) -> None:
        self._set_preview(self.screenshot_preview,
                          Path(step.screenshot_path) if step.screenshot_path else None)
        self._set_preview(self.template_preview,
                          self._templates_dir / step.template_path
                          if step.template_path else None)

    def _set_preview(self, label: QLabel, path: Path | None) -> None:
        if path is None or not path.exists():
            label.setText("No image")
            return
        pixmap = QPixmap(str(path))
        label.setPixmap(pixmap.scaled(PREVIEW_SIZE, PREVIEW_SIZE, Qt.KeepAspectRatio))

    def _on_strategy_changed(self, index: int) -> None:
        if index < 0:
            return
        self._on_field_changed("strategy", StrategyType(self.strategy_combo.itemData(index)))

    def _on_field_changed(self, field: str, value) -> None:
        if self._current_index is None:
            return
        self.controller.update_step(self._current_index, **{field: value})
        if field in ("name", "enabled"):
            self._refresh_list()

    def _on_up_clicked(self) -> None:
        if self._current_index is None:
            return
        index = self._current_index
        self.controller.move_up(index)
        self._refresh_list()
        self.step_list.setCurrentRow(max(index - 1, 0))

    def _on_down_clicked(self) -> None:
        if self._current_index is None:
            return
        index = self._current_index
        self.controller.move_down(index)
        self._refresh_list()
        self.step_list.setCurrentRow(min(index + 1, self.step_list.count() - 1))

    def _on_delete_clicked(self) -> None:
        if self._current_index is None:
            return
        self.controller.delete_step(self._current_index)
        self._refresh_list()

    def _on_save_clicked(self) -> None:
        self.controller.save()
        self.accept()

    def _on_recapture_clicked(self) -> None:
        if self._current_index is None or self._hwnd is None:
            return
        self._awaiting_recapture = True
        self._set_controls_enabled(False)
        self.status_label.setText("Click on the game window now… (Esc to cancel)")
        self._window_manager.activate(self._hwnd)
        self._recapture_session_id = uuid.uuid4().hex[:8]
        self._input_recorder.start(on_event=self._on_recapture_event)

    def _on_recapture_event(self, event) -> None:
        QTimer.singleShot(0, lambda: self._handle_recapture_event(event))

    def _handle_recapture_event(self, event) -> None:
        if not self._awaiting_recapture:
            return
        if event.kind != "mouse_down" or event.x is None or event.y is None:
            return
        left, top, width, height = self._window_manager.get_client_rect(self._hwnd)
        client_x, client_y = event.x - left, event.y - top
        if not (0 <= client_x < width and 0 <= client_y < height):
            return

        self._input_recorder.stop()
        frame = self._screen_capture.grab((left, top, width, height))

        screenshot_dir = self._screenshots_dir / self._recapture_session_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / "recapture.png"
        write_image(screenshot_path, frame)

        template = capture_template(frame, client_x, client_y)
        template_dir = self._templates_dir / self._recapture_session_id
        template_dir.mkdir(parents=True, exist_ok=True)
        write_image(template_dir / "recapture.png", template)

        self.controller.update_step(
            self._current_index,
            template_path=f"{self._recapture_session_id}/recapture.png",
            screenshot_path=str(screenshot_path),
        )
        self._awaiting_recapture = False
        self._on_step_selected(self._current_index)
        self.status_label.setText("Template recaptured.")
        self._set_controls_enabled(True)

    def _cancel_recapture(self) -> None:
        self._input_recorder.stop()
        self._awaiting_recapture = False
        self.status_label.setText("Recapture cancelled.")
        self._set_controls_enabled(True)

    def keyPressEvent(self, event) -> None:
        if self._awaiting_recapture and event.key() == Qt.Key_Escape:
            self._cancel_recapture()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._awaiting_recapture:
            self._input_recorder.stop()
        super().closeEvent(event)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.step_list.setEnabled(enabled)
        self.field_panel.setEnabled(enabled and self._current_index is not None)
        self.buttons.setEnabled(enabled)
