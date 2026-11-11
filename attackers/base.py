"""Attacker interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Attacker(ABC):
    @abstractmethod
    def attack(self, source: dict[str, str], goal: str,
               history: list[tuple[dict[str, str], str]]) -> dict[str, str]:
        """Return a modified copy of `source` (same keys).
        history = [(previous modified source, observation), ...] -- never judge results/evidence."""
