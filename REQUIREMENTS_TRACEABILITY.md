# Requirements Traceability

Status labels: `IMPLEMENTED` means the code exists; `TESTED` means a test was run successfully in this environment; `BLOCKED` means required dependencies or runtime were unavailable here. Update the status after full local integration tests.

| Requirement | Implementation | Evidence / test | Current status |
|---|---|---|---|
| R1 Knowledge retrieval | `app/rag.py`, `app/db.py` | `tests/test_rag_helpers.py`; full Chroma query requires installed runtime dependencies | IMPLEMENTED; FULL RAG TEST BLOCKED HERE |
| R2 Citations on factual answers | `app/workflow.py`, `app/rag.py` | API schema tests; manual citation review required | IMPLEMENTED; SOURCE SUPPORT NEEDS LOCAL REVIEW |
| R3 Abstain when evidence is missing | `app/workflow.py` | RAG workflow branches; evaluation set NA-01 to NA-03 | IMPLEMENTED; LIVE RETRIEVAL TEST BLOCKED HERE |
| R4 Source versions/conflicts | `app/policy.py`, `app/tools.py` | `tests/test_policy.py`; synthetic conflict scenarios in `data/evaluation_set.json` | TESTED UNIT PATHS |
| R5 Deterministic tools and source-linked thresholds | `app/tools.py`, `app/db.py` | `tests/test_data_tools.py`, `scripts/evaluation_oracle.py` | TESTED |
| R6 Multi-step/what-if | `app/workflow.py` | `MULTI-01` in evaluation set | IMPLEMENTED; FULL RAG EVAL BLOCKED HERE |
| R7 Identity/privacy | `app/workflow.py`, `app/tools.py` | `tests/test_workflow_api.py`, PRIV-01 to PRIV-03 | TESTED PERSONAL PATHS |
| R8 Document text is untrusted | `app/llm.py`, workflow controls | Dedicated malicious-content fixture and safe prompt; verify with real local model | IMPLEMENTED; REAL MODEL ADVERSARIAL TEST NOT RUN HERE |
| R9 Answer typing | `app/main.py`, `app/workflow.py` | Workflow/API tests | TESTED COVERED PATHS |
| R10 Auditability | `app/db.py`, `app/workflow.py`, `/audit/{trace_id}` | API/source tests; audit should be reviewed after full run | IMPLEMENTED |
| R11 Live ingestion | `app/main.py`, `app/rag.py` | `POST /ingest`; stage test in `tests/test_ingestion.py` | IMPLEMENTED; LIVE VECTOR TEST BLOCKED HERE |
| R12 Evaluation | `data/evaluation_set.json`, `scripts/evaluate.py`, `scripts/evaluation_oracle.py` | `python scripts/evaluate.py --check-only`; independent oracle | DATASET/ORACLE TESTED; FULL API EVALUATION NOT RUN HERE |
| Exact API contract | `app/main.py` | `tests/test_workflow_api.py` | COVERED PATHS TESTED |
| Annex B Source Register | `data/source_register.csv`, `app/main.py` | `tests/test_source_metadata.py` | TESTED |
| Annex C SQLite schema and loader | `app/db.py`, `scripts/load_students.py` | `tests/test_data_tools.py`, `scripts/validate_students.py` | TESTED |
| Annex D audit record | `app/db.py` | `GET /audit/{trace_id}` | IMPLEMENTED; validate with running API |
| Annex E data card | `data/data_card.md` | Manual review | IMPLEMENTED |
| Minimum 3 official docs | `data/extracted/`, `data/OFFICIAL_DTU_SOURCES.md` | Source Register plus local supplied PDFs | PRESENT LOCALLY; original PDFs excluded from GitHub history due size |
| Synthetic data generation prompt/model/validation | `data/prompts/`, `scripts/generate_students.py`, `scripts/validate_students.py`, `data/data_card.md`, `reports/` | validation output | TESTED DATA PIPELINE |
| Docker/local setup | `Dockerfile`, `docker-compose.yml`, `README.md` | Docker binary unavailable in this environment | NOT RUN HERE |
| Streamlit UI | `frontend/streamlit_app.py` | package unavailable in this environment | NOT RUN HERE |
