"""Adapter registry. Real adapters register here as they are written."""
from __future__ import annotations

from core.benign import BenignModel

from .base import Adapter
from .bipia import BipiaAdapter
from .injecagent import InjecAgentAdapter
from .mock import MockAdapter


def _agentdojo(benign: BenignModel) -> Adapter:
    from .agentdojo import AgentDojoAdapter   # heavy import; only when needed
    return AgentDojoAdapter(benign)


REAL: dict[str, type[Adapter] | object] = {
    "injecagent": InjecAgentAdapter,
    "agentdojo": _agentdojo,   # also serves runner "agentdyn"
    "bipia": BipiaAdapter,
}


def build_adapters(names: set[str], mode: str, benign: BenignModel) -> dict[str, Adapter]:
    """mode: "real" (fail if missing) | "mock" (all mock) | "auto" (real where available, else mock)."""
    out: dict[str, Adapter] = {}
    for n in names:
        if mode != "mock" and n in REAL:
            out[n] = REAL[n](benign)
        elif mode in ("mock", "auto"):
            out[n] = MockAdapter(benign)
        else:
            raise SystemExit(f"no real adapter for {n!r} yet; use `adapters: auto` or `mock`")
    return out
