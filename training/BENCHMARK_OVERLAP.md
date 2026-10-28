# Benchmark overlap screening

Run from the repository root with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -B training\audit_benchmark_overlap.py --dataset open-thoughts/OpenThoughts-Agent-SFT-10K --revision d0f898f7b65290c9312f59089a7e9265fdaed00c --output-dir data\audits\terminal-bench-2-1-overlap-10k
```

The command refuses to overwrite an existing output directory. Use a new audit
directory for a rerun. A directory without report.json indicates an incomplete run.

This reads all training candidates at the specified dataset revision and compares
their task IDs and initial instructions with the 89 pinned Terminal-Bench tasks.
It downloads only benchmark instructions, never oracle solutions or test scripts.
It does not execute instructions or code found in either dataset.

Outputs:

- report.json: counts, flagged rows, method, source revisions and instruction hashes.
- benchmark-instructions.audit-only.json: reference text for auditing ONLY.

IMPORTANT: Never include data/audits in training files, validation files or RAG
ingestion. Explicitly name approved training JSONL files instead of recursively
loading every JSON/JSONL file below data.

Interpretation:

- A flag is a candidate overlap, not automatically a confirmed duplicate.
- A zero-flag result is not proof of no leakage. Paraphrases, renamed variants,
  solution-only matches and base-model contamination are not fully covered.
- This check does not verify solution correctness or approve a dataset licence.
- Before a full training release, review flags and remaining provenance/semantic
  overlap risks. Keep copies of each task in one train/validation split.

Unit checks (no network or benchmark material required):

```powershell
python -B -m unittest training.test_benchmark_overlap
```
