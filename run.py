"""Entry point: config -> cases -> attempt loop per case -> logs + summary in outputs/<timestamp>/.

Examples
  python run.py                                   # everything as in config.yaml
  python run.py --sample 20                       # 20 cases per benchmark (runner)
  python run.py --sample 20 --runners bipia injecagent --budget 3
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time

# AgentDojo reads its UTF-8 data files with the locale encoding (cp949 on Korean Windows).
# Re-launch in Python's UTF-8 mode before anything else is imported.
if sys.platform == "win32" and not sys.flags.utf8_mode:
    sys.exit(subprocess.call([sys.executable, "-X", "utf8", *sys.argv]))

from dataclasses import asdict
from pathlib import Path

import yaml

from adapters import build_adapters
from attackers import ATTACKERS
from core.benign import BenignModel
from core.config import load_config
from core.loader import load_cases
from core.logger import JsonlLogger
from core.loop import run_case
from core.report import format_table, summarize

RUNNERS = ("agentdojo", "agentdyn", "injecagent", "bipia")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--sample", type=int, help="cases per runner (overrides sample_per_runner; 0 = all)")
    ap.add_argument("--budget", type=int, help="B, max attempts per case (overrides config)")
    ap.add_argument("--runners", nargs="+", choices=RUNNERS, help="only these benchmarks")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.sample is not None:
        cfg.sample_per_runner = args.sample or None
    if args.budget is not None:
        cfg.budget = args.budget

    cases = load_cases(cfg.data_paths(), sample_per_runner=cfg.sample_per_runner, seed=cfg.seed)
    if args.runners:
        cases = [c for c in cases if c.runner in args.runners]
    if not cases:
        sys.exit("[run] no cases selected")
    benign = BenignModel(cfg.benign, seed=cfg.seed)
    adapters = build_adapters({c.adapter for c in cases}, cfg.adapters, benign)
    if cfg.attacker not in ATTACKERS:
        sys.exit(f"[run] unknown attacker {cfg.attacker!r}; registered: {sorted(ATTACKERS)}")

    def new_attacker():   # the only place the attacker is built; a fresh one per case (no memory across cases)
        return ATTACKERS[cfg.attacker](**cfg.attacker_args)

    out_dir = Path(cfg.output_dir) / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.config, out_dir / "config.yaml")   # settings as written
    effective = asdict(cfg) | {"runners": args.runners}
    (out_dir / "effective_config.yaml").write_text(   # settings after CLI overrides
        yaml.safe_dump(effective, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[run] {len(cases)} cases, B={cfg.budget}, T={cfg.benign.timeout_s}s, "
          f"benign={benign.name}, attacker={cfg.attacker} -> {out_dir}")

    with JsonlLogger(out_dir) as log:
        for n, case in enumerate(cases, 1):
            res = run_case(case, adapters[case.adapter], new_attacker(), cfg.budget, log)
            log.log_result(res)
            status = "success" if res.success else ("ERROR" if res.end_reason == "error" else "fail")
            print(f"  [{n}/{len(cases)}] {case.case_id}: {status} after {res.attempts_used}", flush=True)

    print(format_table(summarize(out_dir)))


if __name__ == "__main__":
    main()
