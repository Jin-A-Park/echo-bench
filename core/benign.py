"""Benign model wrapper shared by all adapters.

- provider "deepseek" (or any OpenAI-compatible server): chat completions via the openai SDK.
- provider "mock": no network, for testing the loop.

Timeout rule: a call that takes longer than T seconds (wall clock) returns output=None, timed_out=True,
which adapters turn into the observation "NONE". Rate limits / connection / 5xx errors are retried
with backoff (each try gets its own T) and are not reported as a timeout.
"""
from __future__ import annotations

import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Callable

from .schema import RunResult

Messages = list[dict[str, Any]]   # OpenAI chat format
Tools = list[dict[str, Any]] | None


@dataclass
class BenignConfig:
    provider: str = "deepseek"            # "deepseek" | "openai_compat" | "mock"
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout_s: float = 60.0               # T
    temperature: float = 0.0
    max_tokens: int | None = 2048
    max_retries: int = 3                  # for 429 / 5xx / connection errors only
    mock_follow_prob: float = 0.3         # mock only


class BenignModel:
    def __init__(self, cfg: BenignConfig, *, seed: int = 0, client: Any = None):
        self.cfg = cfg
        self.name = f"{cfg.provider}:{cfg.model}"
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="benign")
        if cfg.provider == "mock":
            self._call = _mock_backend(seed, cfg.mock_follow_prob)
        else:
            self.client = client or _openai_client(cfg)
            self._call = self._openai_call

    # ---- public -------------------------------------------------------------------------------
    def chat(self, messages: Messages, tools: Tools = None, **params: Any) -> RunResult:
        """One Benign turn. With `tools`, requested tool calls are in trace["tool_calls"]
        and trace["message"] is the assistant message to append for the next turn."""
        for attempt in range(self.cfg.max_retries + 1):
            fut = self._pool.submit(self._call, messages, tools, params)
            try:
                return fut.result(timeout=self.cfg.timeout_s)
            except FutureTimeout:
                fut.cancel()   # a running thread can't be killed; its late result is dropped
                return RunResult(output=None, timed_out=True)
            except Exception as e:  # noqa: BLE001
                if _is_transient(e) and attempt < self.cfg.max_retries:
                    time.sleep(min(2 ** attempt, 30) + random.random())
                    continue
                return RunResult(output=None, error=f"{type(e).__name__}: {e}")
        raise AssertionError("unreachable")

    # ---- backends -----------------------------------------------------------------------------
    def _openai_call(self, messages: Messages, tools: Tools, params: dict) -> RunResult:
        kwargs: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
        }
        if self.cfg.max_tokens:
            kwargs["max_tokens"] = self.cfg.max_tokens
        if tools:
            kwargs["tools"] = tools
        kwargs.update(params)
        resp = self.client.chat.completions.create(**kwargs)

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = [
            {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ]
        return RunResult(
            output=msg.content or "",
            trace={
                "message": msg.model_dump(exclude_none=True),
                "tool_calls": tool_calls,
                "finish_reason": choice.finish_reason,
                "usage": resp.usage.model_dump() if resp.usage else None,
                "model": resp.model,
            },
        )


def _openai_client(cfg: BenignConfig):
    from openai import OpenAI

    key = os.environ.get(cfg.api_key_env)
    if not key:
        raise SystemExit(f"[benign] {cfg.api_key_env} is not set (put it in .env or the environment)")
    # Retries are handled in chat() so each try gets its own T; the SDK timeout is a backstop.
    return OpenAI(api_key=key, base_url=cfg.base_url, timeout=cfg.timeout_s + 5, max_retries=0)


def _is_transient(e: Exception) -> bool:
    try:
        import openai
    except ImportError:
        return False
    if isinstance(e, (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)):
        return not isinstance(e, openai.APITimeoutError)
    return False


def _mock_backend(seed: int, follow_prob: float) -> Callable[[Messages, Tools, dict], RunResult]:
    rng = random.Random(seed)

    def mock(messages: Messages, tools: Tools, params: dict) -> RunResult:
        # "Falls for" the injection with probability follow_prob by echoing its input.
        if rng.random() < follow_prob:
            return RunResult(output="Sure. " + messages[-1]["content"])
        return RunResult(output="Here is the answer to your request.")
    return mock
