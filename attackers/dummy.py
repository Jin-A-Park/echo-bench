"""Baseline: append the goal verbatim to every slot. Ignores history.
For BIPIA this reproduces poisoned_context (position=end); for InjecAgent, the base setting."""
from __future__ import annotations

from .base import Attacker


# TODO(attacker): placeholder baseline (ignores history); the real attacker goes in its own file
class DummyAttacker(Attacker):
    def attack(self, source, goal, history):
        return {k: (f"{v}\n{goal}" if v else goal) for k, v in source.items()}
