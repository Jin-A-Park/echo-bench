"""Load benchmark jsonl files into Case objects (dedupe + optional sampling)."""
from __future__ import annotations
 
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator
 
from .schema import ADAPTER_OF, Case
 
 
def _iter_jsonl(path: Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:          # line by line: code.jsonl is ~38MB
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
 
 
def _keep_row(row: dict) -> bool:
    """Drop variants that only differ in how the injection is placed.
    Echo's attacker writes the injection itself, so these multipliers are meaningless."""
    runner = row["evaluation"]["runner"]
    if runner == "bipia":
        return row["untrusted_content"].get("position") == "end"
    if runner == "injecagent":
        return row.get("setting") == "base"
    return True
 
 
def _bipia_goal(row: dict) -> str:
    """BIPIA's attack_goal is only a category name. For position=='end',
    poisoned_context == clean_context + attack text, so slice off the suffix."""
    uc = row["untrusted_content"]
    clean, poisoned = uc["clean_context"], uc["poisoned_context"]
    if not poisoned.startswith(clean):
        raise ValueError(f"cannot recover BIPIA payload for {row['case_id']}")
    return poisoned[len(clean):].strip()
 
 
def _to_case(row: dict) -> Case:
    runner = row["evaluation"]["runner"]
    if runner not in ADAPTER_OF:
        raise ValueError(f"unknown runner {runner!r} in {row.get('case_id')}")
    goal = _bipia_goal(row) if runner == "bipia" else row["attack_goal"]
    return Case(
        case_id=row["case_id"],
        runner=runner,
        adapter=ADAPTER_OF[runner],
        suite=row["suite"],
        user_case_id=row["user_case_id"],
        attacker_case_id=row["attacker_case_id"],
        user_prompt=row["user_prompt"],
        goal=goal,
        raw=row,
    )
 
 
def load_cases(
    paths: Iterable[str | Path],
    dedupe: bool = True,
    sample_per_runner: int | None = None,
    seed: int = 0,
) -> list[Case]:
    cases: list[Case] = []
    seen: set[tuple[str, str]] = set()
    for p in paths:
        p = Path(p)
        if not p.exists() or p.stat().st_size == 0:
            print(f"[loader] skip empty/missing file: {p}")
            continue
        for row in _iter_jsonl(p):
            if dedupe:
                if not _keep_row(row):
                    continue
                key = (row["user_case_id"], row["attacker_case_id"])
                if key in seen:
                    continue
                seen.add(key)
            cases.append(_to_case(row))
 
    if sample_per_runner:
        rng = random.Random(seed)
        by_runner: dict[str, list[Case]] = defaultdict(list)
        for c in cases:
            by_runner[c.runner].append(c)
        cases = [c for group in by_runner.values()
                 for c in rng.sample(group, min(sample_per_runner, len(group)))]
    return cases