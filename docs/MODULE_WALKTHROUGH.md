# Module Walkthrough

| Module | Responsibility | Inputs / outputs | How to test | Small judge change idea |
|---|---|---|---|---|
| `app/main.py` | FastAPI endpoints, request schemas, live ingestion | HTTP input -> validated JSON | `tests/test_workflow_api.py`; open `/docs` locally | Add a harmless metadata field validation |
| `app/workflow.py` | Intent routing, access gate, LangGraph nodes, final answer state | Question/context -> response object | `tests/test_workflow_api.py`; evaluation set | Add a synonym to deterministic intent router |
| `app/rag.py` | Text extraction, OCR fallback, chunking, persistent Chroma indexing/query | File/text/query -> passages plus metadata | `tests/test_rag_helpers.py`; live ingest test | Change configurable top-k and rerun retrieval tests |
| `app/policy.py` | Applicability and source precedence | Retrieved passages + date/scope -> selected evidence/conflicts | `tests/test_policy.py` | Add a same-authority recency fixture |
| `app/tools.py` | SQL reads and deterministic computations | Authorised student ID + rule data -> structured tool output | `tests/test_data_tools.py` | Change an edge fixture, not the production threshold constant |
| `app/db.py` | SQLite schema, source metadata, rule registry and audit | Repositories -> structured rows | isolated test DB fixture | Add an audit field without logging unnecessary PII |
| `app/llm.py` | Local Ollama explanation and mock templates | Validated question/evidence -> explanation | mock path in tests; real model only when configured | Tighten output length or model timeout |
| `frontend/streamlit_app.py` | UI presentation and API requests | User input -> displayed API response | run Streamlit and exercise every control locally | Improve a response-state label |
| `scripts/generate_students.py` | AI profile generation/fallback and deterministic relational records | Prompt + rule registry -> CSV bundle | run generator then validator | Change seed to demonstrate reproducibility |
| `scripts/validate_students.py` / `scripts/load_students.py` | Data validation and idempotent CSV loading | CSV rows -> validation report/SQLite | `tests/test_data_tools.py` | Add another invalid-row validation test |
| `scripts/propose_rule.py` / `scripts/activate_rule.py` | Candidate rule lifecycle | Explicit source-linked candidate -> inactive/active rule | inspect script help then execute against test DB | Reject invalid section reference |
| `scripts/evaluate.py` | Live evaluation execution | evaluation JSON + API endpoint -> report | `python scripts/evaluate.py --check-only`, then live run | Add one expected source ID to a test case |

All outputs are operational summaries; no module is supposed to expose private chain-of-thought.
