"""M1 retrieval: corpus hygiene (no benchmark answers), hybrid retrieval, embedder caching, evaluation maths."""
from __future__ import annotations

import json
import re

import httpx
import pytest
import yaml

from model1_rag_generator.backend.app.hybrid_rag import (
    BM25,
    HashEmbedder,
    HybridRetriever,
    OllamaEmbedder,
    format_context,
    load_chunks,
    tokenize,
)
from shared.benchmarks.private_loader import load_all_private_tasks
from shared.paths import SVAGA_ROOT

CHUNKS = load_chunks()


def test_corpus_loads_with_unique_ids_and_tags():
    assert len(CHUNKS) >= 90
    assert len({c.chunk_id for c in CHUNKS}) == len(CHUNKS)
    assert all(c.tags and c.text for c in CHUNKS)


def test_corpus_contains_no_private_benchmark_material():
    blob = "\n".join(c.document() for c in CHUNKS)
    for task in load_all_private_tasks():
        assert task.canary not in blob
        for check in task.hidden_checks:
            assert check["id"] not in blob, check["id"]


def _triples(lines: list[str]) -> set[tuple[str, ...]]:
    kept = [re.sub(r"\s+", " ", l.strip()) for l in lines]
    kept = [l for l in kept if len(l) >= 12 and not l.startswith(("import ", "from ", "#", "@", ")", "]"))]
    return {tuple(kept[i:i + 3]) for i in range(len(kept) - 2)}


def test_corpus_shares_no_code_with_reference_apps():
    corpus = set()
    for chunk in CHUNKS:
        corpus |= _triples(chunk.text.splitlines())
    for task in load_all_private_tasks():
        shared = corpus & _triples(task.reference_app.read_text(encoding="utf-8").splitlines())
        assert not shared, (task.task_id, sorted(shared)[:2])


def test_labeled_queries_reference_existing_chunks_and_exclude_test_tasks():
    queries = yaml.safe_load((SVAGA_ROOT / "model1_rag_generator/backend/rag_eval/queries.yaml").read_text(encoding="utf-8"))
    ids = {c.chunk_id for c in CHUNKS}
    assert len(queries["queries"]) == 50
    for q in queries["queries"]:
        assert set(q["relevant"]) <= ids, q["id"]
    split = json.loads((SVAGA_ROOT / "benchmarks/manifest/split.json").read_text(encoding="utf-8"))
    from shared.benchmarks.task_package import load_public_task
    test_prompts = {" ".join(load_public_task(t).prompt.split())[:60] for t in split["test"]}
    for q in queries["queries"]:
        assert " ".join(q["query"].split())[:60] not in test_prompts, q["id"]


def test_tokenizer_splits_identifiers():
    assert {"min_length", "min", "length"} <= set(tokenize("Field(min_length=1)"))
    assert {"stringlength", "string", "length"} & set(tokenize("stringLength"))


def test_bm25_finds_the_obvious_chunk():
    bm = BM25([c.document() for c in CHUNKS])
    scores = bm.scores("reject unknown fields extra forbid mass assignment")
    best = CHUNKS[max(range(len(scores)), key=scores.__getitem__)].chunk_id
    assert best in {"pd-forbid-extra", "pit-ignored-extra"}


@pytest.mark.parametrize("mode", ["bm25", "dense", "hybrid", "hybrid_mmr"])
def test_retriever_modes_return_k_distinct_chunks(mode):
    r = HybridRetriever(embedder=HashEmbedder())
    result = r.retrieve("interval overlap for room bookings", top_k=4, mode=mode, category="scheduling")
    # BM25 returns only chunks sharing at least one word with the query, so it may return fewer than k.
    assert 1 <= len(result.chunk_ids) <= 4 and len(set(result.chunk_ids)) == len(result.chunk_ids)
    if mode != "bm25":
        assert len(result.chunk_ids) == 4
    assert "mt-overlap" in result.chunk_ids


def test_format_context_carries_chunk_ids():
    r = HybridRetriever(embedder=HashEmbedder())
    text = format_context(r.retrieve("store passwords safely", top_k=2, mode="hybrid"))
    assert text.startswith("# --- RETRIEVED CONTEXT ---") and "[sec-password-hash]" in text


def test_ollama_embedder_uses_prefixes_and_caches(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.path == "/api/embed"
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0, float(len(t))] for t in body["input"]]})

    emb = OllamaEmbedder(model="nomic-embed-text", base_url="http://x:11434/v1", transport=httpx.MockTransport(handler),
                         cache_path=tmp_path / "cache.json")
    first = emb.embed(["alpha", "beta"], kind="document")
    again = emb.embed(["alpha"], kind="document")
    assert len(calls) == 1 and calls[0]["input"] == ["search_document: alpha", "search_document: beta"]
    assert again[0] == first[0]
    emb.embed(["alpha"], kind="query")
    assert calls[-1]["input"] == ["search_query: alpha"]


def test_evaluation_metrics():
    from scripts.evaluate_retrieval import score
    s = score(["a", "x", "b", "y", "z"], {"a", "b"})
    assert s["recall@4"] == 1.0 and s["hit@4"] == 1.0 and s["MRR@10"] == 1.0
    s = score(["x", "y", "z", "w", "a"], {"a"})
    assert s["recall@4"] == 0.0 and s["MRR@10"] == pytest.approx(0.2)
