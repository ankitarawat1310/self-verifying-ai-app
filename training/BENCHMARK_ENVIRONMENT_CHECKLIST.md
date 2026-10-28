# Ankita and Kapil: benchmark preparation checklist

Status: planning only. No Harbor installation, sandbox creation, benchmark run,
cloud purchase or public result upload has been performed by this checklist.

## 1. Confirm where evaluation will run

Suggested division: Ankita records the evaluation protocol and results; Kapil
confirms lab hardware, model serving and sandbox availability.

- [ ] Confirm lab operating system, RAM, free disk and GPU/VRAM.
- [ ] Confirm permission to use Docker or another Harbor-supported sandbox.
- [ ] Resolve the earlier report that Docker is unavailable in the lab.
- [ ] Confirm whether model inference and task containers share resources.
- [ ] Confirm storage for checkpoints, environment images and evaluation logs.

Run these diagnostic commands on the intended evaluation machine, one at a time.
A missing-command error means that dependency is not available there; it is not
a reason to install software without lab approval.

```text
python --version
nvidia-smi
docker version
docker info
harbor --version
harbor run --help
```

Docker version must show a functioning server, not merely an installed client.
Harbor's current local quickstart lists Python 3.12+ and Docker prerequisites.
Pin a compatible Harbor version after checking the lab environment. Do not modify
the working fine-tuning environment unnecessarily; use a separate evaluation environment.

If Docker is unavailable, ask the lab administrator about an approved supported
sandbox. Cloud providers may incur costs and require credentials; get approval
before provisioning anything. Never execute benchmark commands directly on the host.

## 2. Freeze the evaluation materials

- Benchmark: Terminal-Bench 2.1.
- Task inventory: training/terminal_bench_2_1.json, 89 tasks.
- Source revision: 7131e4375048a0e408a8fb404b5f499d726b695b.
- [ ] Pin the actual task checkout/artifact to this revision and record its identity.
- [ ] Verify that a Harbor Hub artifact, if used, matches the intended task version.
- [ ] Do not substitute a moving latest artifact without recording and approving a change.
- [ ] Keep instructions/tests/oracle solutions outside training and RAG directories.

The task list is recorded, but executable environments have not been validated.
The existing overlap checks are heuristic; do not claim the training corpus is
proven free of all benchmark contamination.

## 3. Make base-versus-fine-tuned comparisons fair

Plan eight conditions: four base models and their four fine-tuned counterparts.
Use the same agent harness and configuration for each paired comparison, including
system prompt, tools, task versions, resource limits, timeout policy, token/step
budgets, decoding policy and number of attempts. Record any necessary differences.

- [ ] Obtain four exact model/tokenizer revisions and adapter hashes from Kapil.
- [ ] Confirm the inference server can load each adapter and expose the expected API.
- [ ] Confirm the agent can parse each model's action/tool-call format.
- [ ] Choose and pin the agent version, serving stack and prompt template.
- [ ] Choose attempt count, seeds, concurrency and compute budget before scoring.
- [ ] Decide a uniform infrastructure retry policy before seeing results.
- [ ] Select fine-tuned checkpoints using validation data, never benchmark scores.

If different SVAGA pipelines are assigned to different models, the comparison
mixes model and pipeline effects. Record pipeline identity and avoid attributing
the whole difference to fine-tuning. Standalone spec/test generators need an
end-to-end agent workflow before they can attempt terminal tasks.

## 4. Check the wiring before a scored run

First test the model endpoint and agent on a non-benchmark diagnostic task. That
is an infrastructure smoke test, not a new research benchmark. If using a benchmark
task for an environment check, log it and do not tune the model on its answer.

- [ ] Endpoint responds and the correct base model/adapter is loaded.
- [ ] Sandbox starts, enforces its resource limits and runs its verifier.
- [ ] Agent actions and terminal feedback are recorded correctly.
- [ ] Raw verifier outcome, exit status and errors are saved.
- [ ] No oracle solutions or hidden tests are exposed to the agent.
- [ ] Start with concurrency 1 until resource use is understood.

Use the installed version's harbor run --help to finalize the run command after
the endpoint, agent, versioned dataset and sandbox are known. This checklist
intentionally does not invent those missing settings or supply a runnable full job.
Do not use public-upload flags; coursework evaluation does not require public release.

## 5. Run and report without changing the scoring rules

Use BENCHMARK_RESULTS_TEMPLATE.md for each condition. Preserve raw job/trial outputs.
For a single-attempt complete run, report successes divided by all 89 planned tasks.
Do not drop infrastructure errors from the denominator to improve the score.
Report errors separately, and apply any predefined retry policy uniformly.

For repeated trials, report task-averaged success frequency over the same number
of attempts per task; do not label best-of-many success as single-attempt accuracy.
Use the task's official success definition; preserve raw rewards rather than
assuming any positive reward is a complete success. If evaluation is incomplete,
report coverage and observed counts, not a complete benchmark score.

Report runtime separately from correctness. A lower training loss or a fluent
answer is not evidence that a benchmark task passed. Terminal-Bench does not by
itself certify secure, production-ready full-stack applications.

## First action now

Send Kapil the diagnostic commands in section 1 and ask for the outputs, the four
model IDs and whether an approved sandbox is available. Keep credentials private.
We can finalize the runnable evaluation configuration once these are known.

## Official references checked

- https://github.com/harbor-framework/terminal-bench-2-1
- https://github.com/harbor-framework/docs/blob/main/quickstart.mdx

The current official submission workflow differs from a private coursework run;
do not claim leaderboard comparability without meeting its current protocol.
