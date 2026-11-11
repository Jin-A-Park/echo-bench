"""Step-2 observation for Data Stealing cases: the attacker tool's simulated response.

The original (src/utils.py get_simulated_attacker_tool_response) looks up
data/attacker_simulated_responses.json by the exact key "(<tool>,<params>)" and, on a miss,
asks GPT-4 (gpt-4-0613) for a new response and writes it back into that file.

echo-bench uses the same cache read-only (attacker_simulated_responses.json, vendored unchanged
from uiuc-kang-lab/InjecAgent @ f19c9f2) and never generates. Lookup order:
  1. exact key, as in the original;
  2. same tool, params equal after normalisation (parsed, keys sorted, whitespace removed);
  3. same tool, any params: the first dict-params entry in file order (deterministic).
The params are what the Benign model wrote in step 1, so (1) mostly misses for a model other than
the ones the cache was built with. The cache covers every Data Stealing tool, so (3) always finds one.
"""
from __future__ import annotations

import ast
import json
import warnings
from functools import lru_cache
from pathlib import Path

CACHE_JSON = Path(__file__).parent / "attacker_simulated_responses.json"


def normalize_params(params: str) -> str | None:
    """Canonical form of an Action Input string, or None if it does not parse."""
    for parse in (json.loads, ast.literal_eval):
        try:
            with warnings.catch_warnings():   # literal_eval warns on escapes like "\_" in cached keys
                warnings.simplefilter("ignore", SyntaxWarning)
                obj = parse(params)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            continue
        try:
            return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError):   # e.g. literal_eval gave a set or bytes
            return None
    return None


@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, str], dict[tuple[str, str], str], dict[str, str]]:
    exact: dict[str, str] = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    by_norm: dict[tuple[str, str], str] = {}
    by_tool: dict[str, str] = {}
    first_any: dict[str, str] = {}
    for key, response in exact.items():
        tool, params = key[1:-1].split(",", 1)
        norm = normalize_params(params)
        if norm is not None:
            by_norm.setdefault((tool, norm), response)
            if norm.startswith("{"):
                by_tool.setdefault(tool, response)
        first_any.setdefault(tool, response)
    return exact, by_norm, {**first_any, **by_tool}


def simulated_response(tool: str, params: str) -> tuple[str, str]:
    """(response, how it was found: "exact" | "normalized" | "same_tool")."""
    exact, by_norm, by_tool = _index()
    if (hit := exact.get(f"({tool},{params})")) is not None:
        return hit, "exact"
    norm = normalize_params(params)
    if norm is not None and (hit := by_norm.get((tool, norm))) is not None:
        return hit, "normalized"
    if tool in by_tool:
        return by_tool[tool], "same_tool"
    raise KeyError(f"no cached simulated response for attacker tool {tool!r}")
