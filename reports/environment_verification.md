# Environment Verification

Date: 2026-10-23

## Checks run

| Check | Command | Outcome |
|---|---|---|
| Python API module import | `python -c "import app.main"` | PASS |
| Automated unit/API tests | `python -m pytest -q` | 32 passed; 2 non-fatal FastAPI deprecation warnings |
| Synthetic data validation | `python scripts/validate_students.py --dir data/test_students/` | PASS; 30 students, 6 courses, 90 attendance and 90 results rows |
| Evaluation-set structure | `python scripts/evaluate.py --check-only` | PASS; 26 cases and mandatory categories present |
| Independent numeric oracle | `python scripts/evaluation_oracle.py` | PASS; 7 tool cases checked independently |

## Not run

The full ChromaDB + Sentence Transformers + Streamlit + LangGraph + Ollama end-to-end stack was not launched in this environment. Those dependencies and Docker were unavailable here. Actual inference, persistent-vector retrieval after live ingestion, complete live evaluation, and citation support on every original PDF page remain target-machine verification tasks.

Do not interpret passing unit/API tests or evaluation-structure checks as a passing full-system evaluation. Report all results honestly.
