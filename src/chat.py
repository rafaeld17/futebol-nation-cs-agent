"""
Minimal CLI for Super Sub. Multi-turn: keeps conversation history so you can
demo escalation-after-N-turns and follow-ups.

    python -m src.chat

Requires ANTHROPIC_API_KEY in the environment or a .env file.
Embeddings use a local sentence-transformers model (no extra API key needed).
"""

from __future__ import annotations
import os
import sys
import braintrust
from dotenv import load_dotenv

from . import agent

BANNER = """\
=========================================================
 Futebol Nation -- Super Sub support agent  (type 'quit')
=========================================================
"""


def main() -> None:
    load_dotenv()
    if os.getenv("BRAINTRUST_API_KEY"):
        braintrust.init_logger(project=agent.PROJECT_NAME)
    print(BANNER)
    history: list[dict] = []

    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user or user.lower() in {"quit", "exit"}:
            break

        history.append({"role": "user", "content": user})
        result = agent.run(history)

        print(f"\nsuper sub > {result['reply']}\n")
        if result["escalated"]:
            esc = result["escalation"]
            print(f"  [escalated -> ticket {esc['ticket_id']} | "
                  f"reason={esc['reason']} | sentiment={esc['sentiment']}]\n")
        if result["tool_calls"]:
            print(f"  (tools: {', '.join(result['tool_calls'])})\n")

        history.append({"role": "assistant", "content": result["reply"]})


if __name__ == "__main__":
    sys.exit(main())
