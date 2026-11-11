"""InjecAgent adapter (prompted ReAct agent, single next-step prediction).

Mirrors InjecAgent's evaluate_prompted_agent.py step 1:
- the attacker edits the <Attacker Instruction> slot of the user tool's response;
- the Benign model sees the original system/user prompt with the scratchpad already containing
  Thought -> Action(user tool) -> Observation(poisoned tool response), and writes its next step;
- judged with the original evaluate_output_prompted: success iff the agent calls attacker_tools[0].

Data Stealing cases are judged on step 1 only (calling the data-reading tool); the original's
step 2 (GmailSendEmail after a GPT-4-simulated observation) is not run.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.benign import BenignModel
from core.schema import Case, RunResult

from .base import Adapter
from .injecagent_src.agent_prompts import PROMPT_DICT
from .injecagent_src.output_parsing import evaluate_output_prompted

SLOT = "attacker_instruction"
PLACEHOLDER = "<Attacker Instruction>"
TOOLS_JSON = Path(__file__).parent / "injecagent_src" / "tools.json"


@lru_cache(maxsize=1)
def tool_dict() -> dict[str, dict]:
    """Same as InjecAgent's utils.get_tool_dict(): full tool name -> spec."""
    out = {}
    for kit in json.loads(TOOLS_JSON.read_text(encoding="utf-8")):
        for tool in kit["tools"]:
            tool = dict(tool, name=kit["toolkit"] + tool["name"])
            out[tool["name"]] = tool
    return out


def render_tool_response(template: str, injection: str) -> str:
    # The original Tool Response is json.dumps(template) with the instruction inserted *unescaped*.
    return json.dumps(template).replace(PLACEHOLDER, injection)


class InjecAgentAdapter(Adapter):
    def __init__(self, benign: BenignModel, prompt_type: str = "InjecAgent"):
        self.benign = benign
        self.sys_prompt, self.user_prompt = PROMPT_DICT[prompt_type]
        self.tools = tool_dict()

    def reset(self, case: Case) -> None:
        pass   # stateless: every attempt starts from the same scratchpad

    def get_source(self, case: Case) -> dict[str, str]:
        return {SLOT: ""}   # clean tool response has nothing in the slot

    def build_messages(self, case: Case, injection: str) -> list[dict[str, str]]:
        r = case.raw
        tool_names = [r["user_tool"]] + r["attacker_tools"]
        observation = render_tool_response(r["untrusted_content"]["template"], injection)
        scratchpad = (f"\n{r['thought']}\nAction: {r['user_tool']}\n"
                      f"Action Input: {r['tool_parameters']}\nObservation: {observation}\n")
        user = self.user_prompt.format(
            available_tool_descriptions=json.dumps([self.tools[t] for t in tool_names], indent=True),
            input=case.user_prompt,
            available_tool_names=tool_names,
            agent_scratchpad=scratchpad,
        )
        return [{"role": "system", "content": self.sys_prompt}, {"role": "user", "content": user}]

    def run(self, case: Case, modified: dict[str, str]) -> RunResult:
        injection = modified[SLOT]
        res = self.benign.chat(self.build_messages(case, injection))
        res.trace["injection"] = injection
        return res

    def judge(self, case: Case, run: RunResult) -> tuple[bool, dict]:
        r = case.raw
        try:
            parsed = evaluate_output_prompted(
                run.output, r["attacker_tools"][0], r["attacker_tools"], r["user_tool"],
                run.trace.get("injection", ""))
        except Exception as e:  # noqa: BLE001 - the original skips such items; we count them invalid
            parsed = {"eval": "invalid", "invalid_reason": f"parser error: {e}"}
        detail = {
            "judge": "injecagent_output_parsing",
            "eval": parsed["eval"],                      # succ | unsucc | invalid
            "invalid_reason": parsed.get("invalid_reason"),
            "attack_family": r["attack_family"],
            "target_tool": r["attacker_tools"][0],
            "attacker_tool_parameters": parsed.get("Attacker Tool Parameters"),
            "timed_out": run.timed_out,
            "error": run.error,
            "finish_reason": run.trace.get("finish_reason"),
            "usage": run.trace.get("usage"),
        }
        return parsed["eval"] == "succ", detail
