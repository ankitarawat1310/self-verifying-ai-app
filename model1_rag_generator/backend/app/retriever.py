"""M1 retrieval entry point: hybrid BM25 + embeddings over the reviewed corpus (see hybrid_rag.py).

The old ChromaDB / keyword retriever over knowledge_base/ is kept in ingest.py and simple_retriever.py for reference
but is no longer used by the pipeline.
"""

from __future__ import annotations

import os
import time
from typing import Any

from model1_rag_generator.backend.app.hybrid_rag import format_context, shared_retriever

DEFAULT_TOP_K = int(os.getenv("SVAGA_RAG_TOP_K", "4"))
# "hybrid" chosen on the 50 labeled dev queries with nomic-embed-text (Sep 24): recall@4 0.805 vs 0.811 dense
# (a tie), better on dev task prompts; MMR lowered recall@4 to 0.770. See docs/m1-retrieval.md.
DEFAULT_MODE = os.getenv("SVAGA_RAG_MODE", "hybrid")


def retrieve_with_provenance(query: str, *, top_k: int = DEFAULT_TOP_K, category: str | None = None,
                             mode: str = DEFAULT_MODE) -> tuple[str, dict[str, Any]]:
    started = time.monotonic()
    result = shared_retriever().retrieve(query, top_k=top_k, mode=mode, category=category)
    return format_context(result), {
        "mode": result.mode,
        "embedder": result.embedder,
        "chunk_ids": result.chunk_ids,
        "top_k": top_k,
        "category": category,
        "seconds": round(time.monotonic() - started, 3),
    }


def retrieve_context(query: str, top_k: int = DEFAULT_TOP_K, category: str | None = None) -> str:
    return retrieve_with_provenance(query, top_k=top_k, category=category)[0]
