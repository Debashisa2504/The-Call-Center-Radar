"""
backend/pipeline/reranker.py
==============================
Cross-encoder reranker + near-duplicate deduplication.

Adapted from CortexV (app/services/chat/reranker.py).

The cross-encoder model (ms-marco-MiniLM-L-6-v2) computes a relevance
score for every (query, chunk_text) pair rather than comparing
independent embeddings.  It catches cases where two chunks have similar
embedding vectors but one is actually more relevant — the most common
failure mode of pure vector search.

Architecture
------------
rerank(query, chunks) -> sorted chunks (most relevant first)
dedup_chunks(chunks)  -> drops near-duplicates (Jaccard >= DEDUP_THRESHOLD)

The model is loaded once at startup via @lru_cache — subsequent calls
are free.  Inference runs in a thread executor to avoid blocking FastAPI's
event loop.

Usage in compliance evaluator
------------------------------
When evaluating a compliance rule, the top-K semantically similar chunks
are re-ranked against the rule description so the most policy-relevant
excerpts float to the top of the LLM prompt.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List

from ..config import RERANKER_MODEL, RERANKER_ENABLED, DEDUP_THRESHOLD

_WORD_RE = re.compile(r"\w+")


@lru_cache(maxsize=1)
def _get_cross_encoder():
    """Load model once, cache forever.  Returns None if unavailable."""
    if not RERANKER_ENABLED:
        return None
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder(RERANKER_MODEL, max_length=512)
        return model
    except Exception as exc:
        print(f"[reranker] failed to load {RERANKER_MODEL}: {exc}")
        return None


def _chunk_text(chunk: Any) -> str:
    """Extract plain text from a chunk dict or CallChunk object."""
    if isinstance(chunk, dict):
        return chunk.get("text", "") or chunk.get("contextual_text", "")
    return getattr(chunk, "text", "") or getattr(chunk, "contextual_text", "")


def rerank(query: str, chunks: List[Any]) -> List[Any]:
    """
    Score chunks against the query using the cross-encoder.
    Returns chunks sorted by relevance score descending.
    Falls back to original order on any failure.
    """
    if not chunks:
        return chunks
    model = _get_cross_encoder()
    if model is None:
        return chunks
    try:
        pairs  = [(query, _chunk_text(c)) for c in chunks]
        scores = model.predict(pairs).tolist()
        return [
            c for _, c in sorted(
                zip(scores, chunks), key=lambda x: x[0], reverse=True
            )
        ]
    except Exception as exc:
        print(f"[reranker] scoring failed: {exc}")
        return chunks


def _token_set(chunk: Any) -> set:
    return set(_WORD_RE.findall(_chunk_text(chunk).lower()))


def dedup_chunks(chunks: List[Any], threshold: float = DEDUP_THRESHOLD) -> List[Any]:
    """
    Drop near-duplicate chunks, preserving input order.

    A chunk is dropped when its token-set Jaccard similarity to an
    already-kept chunk is >= threshold (default 0.85).  When called on
    a rerank-sorted list, the higher-ranked chunk of a near-duplicate
    pair survives.

    O(n^2) but n is the rerank pool (~30), so negligible.
    """
    kept:        List[Any]       = []
    kept_tokens: List[set]       = []
    for c in chunks:
        toks = _token_set(c)
        if toks and any(
            kt and len(toks & kt) / len(toks | kt) >= threshold
            for kt in kept_tokens
        ):
            continue
        kept.append(c)
        kept_tokens.append(toks)
    return kept
