"""
Tool definitions + handlers for the Super Sub agent.

Three tools:
  - search_faq        : grounded KB retrieval (RAG)
  - lookup_order      : read-only order status, with email verification
  - escalate_to_human : structured handoff (a first-class success path)

Tool SCHEMAS are Anthropic tool-use definitions. Handlers are plain Python so
they can be unit-tested and reused by the eval harness without the LLM.
"""

from __future__ import annotations
import os
import json
import uuid
import threading
from datetime import datetime, timezone
from braintrust import traced

from . import retrieval

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_KB_PATH = os.path.join(os.path.dirname(__file__), "..", "kb", "faq.md")
_ORDERS_PATH = os.path.join(_DATA_DIR, "orders.json")

# ---------------------------------------------------------------------------
# Lazy-loaded singletons (KB index built once; orders cached). Guarded by a
# lock: Braintrust's Eval() runs rows concurrently in a thread pool
# (max_concurrency=2+), and an unguarded check-then-set here is a real race --
# one thread can observe _kb_chunks already set by another thread while
# _kb_matrix is still mid-assignment, yielding None where a matrix is
# expected (numpy then coerces None into a 0-d array and matmul blows up).
# ---------------------------------------------------------------------------
_kb_chunks = None
_kb_matrix = None
_orders = None
_kb_lock = threading.Lock()
_orders_lock = threading.Lock()


def _kb():
    global _kb_chunks, _kb_matrix
    if _kb_chunks is None:
        with _kb_lock:
            if _kb_chunks is None:  # re-check: another thread may have just finished
                chunks = retrieval.parse_faq(_KB_PATH)
                matrix = retrieval.build_index(chunks)
                _kb_chunks, _kb_matrix = chunks, matrix
    return _kb_chunks, _kb_matrix


def _orders_db() -> list[dict]:
    global _orders
    if _orders is None:
        with _orders_lock:
            if _orders is None:
                _orders = json.load(open(_ORDERS_PATH, encoding="utf-8"))["orders"]
    return _orders


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
@traced
def search_faq(query: str) -> dict:
    chunks, matrix = _kb()
    return retrieval.search(query, chunks, matrix)


@traced
def lookup_order(order_id: str, email: str | None = None) -> dict:
    """
    Read-only order status. Requires an email that matches the order on file
    before returning any details -- prevents PII leakage / enumeration.
    """
    oid = str(order_id).lstrip("#").strip()
    match = next((o for o in _orders_db() if o["order_id"] == oid), None)

    if match is None:
        return {"found": False, "reason": "order_not_found"}

    if not email or email.strip().lower() != match["email"].lower():
        # Order exists, but caller can't prove ownership. Reveal nothing.
        return {"found": False, "reason": "email_mismatch"}

    return {
        "found": True,
        "order_id": match["order_id"],
        "status": match["status"],
        "placed_at": match.get("placed_at"),
        "carrier": match.get("carrier"),
        "tracking_number": match.get("tracking_number"),
        "estimated_delivery": match.get("estimated_delivery"),
        "delivered_at": match.get("delivered_at"),
        "destination_country": match.get("destination_country"),
        "items": match.get("items", []),
    }


@traced
def escalate_to_human(reason: str, summary: str, sentiment: str = "neutral") -> dict:
    """
    Hand off to a human teammate. This is a SUCCESS path, not a failure.
    In production this would create a ticket (e.g. Gorgias/Zendesk/Shopify Inbox).
    """
    return {
        "escalated": True,
        "ticket_id": f"FN-{uuid.uuid4().hex[:8].upper()}",
        "reason": reason,
        "summary": summary,
        "sentiment": sentiment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "name": "search_faq",
        "description": (
            "Search Futebol Nation's help-center knowledge base for policy and "
            "product information (shipping, returns, sizing, customization, "
            "payments, customs). ALWAYS use this before stating any policy. If "
            "the result has in_kb=false, the topic is NOT covered -- do not "
            "invent an answer; say you don't have that info and escalate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The customer's question, close to their own words as a full "
                        "question -- NOT a compressed list of keywords. This KB's retrieval "
                        "matches natural questions better than keyword fragments (e.g. pass "
                        "\"What hours is your support team available?\", not \"support hours "
                        "customer service availability\")."
                    ),
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup_order",
        "description": (
            "Look up the status of a specific order. Requires BOTH the order "
            "number and the email used at checkout. Never call this without an "
            "email -- ask the customer for it first. Returns found=false with "
            "reason 'email_mismatch' if the email doesn't match (do not reveal "
            "any order details in that case)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order number, e.g. 1024."},
                "email": {"type": "string", "description": "Email used at checkout."},
            },
            "required": ["order_id", "email"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the conversation to a human teammate. Use when: the question "
            "is out of KB scope, a risk-sensitive issue (refund, damaged/wrong/"
            "lost item, authenticity, chargeback), an account change is needed "
            "(cancel/edit/address), the customer explicitly asks for a human, or "
            "after ~2 unsuccessful attempts. Always include a concise summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short category, e.g. 'damaged_item', 'out_of_scope', 'customer_request'.",
                },
                "summary": {
                    "type": "string",
                    "description": "1-2 sentence handoff summary: intent, what was tried, key details.",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "neutral", "frustrated", "angry"],
                    "description": "Customer sentiment, to help prioritize.",
                },
            },
            "required": ["reason", "summary"],
        },
    },
]

HANDLERS = {
    "search_faq": search_faq,
    "lookup_order": lookup_order,
    "escalate_to_human": escalate_to_human,
}


def dispatch(name: str, args: dict) -> dict:
    """Route a tool call to its handler."""
    if name not in HANDLERS:
        return {"error": f"unknown tool: {name}"}
    return HANDLERS[name](**args)
