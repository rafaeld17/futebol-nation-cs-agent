"""
Push the golden set to a Braintrust-hosted Dataset for browsing/annotation.

data/golden.csv remains the sole canonical, git-versioned source of truth --
edit rows there, not in the Braintrust UI. This script (and the auto-call from
evals/eval_agent.py's run_braintrust()) make the hosted copy a one-way mirror:
re-running is idempotent (upsert keyed by each row's own `id`), so the UI never
drifts from what was actually scored.

Standalone usage:
    python -m evals.sync_dataset
"""

from __future__ import annotations
import sys
from dotenv import load_dotenv

DATASET_NAME = "golden-v1"


def sync_to_braintrust(rows: list[dict] | None = None):
    """Upsert golden rows into a Braintrust Dataset; returns the Dataset object."""
    import braintrust
    from evals import eval_agent

    rows = rows if rows is not None else eval_agent.load_golden()

    ds = braintrust.init_dataset(
        project=eval_agent.PROJECT_NAME,
        name=DATASET_NAME,
        description=(
            "Synced from data/golden.csv -- golden.csv is canonical; "
            "edit there, not here."
        ),
    )
    for row in rows:
        ds.insert(
            id=row["id"],
            input=row,
            expected=row.get("expected_behavior", ""),
            metadata={k: v for k, v in row.items() if k not in {"id", "expected_behavior"}},
        )
    return ds


def main() -> int:
    load_dotenv()
    ds = sync_to_braintrust()
    print(f"Synced golden set to Braintrust dataset '{DATASET_NAME}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
