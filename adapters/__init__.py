"""Adapter registry. Real adapters register here as they are written."""
from __future__ import annotations

from core.benign import BenignModel

from .base import Adapter
from .mock import MockAdapter

REAL: dict[str, type[Adapter]] = {
    # "injecagent": InjecAgentAdapter,
    # "agentdojo": AgentDojoAdapter,
    # "bipia": BipiaAdapter,
}


def build_adapters(names: set[str], mode: str, benign: BenignModel) -> dict[str, Adapter]:
    out: dict[str, Adapter] = {}
    for n in names:
        if mode == "mock":
            out[n] = MockAdapter(benign)
        elif n in REAL:
            out[n] = REAL[n](benign)
        else:
            raise SystemExit(f"no real adapter for {n!r} yet; set `adapters: mock` in the config")
    return out
