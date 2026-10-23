# Evaluation Report — Not yet run against full local stack

**Status:** evaluation dataset validated; full live API evaluation not run in this build environment.

- Evaluation set: 25 unique cases (`data/evaluation_set.json`).
- Structure check: PASS via `python scripts/evaluate.py --check-only`.
- Independent raw-CSV oracle: PASS for 7 tool-oriented cases via `python scripts/evaluation_oracle.py`.
- Synthetic data validation: PASS — 30 students, 6 courses, 90 attendance rows, 90 result rows, no reported schema/logical violations.
- Unit/API tests available in this environment: 27 passed.
- Full RAG + embedding + ChromaDB + Streamlit + real Ollama integration: **not run here** because ChromaDB, Sentence Transformers, Streamlit and Docker are unavailable in the current environment and dependency installation could not reach the package index.
- Citation-support manual review: pending. OCR-derived official source passages should be checked against the original supplied PDFs.

Run `python scripts/evaluate.py` with the local API and vector store running to create measured end-to-end metrics. The script records HTTP errors and unavailable components as errors, not passing answers. Citation support needs manual source-page review, and numerical outcomes should be compared with `reports/evaluation_oracle.json` before final submission.
