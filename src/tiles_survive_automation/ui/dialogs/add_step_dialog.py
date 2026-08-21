from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from tiles_survive_automation import config
from tiles_survive_automation.rules.models import RuleStep, StepType, StrategyType

ADDABLE_STEP_TYPES = (StepType.WAIT_FOR_IMAGE, StepType.WAIT_IMAGE_DISAPPEAR,
                      StepType.WAIT)


class AddStepDialog(QDialog):
    """Picks the type and the duration of a new step. Deliberately does not ask
    for a template: the picture is attached afterwards with the Rule Editor's
    Recapture button, which already knows how to wait for a click on the game.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add step")

        self.type_combo = QComboBox()
        for step_type in ADDABLE_STEP_TYPES:
            self.type_combo.addItem(step_type.value, userData=step_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 600_000)
        self.duration_spin.setSingleStep(100)
        self.duration_spin.setValue(config.WAIT_FOR_IMAGE_TIMEOUT_MS)

        self.duration_label = QLabel("Timeout (ms)")

        form = QFormLayout()
        form.addRow("Type", self.type_combo)
        form.addRow(self.duration_label, self.duration_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout()
        outer.addLayout(form)
        outer.addWidget(buttons)
        self.setLayout(outer)

    def _selected_type(self) -> StepType:
        return StepType(self.type_combo.currentData())

    def _on_type_changed(self, index: int) -> None:
        if index < 0:
            return
        is_plain_wait = self._selected_type() == StepType.WAIT
        self.duration_label.setText("Duration (ms)" if is_plain_wait
                                    else "Timeout (ms)")

    def build_step(self) -> RuleStep:
        step_type = self._selected_type()
        value = self.duration_spin.value()
        if step_type == StepType.WAIT:
            params = {"duration_ms": value}
        else:
            params = {"timeout_ms": value,
                      "poll_interval_ms": config.WAIT_POLL_INTERVAL_MS}
        # order_index is a placeholder: RuleEditorController.add_step reindexes
        # the whole draft once the step lands in the list.
        return RuleStep(
            id=None, order_index=0, step_type=step_type, name=step_type.value,
            enabled=True, params=params, template_path=None,
            confidence_threshold=config.DEFAULT_CONFIDENCE_THRESHOLD,
            strategy=StrategyType.VISUAL_ONLY, verification=None,
            screenshot_path=None, delay_after_ms=0,
        )
