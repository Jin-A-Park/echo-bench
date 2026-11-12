"""AgentDojo / AgentDyn adapter (workspace + github suites, benchmark version v1).

Mirrors TaskSuite.run_task_with_pipeline with the default no-defense pipeline
(system message -> user prompt -> LLM -> tool loop), with two differences:

1. The LLM element calls the shared BenignModel, so timeout T, retries and the DeepSeek
   client are the same as for every other adapter. T covers the whole attempt (all LLM calls
   of the tool loop, see core/loop.py); the tool loop stops after 15 iterations as in AgentDojo.
2. Injection: AgentDojo str.format()s raw text into environment.yaml, which breaks YAML (or
   folds newlines) for arbitrary attacker text. We load the environment with plain markers in the
   injectable vectors and then replace each marker with the attacker's exact text on the
   loaded objects.

Security = AgentDojo's injection-task check (attack success). Utility is logged only.
"""
from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from openai.types.chat import ChatCompletionMessage

from agentdojo.agent_pipeline import (
    AgentPipeline, BasePipelineElement, InitQuery, SystemMessage, ToolsExecutionLoop, ToolsExecutor,
)
from agentdojo.agent_pipeline.agent_pipeline import load_system_message
from agentdojo.agent_pipeline.llms.openai_llm import (
    _function_to_openai, _message_to_openai, _openai_to_assistant_message,
)
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.attacks.base_attacks import BaseAttack
from agentdojo.functions_runtime import EmptyEnv, FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.task_suite.task_suite import functions_stack_trace_from_messages, model_output_from_messages
from agentdojo.types import ChatMessage, get_text_content_as_str

from core.benign import BenignModel
from core.schema import Case, RunResult

from .base import NONE, Adapter

BENCHMARK_VERSION = "v1"


# ---- LLM element backed by the shared Benign wrapper ------------------------------------------

class BenignUnavailable(Exception):
    """The Benign call timed out or failed; carries the state reached so far."""

    def __init__(self, result: RunResult, messages: Sequence[ChatMessage], env: Any):
        super().__init__(result.error or "timeout")
        self.result, self.messages, self.env = result, list(messages), env


def _to_plain(msg: dict) -> dict:
    """AgentDojo's OpenAI messages -> plain chat format (system role, string content) for DeepSeek."""
    msg = dict(msg)
    if msg["role"] == "developer":
        msg["role"] = "system"
    content = msg.get("content")
    if isinstance(content, list):
        msg["content"] = "".join(part.get("text", "") for part in content)
    return msg


class BenignLLM(BasePipelineElement):
    name = "benign"

    def __init__(self, benign: BenignModel):
        self.benign = benign
        self.calls: list[dict] = []   # per-call usage/finish_reason of the current run

    def query(self, query: str, runtime: FunctionsRuntime, env=EmptyEnv(),
              messages: Sequence[ChatMessage] = [], extra_args: dict = {}):
        oa_messages = [_to_plain(_message_to_openai(m, self.benign.cfg.model)) for m in messages]
        tools = [_function_to_openai(t) for t in runtime.functions.values()]
        res = self.benign.chat(oa_messages, tools=tools or None,
                               **({"tool_choice": "auto"} if tools else {}))
        self.calls.append({k: res.trace.get(k) for k in ("finish_reason", "usage")}
                          | {"timed_out": res.timed_out, "error": res.error})
        if res.output is None:
            raise BenignUnavailable(res, messages, env)
        output = _openai_to_assistant_message(ChatCompletionMessage.model_validate(res.trace["message"]))
        return query, runtime, env, [*messages, output], extra_args


# ---- injection helpers -------------------------------------------------------------------------

class _Candidates(BaseAttack):
    """Only used for BaseAttack.get_injection_candidates (canary + ground-truth run, no LLM)."""
    name = "echo_candidates"

    def attack(self, user_task, injection_task):
        return {}


def _replace(obj: Any, rep: dict[str, str]) -> Any:
    if isinstance(obj, str):
        for k, v in rep.items():
            obj = obj.replace(k, v)
        return obj
    if isinstance(obj, list):
        return [_replace(x, rep) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_replace(x, rep) for x in obj)
    if isinstance(obj, dict):
        return {_replace(k, rep): _replace(v, rep) for k, v in obj.items()}
    return obj


@lru_cache(maxsize=None)
def _suite(name: str):
    return get_suite(BENCHMARK_VERSION, name)


@lru_cache(maxsize=None)
def _candidates(suite_name: str, user_task_id: str) -> tuple[str, ...]:
    suite = _suite(suite_name)
    return tuple(_Candidates(suite, None).get_injection_candidates(suite.get_user_task_by_id(user_task_id)))


