# M1 retrieval

M1 = retrieval-augmented generation: before writing code, the model is given the 4 most relevant chunks from a reviewed
guidance corpus. M0 (plain-prompt baseline) is the same generator with no retrieval and no verification loop.

## Corpus

`model1_rag_generator/backend/rag_corpus/`: 98 short chunks in 11 files (FastAPI basics, Pydantic v2, CRUD, identity and
access control, workflows and state machines, money and time, external calls, OWASP API security, testing, pitfalls).
General guidance only. `tests/test_rag.py` enforces that no chunk contains a private canary or hidden check name, and
that no chunk shares three consecutive non-trivial code lines with any benchmark reference app. The guard caught two
harmless collisions (a generic example test name, a standard not-blank validator); both were reworded.

## Retrieval pipeline (`model1_rag_generator/backend/app/hybrid_rag.py`)

1. BM25 keyword ranking; identifiers are split so `min_length` also matches "min length".
2. Dense ranking with `nomic-embed-text` embeddings from the local Ollama (`search_document:` / `search_query:`
   prefixes, cached on disk in `rag_index/`). Falls back to a hashed n-gram embedder when Ollama is unreachable; the
   run record names the embedder used.
3. Reciprocal rank fusion (k = 60) of the two lists plus a small boost list for chunks tagged with the task's public
   category.
4. Optional MMR diversity pass (mode `hybrid_mmr`).

Each M1 run records `retrieval.mode`, `retrieval.embedder`, `retrieval.chunk_ids` and time in its metadata.

## Evaluation (`scripts/evaluate_retrieval.py`)

50 labeled queries (`rag_eval/queries.yaml`): the 5 dev task prompts plus 45 developer-style questions, labeled before
any run. Test-task prompts are excluded (enforced by a test) so retrieval is never tuned on the test set. Caveat for
the report: the same person wrote the corpus and the labels, so absolute scores are optimistic; the comparison
between modes is the useful part.

Results with `nomic-embed-text` (run on the team's PC, Sep 24), next to the hash fallback for the dense part:

| Mode | recall@4 | hit@4 | MRR@10 | nDCG@4 | recall@4 with hash fallback |
| --- | --- | --- | --- | --- | --- |
| BM25 (keywords) | 0.759 | 0.900 | 0.802 | 0.726 | 0.759 (same, no embeddings used) |
| Dense (meaning) | 0.811 | 0.960 | 0.901 | 0.795 | 0.769 |
| Hybrid (RRF), M1 default | 0.805 | 0.940 | 0.864 | 0.790 | 0.780 |
| Hybrid + MMR diversity | 0.770 | 0.940 | 0.861 | 0.755 | 0.670 |

Decision: keep `hybrid` as the M1 default.

- Dense and hybrid tie on recall@4 (0.811 vs 0.805; one relevant chunk across 50 queries), and recall@4 is the metric
  that matters because all 4 chunks go into the prompt regardless of order.
- Per query they split 5 to 4. Hybrid is better on the dev task prompts, which are what M1 actually sends
  (q01 0.4 vs 0.2, q02 0.75 vs 0.25; dense better on q03). Keywords rescue exact-identifier queries (q33 SSRF url
  field: hybrid 1.0, dense 0.0).
- MMR diversity lowers recall with both embedders: it drops the second of two correct chunks that look alike
  (q25 Decimal money / float pitfall, q40 password hashing / no secrets out).
- Real embeddings help: dense recall@4 rose from 0.769 (hash) to 0.811 (nomic).

With 50 queries, differences of about 0.02 are within noise; report them as ties.
