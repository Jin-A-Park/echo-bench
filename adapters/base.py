"""Adapter interface: everything benchmark-specific lives behind these methods."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.schema import Case, RunResult

NONE = "NONE"   # observation when the attacker gets nothing back (timeout, no visible output)


class Adapter(ABC):
    @abstractmethod
    def reset(self, case: Case) -> None:
        """Restore the initial environment snapshot before each attempt."""

    @abstractmethod
    def get_source(self, case: Case) -> dict[str, str]:
        """Editable slots -> original (clean) text. The attacker only rewrites these."""

    @abstractmethod
    def run(self, case: Case, modified: dict[str, str]) -> RunResult:
        """Inject the modified slots and run the Benign model."""

    def observe(self, run: RunResult) -> str:
        """What the attacker may see. Default: the Benign output, or NONE."""
        return run.output if run.output is not None else NONE

    @abstractmethod
    def judge(self, case: Case, run: RunResult) -> tuple[bool, dict]:
        """(attack succeeded?, evidence). Evidence is logged but never shown to the attacker."""
