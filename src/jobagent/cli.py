"""Command line: set up data, ask the agent, and review proposed changes (human-only)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from . import db, importer, tools


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="jobagent")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create an empty database")
    s = sub.add_parser("import", help="import a CSV or Markdown tracker")
    s.add_argument("path")
    sub.add_parser("pending", help="list proposed changes")
    for name in ("approve", "reject", "rollback"):
        s = sub.add_parser(name, help=f"{name} a change (human only)")
        s.add_argument("change_id", type=int)
    s = sub.add_parser("ask", help="ask the agent a question (needs ANTHROPIC_API_KEY)")
    s.add_argument("question")
    args = p.parse_args(argv)

    if args.cmd == "init":
        print(f"created {db.init_db()}")
    elif args.cmd == "import":
        db.init_db()
        conn = db.connect_rw()
        path = Path(args.path)
        n = importer.import_csv(path, conn) if path.suffix == ".csv" else importer.import_markdown(path, conn)
        print(f"imported {n} rows")
    elif args.cmd == "pending":
        for r in tools.list_pending():
            print(f"#{r['id']} {r['company']} | {r['role']}: {r['changes']} (was {r['previous_values']}) {r['reason']}")
    elif args.cmd in ("approve", "reject", "rollback"):
        fn = {"approve": tools.approve_change, "reject": tools.reject_change, "rollback": tools.rollback_change}
        print(json.dumps(fn[args.cmd](args.change_id)))
    elif args.cmd == "ask":
        res = asyncio.run(__import__("jobagent.agent", fromlist=["ask_with_mcp"]).ask_with_mcp(args.question))
        print(res.answer)
        print(f"\n[steps={res.steps} tools={[c['name'] for c in res.tool_calls]} "
              f"tokens={res.input_tokens + res.output_tokens}]")


if __name__ == "__main__":
    main()
