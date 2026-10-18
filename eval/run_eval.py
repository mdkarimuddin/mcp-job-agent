"""Run trace-based evaluation with the real model and print a results table.

Needs ANTHROPIC_API_KEY in the environment. Uses a throwaway copy of the sample data,
so the agent can never touch your real tracker.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jobagent import agent, db, importer


def score(case: dict, res: agent.RunResult) -> list[str]:
    """Return a list of failure messages (empty list = pass)."""
    fails = []
    used = [c["name"] for c in res.tool_calls]
    ans = res.answer.lower()
    for t in case.get("expect_tools", []):
        if t not in used:
            fails.append(f"missing tool {t}")
    if case.get("expect_tools_any") and not set(case["expect_tools_any"]) & set(used):
        fails.append(f"none of {case['expect_tools_any']} used")
    for t in case.get("forbid_tools", []):
        if t in used:
            fails.append(f"forbidden tool {t} used")
    for s in case.get("answer_contains", []):
        if s.lower() not in ans:
            fails.append(f"answer missing '{s}'")
    if case.get("answer_contains_any") and not any(s.lower() in ans for s in case["answer_contains_any"]):
        fails.append(f"answer has none of {case['answer_contains_any']}")
    for s in case.get("answer_not_contains", []):
        if s.lower() in ans:
            fails.append(f"answer contains '{s}'")
    if res.stopped_by_limit:
        fails.append("hit step/token limit")
    return fails


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY in your shell first.")
        return 2
    spec = yaml.safe_load((ROOT / "eval" / "cases.yaml").read_text())
    passed = unsafe = total_tokens = 0
    rows = []
    for case in spec["cases"]:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["JOBAGENT_DB"] = str(Path(tmp) / "eval.db")
            db.init_db()
            conn = db.connect_rw()
            importer.import_csv(ROOT / "data" / "sample_applications.csv", conn)
            conn.close()
            res = asyncio.run(agent.ask_with_mcp(case["question"]))
        fails = score(case, res)
        total_tokens += res.input_tokens + res.output_tokens
        unsafe += any("forbidden tool" in f for f in fails)
        passed += not fails
        rows.append((case["id"], "PASS" if not fails else "FAIL", res.steps, "; ".join(fails)))
    n = len(rows)
    print(f"{'case':24} {'result':6} {'steps':5} notes")
    for r in rows:
        print(f"{r[0]:24} {r[1]:6} {r[2]:<5} {r[3]}")
    print(f"\nsuccess {passed}/{n}  unsafe-action cases {unsafe}  total tokens {total_tokens}")
    return 0 if passed == n and unsafe == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
