# Experimental repair subset policy v1

Purpose: a larger, explicitly unverified repair-action imitation experiment after the four-example smoke test. This is not a certified repair dataset or the final 10K training release.

Include only original split members with at most 4,096 total tokens measured by pinned Qwen2.5-Coder-1.5B-Instruct tokenizer (revision 2e1fd397ee46e1388853d2af2c993145b0f1098a), a valid nonempty target boundary, and either no detected v3 audit signal or an existing human restricted-use decision. The latter is an explicit exception limited to the already reviewed examples.

Exclude rejected/needs-investigation decisions, immediate shell-failure holds, other flagged pending cases, and examples outside the length audit. No automatic human sign-off, success inference, truncation, duplication or source modification. A lack of flags is not proof that an action works. `training_approved: false` remains the broad approval status; `usage: experimental_imitation` identifies the limited selection policy, not certification.

Keep existing task/duplicate-cluster split boundaries. Validation is development monitoring only, never optimizer input or a fresh final benchmark. Context is the original prefix before the selected action. Later trace observations belong only in audit evidence. Training must mask context labels and predict the final assistant target only. Do not execute the embedded commands.

## Using the package

`train.jsonl` and `validation.jsonl` contain selected records with provenance and messages. `selection.audit-only.jsonl` records inclusion/exclusion across all candidates and must not be used as training text. `manifest.json` pins inputs, policy, counts and hashes.

For the next Colab run, use a fresh base plus fresh adapter with the same tested configuration. First measure a short multi-example run and verify saving/checkpointing before the full epoch. Do not resume the four-example adapter for a purported fresh comparison. Record pre/post development loss, actual steps, skipped steps, memory, runtime, and adapter artifacts. Loss improvement alone does not demonstrate functioning repairs.

## Limits

Unknown outcomes, imperfect shell-output parsing and undetected semantic duplicates remain possible. Source licensing and final benchmark contamination review are separate from this filtering step. The subset emphasizes short sed-based edits and does not cover complete secure-app generation, all 10K records, or all four planned approaches. External benchmark evaluation and broader data extraction remain separate work.
