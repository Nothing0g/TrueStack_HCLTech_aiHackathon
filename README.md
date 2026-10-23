# TrueStack — HCLTech AI Engineer Hackathon

**AI-Powered University Student Services Assistant**  
Local-first RAG + deterministic Python tools + one LangGraph workflow.

## Get the complete source

Download the source bundle attached in this repository: **[truestack-source-bundle.tar.gz](./truestack-source-bundle.tar.gz)**. Extract it and open the `TrueStack_HCLTech_aiHackathon/` folder.

If you only want to inspect the source files online, the bundle contains the complete implementation, documentation, test suite, synthetic data kit and evaluation assets.

## Local run

Requirements: Python 3.11/3.12 recommended; Docker Desktop + Docker Compose for the container route; Ollama and the configured model for real local-model answers. The app can also be exercised with `MOCK_LLM=true` for pipeline/testing work.

### Docker route

1. Install/start Docker Desktop.
2. Install Ollama locally and run `ollama pull qwen2.5:7b-instruct` if using real model inference.
3. Copy `.env.example` to `.env`. Keep `MOCK_LLM=true` for a quick mock-mode smoke test, or set it to false after Ollama is ready.
4. Run `docker compose up --build`.
5. Open Streamlit at http://localhost:8501 and API docs at http://localhost:8000/docs.

### Native Python route

Follow the full README inside the extracted folder. It contains Windows PowerShell and Linux/macOS commands, data loading and generation, tests, evaluation, ingestion, and troubleshooting.

## Data provenance

The bundle contains three user-supplied DTU source PDFs as local files in the original project bundle, page-anchored extracted text for indexing, and a Source Register. OCR-derived text can contain errors; citations should be checked against the corresponding PDF page before real-world use.

All bundled student records are fictional. Synthetic policies are visibly marked as **SYNTHETIC DEMO — NOT OFFICIAL DTU POLICY** and must not be used for real academic decisions.

## Honest implementation status

The repository bundle includes a pytest suite and evaluation kit. Unit tests in the build environment passed, but the complete Docker + ChromaDB + Sentence Transformers + Ollama end-to-end run was not verified in that environment. Run the setup and acceptance tests on your machine before presenting the application as fully operational.

## Architecture

`Streamlit → FastAPI/Pydantic v2 → LangGraph → (Sentence Transformers + persistent ChromaDB) and deterministic Python tools + SQLite → evidence/rule/privacy checks → local Qwen/Ollama → validated answer, citations and audit trace`.

RAG retrieves source evidence; Python applies validated, source-linked rules; the LLM explains the verified inputs. Policy precedence follows applicability, explicit supersession, authority and recency. New document indexing is separate from calculation-rule activation.
