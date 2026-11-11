"""Attempt loop for one case: attack -> run -> judge -> log, until success or budget B is used."""
from __future__ import annotations

from adapters.base import Adapter
from attackers.base import Attacker

from .logger import JsonlLogger
from .schema import Attempt, Case, Result


def run_case(case: Case, adapter: Adapter, attacker: Attacker,
             budget: int, logger: JsonlLogger) -> Result:
    source = adapter.get_source(case)
    history: list[tuple[dict[str, str], str]] = []   # (modified source, observation) only

    for i in range(1, budget + 1):
        adapter.reset(case)
        modified = attacker.attack(source, case.goal, history)
        run = adapter.run(case, modified)
        observation = adapter.observe(run)
        success, detail = adapter.judge(case, run)

        logger.log_attempt(Attempt(case.case_id, i, modified, observation, success, detail))
        if success:
            return Result(case.case_id, True, i, "success")
        history.append((modified, observation))

    return Result(case.case_id, False, budget, "budget_exhausted")
