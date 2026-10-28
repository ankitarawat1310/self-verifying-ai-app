# Self Verifying AI App Generator

SVAGA is a research prototype for generating workflow applications and checking their behavior before accepting a run. This repository contains the existing platform plus the dataset preparation, fine-tuning and repair evaluation tools developed after professor feedback.

## Start here

- `docs/handover/SVAGA_After_Feedback_Main_Comparison_2026-10-27.docx`: team report comparing the original main baseline and later work.
- `training/KAPIL_30B_FINAL_HANDOVER_2026-10-26.md`: current handover covering **both** completed Qwen 1.5B and 30B runs despite the original filename.
- `training/handover-qwen3coder30b-2026-10-26.json`: completion status and result locations.

## Completed fine tuning

Both models completed 4-bit LoRA fine-tuning on the same frozen 10,000 SWE-smith repair examples, with 1,000 additional development-validation examples.

| Model | Development prediction loss before to after | Relative loss reduction | Passing executable development repairs before to after |
|---|---|---|---|
| Qwen2.5-Coder-1.5B-Instruct | 0.461682 to 0.331128 | 28.28% | 0/20 to 0/20 |
| Qwen3-Coder-30B-A3B-Instruct | 0.650869 to 0.209103 | 67.87% | 1/20 to 4/20 |

Lower prediction loss is not a repair-accuracy percentage. These are development results with affected code locations supplied. The 30B strict numerical reload comparison remains FAILED even though exported artifact identities matched. Terminal-Bench evaluation, remaining agreed models and integration of these adapters into the web console are pending. Runtime, precision, LoRA and some generation settings differed between models, so the comparison does not isolate model size.

## Project structure

- `svaga_platform/`: FastAPI application, pipeline registry, verification and release decisions.
- `model1_rag_generator/`: generator/retrieval backend components and React frontend.
- `shared/`: schemas, LLM providers, sandbox, benchmark and policy support.
- `benchmarks/`: existing project workflow benchmark and private evaluator files. Keep private files outside model prompts and retrieval ingestion.
- `training/`: dataset preparation, Colab cells/notebooks, isolated repair evaluators and handovers.
- `tests/`, `scripts/`, `docs/`: checks, utilities and project evidence/documentation.
- `data/` and `results/`: local external data and execution artifacts; bulk content is intentionally excluded from Git.

The existing M0 to M4 pipeline names describe approaches. They are not the names of four separately fine-tuned foundation models. Existing M2 and basic M3/M4 code came from the earlier main baseline.

## Run the application locally

The following PowerShell steps create a fresh environment; copied virtual environments are not portable.

```powershell
cd "C:\repositories\self-verifying-ai-app"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The example configuration selects a **scripted provider**, useful for infrastructure checks. It does not demonstrate live Qwen inference or use our trained adapters. The main provider can be configured separately; the fine-tuned adapters still need serving integration.

Start the backend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn svaga_platform.app.main:app --host 127.0.0.1 --port 8003
```

Start the frontend in another terminal:

```powershell
cd "C:\repositories\self-verifying-ai-app\model1_rag_generator\frontend"
npm ci
npm run dev
```

Open http://localhost:5303 for the console and http://127.0.0.1:8003/docs for API documentation. Application dependency files do not install the separate GPU fine-tuning runtime; use the exact software versions in the training handover for Colab.

## Restore external training artifacts

This Git repository keeps code, handovers and compact manifests. Large JSONL files, downloaded source caches, model weights, run logs and ZIP exports remain outside the source commit. A fresh Git clone will need the shared artifacts before reproducing training or inspecting full execution evidence.

Obtain the frozen dataset and adapters from the team's shared handover/repository package. Restore them to these relative locations:

- `data/prepared/swesmith-context-repair-10k-v2/` containing `train.jsonl`, `validation.jsonl` and the original manifest.
- `results/fine_tuning/qwen15b-context-10k-v2/` containing `adapter/`, `tokenizer/` and original reports.
- `results/fine_tuning/qwen3coder30b-context-10k-v1/` containing `adapter/`, `tokenizer/` and original verification evidence.
- `results/fine_tuning/qwen3coder30b-full-dev1000-20261026/` for the full 30B development comparison.
- `results/repair_eval/` and `data/evaluation/` for the saved executable evaluation and public/private task packets.

For source GitHub uploads, keep these bulk artifacts excluded. The local copied folder contains them when available; they are not removed by .gitignore. Use the team's approved artifact storage or a separate release/download location when sharing them. No hosted artifact URL has been configured in this repository yet.

Frozen dataset ZIP SHA256:
`b55b143fc41ec5dd35e1aca897168a293b83e6d83ecc698973d79318519fe3fd`

Qwen 30B revision:
`b2cff646eb4bb1d68355c01b18ae02e7cf42d120`

Qwen 1.5B revision:
`2e1fd397ee46e1388853d2af2c993145b0f1098a`

The dataset is experimental localized Python repair data, not 10,000 independently verified secure applications. Do not ingest `data/audits/` or private evaluator material into training or retrieval. Exact versions, original hashes and known limitations are recorded in the handover.

## Origin of this import

Copied from `self-verifying-ai-app-generator-clean` on 27 October 2026. The earlier platform baseline is commit `514a4add191e14532639ea0f8b236485a49c254d` of the original `ankitarawat1310/self-verifying-ai-app-generator` repository. The old Git history and remotes were not copied. This new repository has its own origin at `https://github.com/ankitarawat1310/self-verifying-ai-app`.
