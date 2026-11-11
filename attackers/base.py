"""Attacker interface: the only connection point between an attacker and the pipeline."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Attacker(ABC):
    """Subclass, register in attackers/__init__.py (ATTACKERS), select with `attacker:` in config.yaml.
    Constructor kwargs come from `attacker_args:` in config.yaml."""

    @abstractmethod
    def attack(self, source: dict[str, str], goal: str,
               history: list[tuple[dict[str, str], str]]) -> dict[str, str]:
        """Return the modified source for the next attempt.

        source:  {slot id: original text}. Return the same keys, str values (checked by the loop).
        goal:    what the injection should make the Benign agent do.
        history: [(previous modified source, observation), ...]; observation is the Benign agent's
                 visible output or "NONE". Never contains judge results or evidence.
        Inputs are copies; mutating them does not affect the loop.
        """
