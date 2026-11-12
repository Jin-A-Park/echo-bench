"""Aggregate a run directory (results.jsonl + attempts.jsonl) into per-benchmark metrics.

Metrics per runner (and overall):
  ASR                    successful cases / cases
  avg attempts           mean attempts used over all cases (failures count as B)
  avg attempts to succ   mean attempts used over successful cases only
  NONE rate              attempts whose observation was "NONE" (timeout/failure) / attempts
  errors                 cases ended by an exception (counted as failures in ASR)

Usage: python -m core.report outputs/<run>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

NONE = "NONE"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# results.jsonl written before Result had a `runner` field: infer it from the case_id prefix
_PREFIX_RUNNER = {"workspace": "agentdojo", "github": "agentdyn", "injecagent": "injecagent", "code": "bipia"}


def _runner_of(case_id: str, known: dict[str, str]) -> str:
    return known.get(case_id) or _PREFIX_RUNNER.get(case_id.split("__", 1)[0], "?")


def summarize(run_dir: str | Path, write: bool = True) -> dict:
    run_dir = Path(run_dir)
    results = _read(run_dir / "results.jsonl")
    attempts = _read(run_dir / "attempts.jsonl")
    runner_of = {r["case_id"]: _runner_of(r["case_id"], {r["case_id"]: r.get("runner", "")})
                 for r in results}
    for r in results:
        r["runner"] = runner_of[r["case_id"]]

    groups: dict[str, dict] = defaultdict(lambda: {"cases": 0, "succ": 0, "used": 0, "used_succ": 0,
                                                   "attempts": 0, "none": 0, "err": 0})
    for r in results:
        for key in (r.get("runner") or "?", "total"):
            g = groups[key]
            g["cases"] += 1
            g["used"] += r["attempts_used"]
            g["err"] += r.get("end_reason") == "error"
            if r["success"]:
                g["succ"] += 1
                g["used_succ"] += r["attempts_used"]
    for a in attempts:
        if a["case_id"] not in runner_of:
            continue   # case still running / crashed before its result line
        for key in (_runner_of(a["case_id"], runner_of), "total"):
            groups[key]["attempts"] += 1
            groups[key]["none"] += a["observation"] == NONE

    summary = {}
    for key, g in groups.items():
        summary[key] = {
            "cases": g["cases"],
            "successes": g["succ"],
            "asr": g["succ"] / g["cases"] if g["cases"] else None,
            "avg_attempts": g["used"] / g["cases"] if g["cases"] else None,
            "avg_attempts_to_success": g["used_succ"] / g["succ"] if g["succ"] else None,
            "attempts": g["attempts"],
            "none_rate": g["none"] / g["attempts"] if g["attempts"] else None,
            "errors": g["err"],
        }
    summary = dict(sorted(summary.items(), key=lambda kv: (kv[0] == "total", kv[0])))
    if write:
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def format_table(summary: dict) -> str:
    def pct(x):
        return "-" if x is None else f"{x:.1%}"

    def num(x):
        return "-" if x is None else f"{x:.2f}"

    rows = [f"{'runner':<12} {'cases':>5} {'ASR':>14} {'avg att':>8} {'att->succ':>9} {'NONE':>14} {'err':>4}"]
    for k, s in summary.items():
        rows.append(f"{k:<12} {s['cases']:>5} {s['successes']:>4} ({pct(s['asr']):>6}) "
                    f"{num(s['avg_attempts']):>8} {num(s['avg_attempts_to_success']):>9} "
                    f"{round((s['none_rate'] or 0) * s['attempts']):>4}/{s['attempts']:<4} ({pct(s['none_rate'])}) {s['errors']:>4}")
    return "\n".join(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m core.report outputs/<run>")
    print(format_table(summarize(sys.argv[1])))
