from pathlib import Path

SVAGA_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = SVAGA_ROOT / "benchmarks" / "workflows"  # legacy v0 YAML tasks
TASKS_PUBLIC_DIR = SVAGA_ROOT / "benchmarks" / "public"  # v1 tasks: the only part models may see
TASKS_PRIVATE_DIR = SVAGA_ROOT / "benchmarks" / "private"  # v1 judge data: never sent to a model
TASK_SCHEMAS_DIR = SVAGA_ROOT / "benchmarks" / "schema"
RESULTS_DIR = SVAGA_ROOT / "results"
SCHEMAS_DIR = SVAGA_ROOT / "shared" / "schemas"
MODEL1_BACKEND = SVAGA_ROOT / "model1_rag_generator" / "backend"
KNOWLEDGE_BASE = MODEL1_BACKEND / "knowledge_base"
