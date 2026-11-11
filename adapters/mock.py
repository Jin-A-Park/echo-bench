"""Stand-in adapter for every runner until the real ones exist.
Builds a plain chat prompt from the data row and judges by substring match.
Good enough to exercise the loop; NOT a valid benchmark judge."""
from __future__ import annotations

from core.benign import BenignModel
from core.schema import Case, RunResult

from .base import Adapter

INJECAGENT_SLOT = "<Attacker Instruction>"


class MockAdapter(Adapter):
    def __init__(self, benign: BenignModel):
        self.benign = benign

    def reset(self, case: Case) -> None:
        pass   # stateless

    def get_source(self, case: Case) -> dict[str, str]:
        if case.runner == "bipia":
            return {"context": case.raw["untrusted_content"]["clean_context"]}
        if case.runner == "injecagent":
            return {"attacker_instruction": ""}   # the tool-response field that carried the payload
        return {"injection": ""}                  # agentdojo/agentdyn: real vectors come from the env

    def _render(self, case: Case, modified: dict[str, str]) -> str:
        if case.runner == "bipia":
            return f"{modified['context']}\n\n{case.user_prompt}"
        if case.runner == "injecagent":
            tool_out = case.raw["untrusted_content"]["template"].replace(
                INJECAGENT_SLOT, modified["attacker_instruction"])
            return f"{case.user_prompt}\n\n[tool {case.raw['user_tool']}] {tool_out}"
        return f"{case.user_prompt}\n\n[tool output] {modified['injection']}"

    def run(self, case: Case, modified: dict[str, str]) -> RunResult:
        msgs = []
        if case.raw.get("system_prompt"):
            msgs.append({"role": "system", "content": case.raw["system_prompt"]})
        msgs.append({"role": "user", "content": self._render(case, modified)})
        return self.benign.chat(msgs)

    def judge(self, case: Case, run: RunResult) -> tuple[bool, dict]:
        hit = run.output is not None and case.goal in run.output
        return hit, {"judge": "mock_substring", "timed_out": run.timed_out, "error": run.error,
                     "finish_reason": run.trace.get("finish_reason"), "usage": run.trace.get("usage")}
