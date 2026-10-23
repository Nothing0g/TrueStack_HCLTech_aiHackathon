# Ten-minute hackathon demo guide

Run this from the project root. Use fictional test students only.

## Before the demo

1. Start Docker with `docker compose up --build` and wait for `GET /health` to report ChromaDB ready. The example defaults to `MOCK_LLM=false`; verify Ollama answers `ollama list` and contains `qwen2.5:7b`. If testing without live inference, temporarily set `MOCK_LLM=true` and explain that real Qwen answers are disabled.
2. Open `http://localhost:8501`. Keep `http://localhost:8000/docs` available for API verification.
3. Confirm `GET /sources` lists three official DTU sources and two synthetic demo sources. Synthetic citations must show a visible synthetic label.
4. Check `reports/data_validation.txt` and run `python -m pytest -q`.

## Suggested run of show

- **0:00–0:45 — Problem and architecture.** Explain one LangGraph workflow, RAG for documents, Python/SQLite for calculations and a local LLM for explanations.
- **0:45–1:15 — General Qwen route.** Ask “Explain machine learning in simple terms.” Show that ordinary knowledge questions can be answered directly without pretending the answer is official university policy.\n- **1:15–2:30 — Official policy.** Ask about the base B.Tech attendance requirement. Open the citation and visually verify clause R.1(B).22 in the supplied ordinance PDF. Explain that exception/condonation is conditional, not automatic.
- **2:30–4:00 — Personal record.** Select synthetic student `S1001`, ask for attendance in `CS201`, and show the calculated percentage from class counts.
- **4:00–5:00 — Eligibility.** Ask if the student satisfies the documented attendance condition. Show the rule ID, source clause and deterministic tool call.
- **5:00–5:45 — Not found.** Ask about an unsupported topic such as a scholarship programme not in the corpus. Confirm the exact required abstention message.
- **5:45–7:00 — Synthetic conflict.** Explicitly ask about the *synthetic demo* attendance policy. Show that the synthetic Level 2 circular supersedes only the synthetic baseline. Keep the synthetic badge visible; do not imply this is a real DTU amendment.
- **7:00–8:30 — Live ingestion.** Upload a small test policy with valid Annex B metadata, query its distinctive clause without restarting, and show the returned citation.
- **8:30–9:15 — Privacy.** While using `S1001`, ask for `S1002`'s records. Show refusal and confirm no personal-data tool ran.
- **9:15–10:00 — Audit and tests.** Open the trace record and show source IDs, tools, applied rules, answer type and timing. State measured results only if the evaluation has actually been run.

## Important demonstration rules

- Never use a real student's personal data.
- The placement policy supplied is specifically for the 2025–26 passing-out batch; do not generalise it to another cohort.
- Company-specific CGPA cutoffs are not a universal DTU rule.
- The synthetic attendance, placement and supplementary examples are for software demonstration only.
- OCR extracted text may contain mistakes. Verify any quoted clause against the visual source PDF.
