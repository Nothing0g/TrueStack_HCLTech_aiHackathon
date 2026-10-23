# Synthetic student-data card — TrueStack Student Services Assistant

## Purpose
Exercise the Annex C schema, policy-grounded calculations, attendance boundaries, result states, backlogs, privacy checks and evaluation workflows. Every student identity and record is fictional and must never be used for real academic decisions.

## Generator and provenance
The bundled profile seed in `data/test_students/ai_profiles_seed.json` was AI-authored during project preparation. Its recorded provider/model label is `GPT-6 (AI-authored bundled fictional profile seed; exact deployment identifier unavailable)`; this does not claim a reproducible deployed model revision. The exact LLM prompt is saved verbatim in `data/prompts/student_data_generation_prompt.md`.

`scripts/generate_students.py` prefers the configured local Ollama model when available. If that model cannot be reached in `--provider auto` mode, it falls back to the bundled AI-authored profile seed and records the fallback. Course rows, per-course attendance and result rows are assembled by deterministic Python. Exact edge cases are applied by `scripts/patch_edge_cases.py` using active, source-linked rules. The validator output and run metadata are stored in `reports/`. This is a disclosed hybrid method; the LLM is not claimed to have generated exact boundary values.

## Schema enforcement
The required Annex C fields and table CSVs are preserved. `scripts/load_students.py` validates required columns, keys, programme/course consistency, attendance bounds, marks totals, result consistency and `active_backlogs` consistency. `scripts/validate_students.py` checks the required dataset size and critical rule-derived edge cases and writes `reports/data_validation.txt`.

## Dataset size
Current bundled dataset: **30 students, 6 courses, 90 attendance rows, 90 result rows, 2 programmes and 2 admission batches**. Programmes are B.Tech CSE and B.Tech Mechanical Engineering; admission batches are 2023 and 2024.

## Edge cases
- S1001 / CS201: exactly 75% attendance (75 of 100 classes), linked to the supplied B.Tech Ordinance clause R.1(B).22, PDF page 25.
- S1002 / CS201: one class below the same threshold (74 of 100 classes).
- S1003 / CS201: FAIL one mark below the 35% lower-grade cutoff in Table 4, PDF page 22. This tests the lower grade boundary; the full grade-assignment formula is not reimplemented for all synthetic records.
- S1004 / CS201: `ABSENT` result.
- S1005 / CS201: `DETAINED` result.
- S1006: multiple non-PASS outcomes/backlogs in synthetic result data.
- S1007: CGPA at the explicitly synthetic placement-demo threshold (6.0), with zero backlogs. The real DTU placement policy says CGPA cutoffs are set by company directives; it does not define one universal threshold for every student or batch.

The actual IDs, values and validation outcomes are in the generated CSVs and `reports/data_validation.txt`. If a source-linked rule changes, rerun the edge-case patch and validation before loading the dataset.

## What the LLM got wrong / corrections
When the bundled AI-authored seed is used, it contains only profile fields. Programme/batch balance is enforced by the Python generator; course assignments, attendance, marks and results are generated relationally in Python. The exact threshold boundary values are also set by Python so that they match the current rule registry. If local Ollama generation is used, the raw responses, model field, schema failures and fallback outcome are recorded when available. The validator does not silently drop invalid rows.

## Known limitations
These records do not represent a real student cohort. The simplified synthetic results do not reproduce every aspect of DTU's relative grading formula. Placement CGPA/backlog and supplementary eligibility examples are synthetic demo rules, not official DTU policy. No real student data is used.
