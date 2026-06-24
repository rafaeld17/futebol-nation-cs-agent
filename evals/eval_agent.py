"""
Braintrust eval runner for the Super Sub agent.

    python -m evals.eval_agent           # full run, logged to Braintrust
    python -m evals.eval_agent --local   # print scores to stdout, no Braintrust

Loads the golden set, runs the agent per row (rebuilding multi-turn context for
conversation rows), and applies the scorers in evals/scorers.py. Scores are
sliced by `category` so you can see per-intent strengths/weaknesses.

Requires ANTHROPIC_API_KEY and (for logged runs) BRAINTRUST_API_KEY.
Embeddings use a local sentence-transformers model (no extra API key needed).
"""

from __future__ import annotations
import os
import sys
import csv
import json
import argparse
from collections import defaultdict
from dotenv import load_dotenv

from src import agent
from evals import scorers

# Re-exported for evals/sync_dataset.py and anything else importing it from
# here; src/agent.py is the single source of truth for the literal.
PROJECT_NAME = agent.PROJECT_NAME

_GOLDEN = os.path.join(os.path.dirname(__file__), "..", "data", "golden.csv")


def load_golden() -> list[dict]:
    """
    Load the golden set from data/golden.csv (Excel-reviewable; the canonical
    source of truth -- edit there, not in Braintrust). Boolean columns are
    written as TRUE/FALSE text; the two multi-turn rows carry a JSON-encoded
    `conversation` array in their own column instead of a flat `input` string.
    """
    rows = []
    with open(_GOLDEN, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            r = dict(row)
            r["expected_escalation"] = r["expected_escalation"] == "TRUE"
            r["kb_grounded"] = r["kb_grounded"] == "TRUE"
            if r.get("conversation"):
                r["conversation"] = json.loads(r["conversation"])
            else:
                r.pop("conversation", None)
            if not r.get("input"):
                r.pop("input", None)
            rows.append(r)
    return rows


def _messages_for(row: dict) -> list[dict]:
    """Multi-turn rows carry a `conversation`; single-turn rows use `input`."""
    if "conversation" in row:
        return [{"role": m["role"], "content": m["content"]} for m in row["conversation"]]
    return [{"role": "user", "content": row["input"]}]


def run_agent_task(row: dict) -> dict:
    """Task function: run the agent, return the structured trace."""
    return agent.run(_messages_for(row))


def score_row(output: dict, row: dict) -> list[dict]:
    results = []
    for fn in scorers.ALL_SCORERS:
        r = fn(output, row)
        if r["score"] is not None:
            results.append(r)
    return results


# ---------------------------------------------------------------------------
# Local runner (no Braintrust dependency) -- handy for quick iteration / CI
# ---------------------------------------------------------------------------
def run_local() -> None:
    load_dotenv()
    rows = load_golden()
    by_scorer = defaultdict(list)
    by_category = defaultdict(lambda: defaultdict(list))

    for i, row in enumerate(rows, 1):
        output = run_agent_task(row)
        for r in score_row(output, row):
            by_scorer[r["name"]].append(r["score"])
            by_category[row["category"]][r["name"]].append(r["score"])
        print(f"[{i:>2}/{len(rows)}] {row['id']:<14} "
              f"tools={output['tool_calls']} escalated={output['escalated']}")

    def avg(xs):
        return sum(xs) / len(xs) if xs else float("nan")

    print("\n=== Overall scores ===")
    for name, xs in sorted(by_scorer.items()):
        print(f"  {name:<22} {avg(xs):.3f}  (n={len(xs)})")

    print("\n=== By category (key scorers) ===")
    key = ["correct_tool_selected", "escalation_correct", "groundedness"]
    for cat, sc in sorted(by_category.items()):
        cells = "  ".join(f"{k.split('_')[0]}={avg(sc[k]):.2f}" for k in key if sc[k])
        print(f"  {cat:<26} {cells}")


# ---------------------------------------------------------------------------
# Braintrust runner
# ---------------------------------------------------------------------------
def run_braintrust() -> None:
    load_dotenv()
    from braintrust import Eval
    from evals import sync_dataset

    rows = load_golden()

    # Sync to a Braintrust-hosted Dataset on every run, so the UI always shows
    # exactly the rows that were just scored -- no separate "remember to sync"
    # step, and zero drift between data/golden.csv (canonical) and the hosted
    # copy. Cost is ~60 cheap metadata upserts, not LLM calls.
    dataset = sync_dataset.sync_to_braintrust(rows)

    def task(row: dict) -> dict:
        # `row` is the full golden row dict (passed as `input` below).
        # Multi-turn rows carry a `conversation` key; single-turn use `input`.
        return run_agent_task(row)

    def make_scorer(fn):
        # Braintrust scorer signature: (input, output, expected)
        #   input    = full golden row dict (has expected_*, category, etc.)
        #   output   = dict returned by run_agent_task (reply, tool_calls, ...)
        #   expected = expected_behavior string (human-readable; used by LLM judges)
        def _wrapped(input: dict, output: dict, expected: str):
            return fn(output, input)  # our scorers take (output, row)
        _wrapped.__name__ = fn.__name__
        return _wrapped

    # max_concurrency: the first full run blew through Anthropic's 50 req/min
    # limit (haiku for agent calls, sonnet for judge calls) because Braintrust
    # fired all 60 rows near-simultaneously -> 43/60 rows errored with 429s.
    # Throttling concurrency + retries (see Anthropic(max_retries=...) in
    # agent.py / scorers.py) keeps the run under the per-minute ceiling.
    Eval(
        PROJECT_NAME,
        data=dataset,
        task=task,
        scores=[make_scorer(fn) for fn in scorers.ALL_SCORERS],
        max_concurrency=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Run without Braintrust.")
    args = parser.parse_args()
    if args.local:
        run_local()
    else:
        run_braintrust()
    return 0


if __name__ == "__main__":
    sys.exit(main())
