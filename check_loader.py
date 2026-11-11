"""Step 1 check: load all data and print counts / sanity checks.
Usage: python check_loader.py data/*.jsonl
"""
import sys
from collections import Counter
 
from core.loader import load_cases
 
EXPECTED = {"agentdojo": 198, "agentdyn": 180, "injecagent": 1054, "bipia": 2500}
 
paths = sys.argv[1:]
cases = load_cases(paths)
counts = Counter(c.runner for c in cases)
 
print("== counts per runner")
for r, n in sorted(counts.items()):
    flag = "OK" if EXPECTED.get(r) == n else f"expected {EXPECTED.get(r)}"
    print(f"  {r:<11} {n:>5}  {flag}")
print(f"  {'total':<11} {len(cases):>5}")
 
print("== sanity checks")
ids = [c.case_id for c in cases]
print("  duplicate case_id :", len(ids) - len(set(ids)))
print("  empty goal        :", sum(not c.goal for c in cases))
bipia = [c for c in cases if c.runner == "bipia"]
print("  bipia goal w/ code:", sum("```" in c.goal for c in bipia), "/", len(bipia))
 
print("== one example per runner")
shown = set()
for c in cases:
    if c.runner not in shown:
        shown.add(c.runner)
        print(f"\n[{c.runner}] {c}")