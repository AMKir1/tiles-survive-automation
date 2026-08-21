from tiles_survive_automation.rules.models import StepType, StrategyType
from tiles_survive_automation.ui.dialogs.add_step_dialog import AddStepDialog


def _dialog(qtbot):
    dialog = AddStepDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_offers_exactly_the_three_step_types_a_user_can_add(qtbot):
    dialog = _dialog(qtbot)

    types = [dialog.type_combo.itemData(i) for i in range(dialog.type_combo.count())]

    assert types == [StepType.WAIT_FOR_IMAGE, StepType.WAIT_IMAGE_DISAPPEAR,
                     StepType.WAIT]


def test_builds_a_wait_for_image_step_with_timeout_and_poll_interval(qtbot):
    dialog = _dialog(qtbot)
    dialog.type_combo.setCurrentIndex(
        dialog.type_combo.findData(StepType.WAIT_FOR_IMAGE))
    dialog.duration_spin.setValue(4000)

    step = dialog.build_step()

    assert step.step_type == StepType.WAIT_FOR_IMAGE
    assert step.params["timeout_ms"] == 4000
    assert step.params["poll_interval_ms"] > 0
    assert step.template_path is None       # attached later via Recapture
    assert step.strategy == StrategyType.VISUAL_ONLY
    assert step.enabled is True
    assert step.id is None


def test_builds_a_plain_wait_step_with_a_duration(qtbot):
    dialog = _dialog(qtbot)
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(StepType.WAIT))
    dialog.duration_spin.setValue(1500)

    step = dialog.build_step()

    assert step.step_type == StepType.WAIT
    assert step.params == {"duration_ms": 1500}


def test_duration_label_follows_the_selected_type(qtbot):
    dialog = _dialog(qtbot)

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(StepType.WAIT))
    assert "Duration" in dialog.duration_label.text()

    dialog.type_combo.setCurrentIndex(
        dialog.type_combo.findData(StepType.WAIT_IMAGE_DISAPPEAR))
    assert "Timeout" in dialog.duration_label.text()


def test_generated_name_describes_the_step_type(qtbot):
    dialog = _dialog(qtbot)
    dialog.type_combo.setCurrentIndex(
        dialog.type_combo.findData(StepType.WAIT_IMAGE_DISAPPEAR))

    assert dialog.build_step().name == "WaitImageDisappear"
