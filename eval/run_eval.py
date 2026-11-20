"""Measure tool selection of the live agent against eval/tool_selection.jsonl.

Requires GROQ_API_KEY (calls the real model; makes one or more requests per
query). Conversation history is not saved (the agent only reads from a throwaway database).

    GROQ_API_KEY=... python eval/run_eval.py
    GROQ_API_KEY=... python eval/run_eval.py --delay 2 --limit 5

Raw per-query results go to eval/results/<timestamp>.json.

Metrics
  tool_selection_exact  the set of tools the model tried to call equals the expected set
  args_ok               for queries with expected_args, the validated arguments contain the
                        expected key/values (checked only when the tool was selected)
  invalid_calls         tool calls rejected by argument validation (the model then retries)
"""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The agent reads history from the conversation DB; point it at a throwaway file.
os.environ["ERP_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "eval.db")

from app.agents import erp_agent  # noqa: E402
from app.memory import conversation_store as mem  # noqa: E402

DATASET = Path(__file__).with_name("tool_selection.jsonl")
RESULTS_DIR = Path(__file__).with_name("results")


def load_cases(limit=None):
    cases = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    return cases[:limit] if limit else cases


def args_match(expected, actual):
    return all(actual.get(k) == v for k, v in expected.items())


def score_case(case, result):
    attempted = [c["name"] for c in result.tool_calls]
    selected_ok = set(attempted) == set(case["expected_tools"])

    args_ok = None
    for tool, expected in case.get("expected_args", {}).items():
        calls = [c for c in result.tool_calls if c["name"] == tool and c["status"] != "invalid_arguments"]
        ok = any(args_match(expected, c["arguments"]) for c in calls)
        args_ok = ok if args_ok is None else (args_ok and ok)

    return {
        "id": case["id"],
        "query": case["query"],
        "expected_tools": case["expected_tools"],
        "attempted_tools": attempted,
        "tool_selection_exact": selected_ok,
        "args_ok": args_ok,
        "invalid_calls": sum(c["status"] == "invalid_arguments" for c in result.tool_calls),
        "agent_status": result.status,
        "tool_calls": result.tool_calls,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--delay", type=float, default=1.0, help="seconds to wait between queries")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N queries")
    opts = parser.parse_args()

    if not os.getenv("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY is not set. This eval calls the live model; see the docstring.")

    mem.init_db()
    rows = []
    for case in load_cases(opts.limit):
        try:
            result = erp_agent.run_agent(
                case["query"], "S001", f"eval-{case['id']}", "Arjun Sharma", "10-A"
            )
            row = score_case(case, result)
        except Exception as exc:  # keep going; record the failure
            row = {"id": case["id"], "query": case["query"], "tool_selection_exact": False,
                   "args_ok": None, "invalid_calls": 0, "agent_status": "exception", "error": str(exc)}
        rows.append(row)
        print(f"{'PASS' if row['tool_selection_exact'] else 'FAIL'}  {row['id']}: {row.get('attempted_tools')}")
        time.sleep(opts.delay)

    arg_rows = [r for r in rows if r["args_ok"] is not None]
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": erp_agent.MODEL,
        "queries": len(rows),
        "tool_selection_exact": sum(r["tool_selection_exact"] for r in rows),
        "args_checked": len(arg_rows),
        "args_ok": sum(bool(r["args_ok"]) for r in arg_rows),
        "invalid_calls": sum(r["invalid_calls"] for r in rows),
        "errors": sum(r["agent_status"] != "ok" for r in rows),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"summary": summary, "results": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"raw results: {out}")


if __name__ == "__main__":
    main()
