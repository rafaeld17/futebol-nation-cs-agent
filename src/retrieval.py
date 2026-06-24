"""
Retrieval layer: faq.md -> chunks -> embeddings -> cosine search.

The interface (`search`) is stable; the backend (numpy in-memory) is swappable
for a real vector DB without touching the agent or tools. At 23 chunks an
in-memory cosine search is exact, zero-latency, and fully offline.

Embeddings use sentence-transformers (local, free, no API key). The model is
downloaded once on first use (~90 MB) and cached by the library.
"""

from __future__ import annotations
import os
import uuid
import numpy as np
from sentence_transformers import SentenceTransformer

_EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
_THRESHOLD = float(os.getenv("RETRIEVAL_THRESHOLD", "0.50"))
_encoder: SentenceTransformer | None = None


def _model() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer(_EMBED_MODEL)
    return _encoder


def parse_faq(path: str) -> list[dict]:
    """Split faq.md on ### boundaries into one chunk per Q&A pair."""
    text = open(path, encoding="utf-8").read()
    chunks: list[dict] = []
    current_section = "General"
    block_question = ""
    block_lines: list[str] = []

    def flush(section: str, question: str, lines: list[str]) -> None:
        answer = "\n".join(lines).strip()
        if question and answer:
            chunks.append({
                "id": str(uuid.uuid4()),
                "section": section,
                "question": question,
                "answer": answer,
                "text": f"Q: {question}\nA: {answer}",
            })

    for line in text.splitlines():
        if line.startswith("### "):
            flush(current_section, block_question, block_lines)
            block_question = line.lstrip("# ").strip()
            block_lines = []
        elif line.startswith("## "):
            current_section = line.lstrip("# ").strip()
        else:
            block_lines.append(line)

    flush(current_section, block_question, block_lines)
    return chunks


def _embed(texts: list[str]) -> np.ndarray:
    return _model().encode(texts, convert_to_numpy=True).astype(np.float32)


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-9)


def build_index(chunks: list[dict]) -> np.ndarray:
    """Embed all chunks once at startup. Returns an L2-normalized matrix."""
    return _normalize(_embed([c["text"] for c in chunks]))


def search(
    query: str,
    chunks: list[dict],
    matrix: np.ndarray,
    k: int = 3,
    threshold: float | None = None,
) -> dict:
    """
    Top-k cosine search over the FAQ.

    Returns:
        {
          "chunks": [{"question", "answer", "section", "score"}, ...],
          "top_score": float,
          "in_kb": bool   # False when top score < threshold -> escalation signal
        }
    """
    if threshold is None:
        threshold = _THRESHOLD

    q_vec = _normalize(_embed([query]))[0]
    scores = matrix @ q_vec
    order = np.argsort(scores)[::-1][:k]

    top_score = float(scores[order[0]]) if len(order) else 0.0
    return {
        "chunks": [
            {
                "question": chunks[i]["question"],
                "answer": chunks[i]["answer"],
                "section": chunks[i]["section"],
                "score": round(float(scores[i]), 4),
            }
            for i in order
        ],
        "top_score": round(top_score, 4),
        "in_kb": top_score >= threshold,
    }
