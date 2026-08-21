from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from tiles_survive_automation.rules.models import Rule


class RuleEditorController:
    def __init__(self, rule: Rule, rule_repository) -> None:
        self._draft = deepcopy(rule)
        self._rule_repository = rule_repository

    @property
    def draft(self) -> Rule:
        return self._draft

    def move_up(self, index: int) -> None:
        if index <= 0 or index >= len(self._draft.steps):
            return
        self._swap(index, index - 1)

    def move_down(self, index: int) -> None:
        if index < 0 or index >= len(self._draft.steps) - 1:
            return
        self._swap(index, index + 1)

    def delete_step(self, index: int) -> None:
        if index < 0 or index >= len(self._draft.steps):
            return
        del self._draft.steps[index]
        self._reindex()

    def update_step(self, index: int, **fields) -> None:
        step = self._draft.steps[index]
        self._draft.steps[index] = replace(step, **fields)

    def draft_from(self, index: int) -> Rule:
        return replace(self._draft, steps=list(self._draft.steps[index:]))

    def save(self) -> Rule:
        self._draft = self._rule_repository.save(self._draft)
        return self._draft

    def _swap(self, i: int, j: int) -> None:
        steps = self._draft.steps
        steps[i], steps[j] = steps[j], steps[i]
        self._reindex()

    def _reindex(self) -> None:
        for i, step in enumerate(self._draft.steps):
            self._draft.steps[i] = replace(step, order_index=i)
