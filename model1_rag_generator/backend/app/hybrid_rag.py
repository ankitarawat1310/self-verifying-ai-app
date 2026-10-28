"""Hybrid retrieval for M1: BM25 (keywords) + dense embeddings (meaning), fused with reciprocal rank fusion,
then a maximal-marginal-relevance (MMR) pass so the final chunks are relevant AND different from each other.

Corpus: model1_rag_generator/backend/rag_corpus/*.md, one chunk per "## <id>: <title>" heading with a "tags:" line.

Embedders:
  OllamaEmbedder  nomic-embed-text through the local Ollama (/api/embed), cached on disk by content hash
  HashEmbedder    deterministic hashed character n-grams; used for tests and whenever Ollama is unreachable.
                  It is a lexical stand-in, so evaluation numbers must say which embedder produced them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

CORPUS_DIR = Path(__file__).resolve().parents[1] / "rag_corpus"
INDEX_DIR = Path(__file__).resolve().parents[1] / "rag_index"
CHUNK_RE = re.compile(r"^## ([a-z0-9-]+): (.+)$", re.M)
STOPWORDS = frozenset("a an and are as at be by for from has have if in into is it its of on or that the then this "
                      "to was were will with when must can cannot may not no".split())
MODES = ("bm25", "dense", "hybrid", "hybrid_mmr")
# Public task category -> corpus tags that get a small boost (a third ranked list in the fusion).
CATEGORY_TAGS = {
    "data_rules": {"crud", "validation", "money"},
    "access_control": {"access-control", "identity", "passwords"},
    "workflow_state": {"workflow", "state-machine"},
    "scheduling": {"scheduling", "time", "graph"},
    "external_service": {"external-service"},
}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    title: str
    tags: tuple[str, ...]
    text: str
    source: str

    def document(self) -> str:
        return f"{self.title}\n{' '.join(self.tags)}\n{self.text}"


def load_chunks(corpus_dir: Path | None = None) -> list[Chunk]:
    corpus_dir = corpus_dir or CORPUS_DIR
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        heads = list(CHUNK_RE.finditer(text))
        for i, head in enumerate(heads):
            body = text[head.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip("\n")
            lines = body.split("\n")
            tags: tuple[str, ...] = ()
            if lines and lines[0].startswith("tags:"):
                tags = tuple(t.strip() for t in lines[0][5:].split(",") if t.strip())
                lines = lines[1:]
            chunks.append(Chunk(head.group(1), head.group(2).strip(), tags, "\n".join(lines).strip(), path.name))
    ids = [c.chunk_id for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate chunk ids: {sorted(duplicates)}")
    return chunks


def tokenize(text: str) -> list[str]:
    """Lowercase words; identifiers also split on snake_case and camelCase so `min_length` matches "min length"."""
    tokens: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9_]+", text):
        parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", raw.replace("_", " "))
        words = [raw.lower()] + [p.lower() for p in parts if p.lower() != raw.lower()]
        tokens.extend(w for w in words if len(w) > 1 and w not in STOPWORDS)
    return tokens


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / max(1, len(self.lengths))
        self.k1, self.b = k1, b
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for doc, length in zip(self.docs, self.lengths):
            s = 0.0
            for t in q:
                tf = doc.get(t, 0)
                if tf:
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg))
            out.append(s)
        return out


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic, dependency-free embedding from hashed word and character-trigram features."""

    name = "hash-ngram-1024"

    def __init__(self, dims: int = 1024):
        self.dims = dims

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dims
            words = tokenize(text)
            grams = [w[i:i + 3] for w in words for i in range(max(1, len(w) - 2))]
            for feature, weight in [(w, 1.0) for w in words] + [(g, 0.5) for g in grams]:
                h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
                vec[h % self.dims] += weight if (h >> 63) & 1 else -weight
            out.append(_normalize(vec))
        return out


