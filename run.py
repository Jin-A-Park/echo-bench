"""Entry point: config -> cases -> attempt loop per case -> logs in outputs/<timestamp>/."""
from __future__ import annotations

import argparse
import shutil
import time
from collections import Counter
from pathlib import Path

from adapters import build_adapters
from attackers import ATTACKERS
from core.benign import BenignModel
from core.config import load_config
from core.loader import load_cases
from core.logger import JsonlLogger
from core.loop import run_case


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cases = load_cases(cfg.data_paths(), sample_per_runner=cfg.sample_per_runner, seed=cfg.seed)
    benign = BenignModel(cfg.benign, seed=cfg.seed)
    adapters = build_adapters({c.adapter for c in cases}, cfg.adapters, benign)
    attacker = ATTACKERS[cfg.attacker]()

    out_dir = Path(cfg.output_dir) / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.config, out_dir / "config.yaml")   # keep the settings next to the logs
    print(f"[run] {len(cases)} cases, B={cfg.budget}, T={cfg.benign.timeout_s}s, "
          f"benign={benign.name}, attacker={cfg.attacker} -> {out_dir}")

    wins: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    with JsonlLogger(out_dir) as log:
        for case in cases:
            res = run_case(case, adapters[case.adapter], attacker, cfg.budget, log)
            log.log_result(res)
            totals[case.runner] += 1
            wins[case.runner] += res.success

    print("== ASR per runner")
    for r in sorted(totals):
        print(f"  {r:<11} {wins[r]:>4}/{totals[r]:<4} {wins[r] / totals[r]:.0%}")


if __name__ == "__main__":
    main()
