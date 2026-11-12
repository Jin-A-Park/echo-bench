"""Read config.yaml (+ .env for API keys) into dataclasses."""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from .benign import BenignConfig


@dataclass
class Config:
    benign: BenignConfig = field(default_factory=BenignConfig)
    budget: int = 10                  # B
    attacker: str = "dummy"           # key in attackers.ATTACKERS; normally set in config.yaml
    attacker_args: dict = field(default_factory=dict)   # passed as ATTACKERS[attacker](**attacker_args)
    adapters: str = "real"            # "real" | "auto" | "mock"
    data: list[str] = field(default_factory=lambda: ["data/test_cases.jsonl"])   # not data/*.jsonl: catalogs aren't cases
    sample_per_runner: int | None = None
    seed: int = 0
    output_dir: str = "outputs"

    def data_paths(self) -> list[str]:
        out: list[str] = []
        for pat in self.data:
            out.extend(sorted(glob.glob(pat)) or [pat])
        return out


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal KEY=VALUE reader; real environment variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def load_config(path: str | Path) -> Config:
    load_dotenv(Path(path).parent / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")   # project root
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    benign_raw = raw.pop("benign", None) or {}
    known = {f.name for f in fields(BenignConfig)}
    unknown = set(benign_raw) - known
    if unknown:
        raise SystemExit(f"[config] unknown benign keys: {sorted(unknown)}")
    return Config(benign=BenignConfig(**benign_raw), **raw)
