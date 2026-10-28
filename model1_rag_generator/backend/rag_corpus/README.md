# M1 retrieval corpus (v1)

Reviewed, general guidance for generating small FastAPI services. One chunk per `## <id>: <title>` heading, with a
`tags:` line underneath. Rules:

- General patterns only. Nothing here may be copied from, or written to answer, a benchmark task. `tests/test_rag.py`
  fails if a chunk shares three consecutive non-trivial code lines with any benchmark reference app, or contains any
  private canary or hidden check name.
- Pydantic v2 and FastAPI current syntax only.
- Keep chunks short (under about 150 words) so four of them fit the context budget.
