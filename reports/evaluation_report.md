# Evaluation Report — 23 October 2026

## Status

**The evaluation set and independent deterministic-tool oracle pass structural checks. Full end-to-end RAG/LLM evaluation has not been run in this environment.** Do not present this report as a full-stack accuracy result.

## Verified locally in the available environment

- **Evaluation set:** 29 unique cases; required categories and independent tool-value oracles are present (`python scripts/evaluate.py --check-only`).
- **Independent tool oracle:** PASS for 7 tool-oriented cases, computed independently from raw CSV values (`python scripts/evaluation_oracle.py`).
- **Synthetic data validator:** PASS — 30 fictional students, 6 courses, 90 attendance rows and 90 result rows; 2 programmes and 2 admission batches; no schema/logical violations reported (`python scripts/validate_students.py --dir data/test_students/`).
- **Automated unit/API tests:** The prior recorded baseline was 32 passed (`python -m pytest -q`) before the recent general-Qwen routing change. Seven new routing/relevance regression tests have since been added but have not been executed in this environment. Treat the latest test status as pending until rerun.
- **API module import:** PASS (`import app.main`).

## Not verified here

- Full live API evaluation against persistent ChromaDB and Sentence Transformers.
- Streamlit UI running in the target environment.
- Actual Qwen inference through Ollama, including the general-knowledge route.
- Execution of the seven newly added routing/relevance regression tests.
- Live `/ingest` retrieval end-to-end against a running vector store.
- Manual verification that every generated citation supports the claim on the cited original PDF page.
- Latency p50/p95 and real-model token counts.

These integration checks could not be completed here because ChromaDB, Sentence Transformers, Streamlit, LangGraph and Docker are not installed/available in the environment. No unexecuted tests are counted as passed, and no accuracy or latency percentages are claimed.

## Reproduce the available checks

Run from the project root:

```bash
python -m pytest -q
python scripts/validate_students.py --dir data/test_students/
python scripts/evaluate.py --check-only
python scripts/evaluation_oracle.py
```

For the full evaluation, install `requirements.txt`, start ChromaDB-backed API and the desired local Ollama model, then run:

```bash
python scripts/evaluate.py
```

The live evaluation script records failed/unavailable calls as errors rather than successful answers. Citation-support review still requires checking the real source passage and page visually. OCR-derived ordinance text may contain errors; use the original PDF as the final reference.
