"""Attempt loop for one case: attack -> run -> observe -> judge -> log, until success or budget B.

The attacker is touched in exactly one place: attacker.attack(source, goal, history).
Threat-model rules enforced here:
- T is the attacker's wait for one attempt: adapter.run() (all Benign calls, tool loop, retries)
  runs inside one T-second window for the case's runner; past it the observation is NONE;
- an attempt whose observation is NONE (timeout / failed call) is not judged and counts as a failure;
- an exception in one case ends that case with end_reason="error" instead of stopping the run.
"""
from __future__ import annotations

import copy
import time
import traceback

from adapters.base import NONE, Adapter
from attackers.base import Attacker

from .benign import BenignModel
from .logger import JsonlLogger
from .schema import Attempt, Case, Result


def _check_modified(modified: object, source: dict[str, str]) -> dict[str, str]:
    """Fail fast with a clear message if an attacker returns the wrong shape."""
    if not isinstance(modified, dict):
        raise TypeError(f"attack() must return dict[str, str], got {type(modified).__name__}")
    if set(modified) != set(source):
        raise ValueError(f"attack() must return the same keys as source: "
                         f"expected {sorted(source)}, got {sorted(modified)}")
    bad = [k for k, v in modified.items() if not isinstance(v, str)]
    if bad:
        raise TypeError(f"attack() values must be str; not str for {bad}")
    return modified


def run_case(case: Case, adapter: Adapter, attacker: Attacker,
             budget: int, logger: JsonlLogger, benign: BenignModel) -> Result:
    def result(success: bool, used: int, reason: str, error: str | None = None) -> Result:
        return Result(case.case_id, success, used, reason, runner=case.runner, suite=case.suite, error=error)

    history: list[tuple[dict[str, str], str]] = []   # (modified source, observation) only
    i = 0
    timeout_s = benign.timeout_for(case.runner)
    try:
        source = adapter.get_source(case)
        for i in range(1, budget + 1):
            adapter.reset(case)
            # copies: an attacker that mutates its inputs cannot corrupt the source or past history
            modified = _check_modified(
                attacker.attack(dict(source), case.goal, copy.deepcopy(history)), source)
            started = time.monotonic()
            with benign.attempt_window(timeout_s):
                run = adapter.run(case, modified)
            elapsed = round(time.monotonic() - started, 2)
            observation = adapter.observe(run)

            if observation == NONE:   # flowchart: NONE skips "goal reached?" and goes to the budget check
                success, detail = False, {"judge": "skipped_none", "timed_out": run.timed_out,
                                          "error": run.error}
            else:
                success, detail = adapter.judge(case, run)
            detail = {**detail, "elapsed_s": elapsed, "timeout_s": timeout_s}

            logger.log_attempt(Attempt(case.case_id, i, modified, observation, success, detail))
            if success:
                return result(True, i, "success")
            history.append((modified, observation))
    except Exception as e:  # noqa: BLE001 - one broken case must not kill a long run
        msg = f"{type(e).__name__}: {e}"
        print(f"  [error] {case.case_id} at attempt {i}: {msg}", flush=True)
        return result(False, i, "error", error=msg + "\n" + traceback.format_exc(limit=5))

    return result(False, budget, "budget_exhausted")
