"""AST chunking and vector indexing for knowledge_base templates."""

from __future__ import annotations

import ast
import os
from pathlib import Path

from model1_rag_generator.backend.app.config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL, KNOWLEDGE_BASE_DIR

COLLECTION_NAME = "svaga_knowledge"
_MEMORY: list[tuple[str, str]] = []


def _extract_chunks(py_path: Path) -> list[str]:
    source = py_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    chunks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            segment = ast.get_source_segment(source, node)
            if segment:
                doc = ast.get_docstring(node) or ""
                chunks.append(f"# File: {py_path.name}\n# {doc}\n{segment}")
    if not chunks:
        chunks.append(f"# File: {py_path.name}\n{source[:4000]}")
    return chunks


def _use_chroma() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except ImportError:
        return False


def _embedding_function():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction, OpenAIEmbeddingFunction

    if api_key:
        return OpenAIEmbeddingFunction(api_key=api_key, model_name=EMBEDDING_MODEL)
    return DefaultEmbeddingFunction()


def get_collection():
    if not _use_chroma():
        return None
    import chromadb

    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=_embedding_function())


def ingest_reference_code(directory: str | Path | None = None) -> int:
    global _MEMORY
    directory = Path(directory or KNOWLEDGE_BASE_DIR)
    ids: list[str] = []
    documents: list[str] = []
    for py_file in sorted(directory.glob("*.py")):
        for i, chunk in enumerate(_extract_chunks(py_file)):
            cid = f"{py_file.stem}:{i}"
            ids.append(cid)
            documents.append(chunk)
    _MEMORY = list(zip(ids, documents))
    collection = get_collection()
    if collection is None:
        return len(ids)
    if not ids:
        return 0
    collection.upsert(ids=ids, documents=documents)
    return len(ids)


def memory_query(query: str, top_k: int = 3) -> list[str]:
    if not _MEMORY:
        ingest_reference_code()
    q = query.lower()

    def score(doc: str) -> int:
        return sum(1 for token in q.split() if token in doc.lower())

    ranked = sorted(_MEMORY, key=lambda item: score(item[1]), reverse=True)
    return [doc for _, doc in ranked[:top_k]]


if __name__ == "__main__":
    n = ingest_reference_code()
    print(f"Ingested {n} chunks (chroma={'yes' if _use_chroma() else 'memory'})")