def _fmt_call(c) -> str:
    return f"{c.function}({', '.join(f'{k}={v!r}' for k, v in c.args.items())})"


def _marker(i: int) -> str:
    return f"ECHOINJ{i:03d}X"   # plain alnum: safe in any YAML context


# ---- adapter -----------------------------------------------------------------------------------

class AgentDojoAdapter(Adapter):
    def __init__(self, benign: BenignModel):
        self.llm = BenignLLM(benign)
        self.pipeline = AgentPipeline([
            SystemMessage(load_system_message(None)),
            InitQuery(),
            self.llm,
            ToolsExecutionLoop([ToolsExecutor(tool_result_to_str), self.llm]),
        ])
        self._fresh: dict[str, Any] = {}   # case_id -> environment with markers (set by reset)

    @staticmethod
    def _ids(case: Case) -> tuple[str, str]:
        return case.user_case_id.split(":", 1)[1], case.attacker_case_id.split(":", 1)[1]

    def get_source(self, case: Case) -> dict[str, str]:
        user_id, _ = self._ids(case)
        defaults = _suite(case.suite).get_injection_vector_defaults()
        return {v: defaults[v] for v in _candidates(case.suite, user_id)}

    def reset(self, case: Case) -> None:
        """Fresh environment for this attempt, with markers in the injectable vectors."""
        user_id, _ = self._ids(case)
        markers = {v: _marker(i) for i, v in enumerate(_candidates(case.suite, user_id))}
        self._fresh[case.case_id] = _suite(case.suite).load_and_inject_default_environment(markers)

    def _inject(self, case: Case, modified: dict[str, str]):
        user_id, _ = self._ids(case)
        env = self._fresh.pop(case.case_id)
        cands = _candidates(case.suite, user_id)
        unknown = set(modified) - set(cands)
        if unknown:
            raise KeyError(f"attacker returned unknown vectors: {sorted(unknown)}")
        rep = {_marker(i): modified.get(v, "") for i, v in enumerate(cands)}
        return type(env).model_validate(_replace(env.model_dump(), rep))

    def run(self, case: Case, modified: dict[str, str]) -> RunResult:
        suite = _suite(case.suite)
        user_id, inj_id = self._ids(case)
        user_task = suite.get_user_task_by_id(user_id)
        if case.case_id not in self._fresh:
            self.reset(case)
        task_env = user_task.init_environment(self._inject(case, modified))
        pre_env = task_env.model_copy(deep=True)
        runtime = FunctionsRuntime(suite.tools)
        self.llm.calls = []

        failure: RunResult | None = None
        messages: list = []
        model_output = None
        for _ in range(3):   # same retry-on-empty-output rule as run_task_with_pipeline
            try:
                _, _, task_env, messages, _ = self.pipeline.query(user_task.PROMPT, runtime, task_env)
            except BenignUnavailable as e:
                task_env, messages, failure = e.env, e.messages, e.result
            try:
                model_output = model_output_from_messages(messages)
            except ValueError:
                model_output = None
            if model_output is not None or failure is not None:
                break

        text = get_text_content_as_str(model_output) if model_output else ""
        return RunResult(
            output=None if failure else text,
            timed_out=bool(failure and failure.timed_out),
            error=failure.error if failure else None,
            trace={
                "user_task": user_task, "injection_task": suite.get_injection_task_by_id(inj_id),
                "pre_env": pre_env, "post_env": task_env, "model_output": model_output or [],
                "stack": functions_stack_trace_from_messages(messages),
                "calls": self.llm.calls,
            },
        )

    def observe(self, run: RunResult) -> str:
        """Threat model, option A: only the agent's final answer to the user (or NONE).
        Tool calls, tool results and reasoning stay hidden; they are logged in `detail` only."""
        return NONE if run.output is None else run.output

    def judge(self, case: Case, run: RunResult) -> tuple[bool, dict]:
        suite, t = _suite(case.suite), run.trace
        args = (t["model_output"], t["pre_env"], t["post_env"], t["stack"])
        security = suite._check_task_result(t["injection_task"], *args)
        try:
            utility = suite._check_task_result(t["user_task"], *args)
        except Exception as e:  # noqa: BLE001 - utility is informational only
            utility = f"error: {type(e).__name__}"
        return bool(security), {
            "judge": "agentdojo_security",
            "security": bool(security),
            "utility": utility,
            "tool_calls": [_fmt_call(c)[:200] for c in t["stack"]],
            "timed_out": run.timed_out,
            "error": run.error,
            "llm_calls": t["calls"],
        }