class OllamaEmbedder:
    """nomic-embed-text via Ollama, with task prefixes and an on-disk cache keyed by content hash."""

    def __init__(self, model: str | None = None, base_url: str | None = None, *, transport=None,
                 cache_path: Path | None = None):
        import httpx

        self.model = model or os.getenv("SVAGA_EMBED_MODEL", "nomic-embed-text")
        base = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
        self.base_url = base[:-3] if base.endswith("/v1") else base
        self.name = f"ollama:{self.model}"
        self.client = httpx.Client(base_url=self.base_url, timeout=120.0, transport=transport)
        self.cache_path = cache_path or INDEX_DIR / f"embeddings_{re.sub(r'[^a-z0-9]+', '_', self.model.lower())}.json"
        self._cache: dict[str, list[float]] | None = None

    def _load(self) -> dict[str, list[float]]:
        if self._cache is None:
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        return self._cache

    def embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        prefix = "search_query: " if kind == "query" else "search_document: "
        cache = self._load()
        keys = [hashlib.sha256(f"{self.model}|{prefix}{t}".encode()).hexdigest() for t in texts]
        missing = [(k, prefix + t) for k, t in zip(keys, texts) if k not in cache]
        if missing:
            reply = self.client.post("/api/embed", json={"model": self.model, "input": [t for _, t in missing],
                                                         "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "24h")})
            reply.raise_for_status()
            for (k, _), vec in zip(missing, reply.json()["embeddings"]):
                cache[k] = _normalize(vec)
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(cache), encoding="utf-8")
        return [cache[k] for k in keys]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def default_embedder() -> Embedder:
    """Ollama when reachable (unless SVAGA_EMBEDDER=hash), otherwise the hash fallback."""
    if os.getenv("SVAGA_EMBEDDER", "").lower() == "hash" or os.getenv("SVAGA_SCRIPTED_LLM", "").lower() in ("1", "true"):
        return HashEmbedder()
    try:
        embedder = OllamaEmbedder()
        embedder.embed(["ping"], kind="query")
        return embedder
    except Exception:
        return HashEmbedder()


@dataclass
class RetrievalResult:
    mode: str
    embedder: str
    chunks: list[Chunk]
    scores: list[float] = field(default_factory=list)

    @property
    def chunk_ids(self) -> list[str]:
        return [c.chunk_id for c in self.chunks]


class HybridRetriever:
    def __init__(self, chunks: list[Chunk] | None = None, embedder: Embedder | None = None):
        self.chunks = chunks if chunks is not None else load_chunks()
        self.embedder = embedder or default_embedder()
        self.bm25 = BM25([c.document() for c in self.chunks])
        self._doc_vecs: list[list[float]] | None = None

    @property
    def doc_vectors(self) -> list[list[float]]:
        if self._doc_vecs is None:
            self._doc_vecs = self.embedder.embed([c.document() for c in self.chunks], kind="document")
        return self._doc_vecs

    def _rank_bm25(self, query: str) -> list[int]:
        s = self.bm25.scores(query)
        return [i for i in sorted(range(len(s)), key=lambda i: -s[i]) if s[i] > 0]

    def _rank_dense(self, qvec: list[float]) -> list[int]:
        sims = [_dot(qvec, d) for d in self.doc_vectors]
        return sorted(range(len(sims)), key=lambda i: -sims[i])

    def retrieve(self, query: str, *, top_k: int = 4, mode: str = "hybrid_mmr", category: str | None = None,
                 rrf_k: int = 60, pool: int = 20, mmr_lambda: float = 0.7) -> RetrievalResult:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == "bm25":
            order = self._rank_bm25(query)
            return RetrievalResult(mode, "none", [self.chunks[i] for i in order[:top_k]])
        qvec = self.embedder.embed([query], kind="query")[0]
        dense = self._rank_dense(qvec)
        if mode == "dense":
            return RetrievalResult(mode, self.embedder.name, [self.chunks[i] for i in dense[:top_k]])
        fused: dict[int, float] = {}
        rankings = [self._rank_bm25(query)[:50], dense[:50]]
        boost_tags = CATEGORY_TAGS.get(category or "", set())
        if boost_tags:
            boosted = [i for i in rankings[0] + dense if boost_tags & set(self.chunks[i].tags)]
            rankings.append(list(dict.fromkeys(boosted)))
        for ranking in rankings:
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + rank + 1)
        order = sorted(fused, key=lambda i: -fused[i])
        if mode == "hybrid":
            picked = order[:top_k]
        else:
            candidates, picked = order[:pool], []
            top = max(fused.values()) if fused else 1.0
            while candidates and len(picked) < top_k:
                def mmr(i: int) -> float:
                    redundancy = max((_dot(self.doc_vectors[i], self.doc_vectors[j]) for j in picked), default=0.0)
                    return mmr_lambda * fused[i] / top - (1 - mmr_lambda) * redundancy
                best = max(candidates, key=mmr)
                picked.append(best)
                candidates.remove(best)
        return RetrievalResult(mode, self.embedder.name, [self.chunks[i] for i in picked], [fused[i] for i in picked])


def format_context(result: RetrievalResult) -> str:
    if not result.chunks:
        return "# --- RETRIEVED CONTEXT ---\n(none)\n# --- END RETRIEVED CONTEXT ---"
    blocks = [f"[{c.chunk_id}] {c.title}\n{c.text}" for c in result.chunks]
    return "# --- RETRIEVED CONTEXT ---\n" + "\n\n".join(blocks) + "\n# --- END RETRIEVED CONTEXT ---"


@lru_cache(maxsize=1)
def shared_retriever() -> HybridRetriever:
    return HybridRetriever()
