# Benchmark authoring scripts

Source of truth for the v1 task packages. Each script writes public task.yaml, private.yaml (hidden check list derived
from the checks' docstrings; existing canaries are kept), checks/test_hidden.py and reference/app.py.

    cd scripts/benchmark_authoring
    python crud.py          # 4 data-rule / access-control tasks
    python approval.py      # 4 workflow-state tasks
    python connector.py     # 4 external-service tasks
    cd ../..
    python scripts/validate_benchmark.py --repeat 3

Edit the scripts, not the generated files, so a regeneration never loses a change.

Once a task has a REVIEW.md (manual review done), these scripts skip it and its files become the source of truth.
Edit reviewed tasks directly. SVAGA_FORCE_REGENERATE=1 overrides this and would discard review changes.
