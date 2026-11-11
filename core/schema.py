"""Shared data classes for the Echo evaluation pipeline."""
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Any
 
 
# Runner names in the data -> adapter name. AgentDojo and AgentDyn share one codebase.
ADAPTER_OF = {
    "agentdojo": "agentdojo",
    "agentdyn": "agentdojo",
    "injecagent": "injecagent",
    "bipia": "bipia",
}
 
 
@dataclass
class Case:
    case_id: str
    runner: str              # original runner name from the data
    adapter: str             # adapter that handles this case
    suite: str
    user_case_id: str
    attacker_case_id: str
    user_prompt: str
    goal: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)  # full source row
 
 
@dataclass
class Attempt:
    case_id: str
    attempt_idx: int
    modified_source: dict[str, str]   # {slot id: text}
    observation: str                  # what the attacker may see, or "NONE"
    success: bool
    detail: dict[str, Any] = field(default_factory=dict)  # judge evidence, never shown to the attacker
 
 
@dataclass
class Result:
    case_id: str
    success: bool
    attempts_used: int
    end_reason: str                   # "success" | "budget_exhausted"


@dataclass
class RunResult:
    """What one Benign run produced. Adapters may put anything extra in `trace`."""
    output: str | None                # final Benign text; None if it timed out / failed
    timed_out: bool = False
    error: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)  # tool calls, env state, ...