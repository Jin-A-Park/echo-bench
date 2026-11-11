"""Append-only jsonl logs: one line per attempt, one line per finished case."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .schema import Attempt, Result


class JsonlLogger:
    def __init__(self, out_dir: str | Path):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._attempts = open(self.dir / "attempts.jsonl", "a", encoding="utf-8")
        self._results = open(self.dir / "results.jsonl", "a", encoding="utf-8")

    def log_attempt(self, a: Attempt) -> None:
        self._write(self._attempts, asdict(a))

    def log_result(self, r: Result) -> None:
        self._write(self._results, asdict(r))

    @staticmethod
    def _write(f, row: dict) -> None:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()   # keep logs usable if a long run crashes

    def close(self) -> None:
        self._attempts.close()
        self._results.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
