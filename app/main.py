from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.config import APP_NAME, DOCUMENTS_PATH, MAX_UPLOAD_MB, ROOT, MOCK_LLM, OLLAMA_BASE_URL, OLLAMA_MODEL
from app.db import connect, get_audit, init_db, seed_sources_and_rules, source_register_rows
from app.rag import delete_document, ingest_path, rag_status, read_document
from app.workflow import run_workflow

app = FastAPI(
    title=APP_NAME,
    version="1.0.0",
    description="Local-first university student-services assistant. Bundled demo policies are synthetic and not official DTU rules.",
)
ALLOWED_SUFFIXES = {".pdf", ".docx", ".md", ".txt"}
SOURCE_FIELDS = [
    "doc_id", "title", "issuer", "authority_level", "doc_type", "version", "effective_from", "effective_to",
    "supersedes", "scope_programmes", "scope_batches", "provenance", "retrieved_on", "synthetic",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    as_of_date: str | None = None

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value

    @field_validator("as_of_date")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("as_of_date must use YYYY-MM-DD") from exc
        return value


class SourceMetadata(BaseModel):
    doc_id: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=2, max_length=300)
    issuer: str = Field(min_length=2, max_length=200)
    authority_level: int = Field(ge=1, le=5)
    doc_type: Literal["regulation", "circular", "notice", "faq", "handbook", "unofficial"]
    version: str = Field(min_length=1, max_length=80)
    effective_from: str = ""
    effective_to: str = ""
    supersedes: str = ""
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    provenance: str = Field(min_length=3, max_length=2000)
    retrieved_on: str
    synthetic: Literal["Y", "N"]

    @field_validator("doc_id")
    @classmethod
    def valid_doc_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,99}", value):
            raise ValueError("doc_id may contain letters, numbers, dots, underscores and hyphens only")
        return value

    @field_validator("effective_from")
    @classmethod
    def valid_optional_effective_date(cls, value: str) -> str:
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("effective_from must use YYYY-MM-DD or be empty when the source does not state a date") from exc
        return value

    @field_validator("retrieved_on")
    @classmethod
    def valid_retrieved_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("retrieved_on must use YYYY-MM-DD") from exc
        return value

    @field_validator("effective_to")
    @classmethod
    def valid_end_date(cls, value: str) -> str:
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("effective_to must use YYYY-MM-DD or be empty") from exc
        return value

    @model_validator(mode="after")
    def effective_order(self):
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        if self.synthetic == "Y" and "SYNTHETIC DEMO" not in self.title.upper():
            raise ValueError("synthetic documents must include 'SYNTHETIC DEMO' in the title")
        return self


def _export_source_register() -> None:
    rows = source_register_rows()
    out = ROOT / "data" / "source_register.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SOURCE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in SOURCE_FIELDS})


@app.on_event("startup")
def startup() -> None:
    init_db()
    try:
        seed_sources_and_rules()
        _export_source_register()
    except Exception as exc:
        # Startup can remain available in degraded mode, but /health exposes the problem.
        print(f"RAG bootstrap deferred: {type(exc).__name__}: {exc}")
    try:
        with connect() as conn:
            has_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] > 0
        if not has_students:
            from scripts.load_students import load
            counts = load(ROOT / "data" / "test_students")
            print(f"Loaded bundled synthetic student fixture: {counts}")
    except Exception as exc:
        print(f"Synthetic student bootstrap deferred: {type(exc).__name__}: {exc}")


@app.get("/")
def root():
    return {
        "name": APP_NAME, "status": "running", "docs": "/docs",
        "notice": "Bundled policy examples are synthetic and not official DTU rules. Add official documents with source metadata through /ingest.",
    }


@app.post("/ask")
def ask(payload: AskRequest, x_student_id: str | None = Header(default=None, alias="X-Student-Id")):
    try:
        response = run_workflow(payload.question, x_student_id, payload.as_of_date)
        if response.get("_error_detail"):
            raise HTTPException(status_code=503, detail=response["_error_detail"])
        return response
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Unhandled request error: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=503, detail="Required assistant component unavailable; check /health and local logs.") from exc


@app.get("/health")
def health():
    components: dict[str, dict] = {}
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
        components["sqlite"] = {"status": "ready"}
    except Exception as exc:
        components["sqlite"] = {"status": "unavailable", "error": type(exc).__name__}
    rag = rag_status()
    components["chromadb"] = {
        "status": rag.get("status", "unknown"),
        "collection_count": rag.get("collection_count"),
        "embedding_model": rag.get("embedding_model"),
    }
    if rag.get("error"):
        components["chromadb"]["error"] = rag["error"]
    if MOCK_LLM:
        components["llm"] = {"status": "mock_mode", "model": OLLAMA_MODEL, "note": "MOCK_LLM=true; no real inference is being claimed."}
    else:
        try:
            import requests
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            r.raise_for_status()
            available = [m.get("name", "") for m in r.json().get("models", [])]
            present = any(name == OLLAMA_MODEL or name.startswith(OLLAMA_MODEL.split(":")[0] + ":") for name in available)
            components["llm"] = {"status": "ready" if present else "model_missing", "model": OLLAMA_MODEL, "available_models": available}
        except Exception as exc:
            components["llm"] = {"status": "unavailable", "model": OLLAMA_MODEL, "error": type(exc).__name__}
    try:
        source_count = len(source_register_rows())
    except Exception:
        source_count = 0
    required = [components.get("sqlite", {}).get("status"), components.get("chromadb", {}).get("status")]
    overall = "ready" if all(x == "ready" for x in required) else "degraded"
    if not MOCK_LLM and components.get("llm", {}).get("status") != "ready":
        overall = "degraded"
    try:
        from app.workflow import LANGGRAPH_AVAILABLE
    except Exception:
        LANGGRAPH_AVAILABLE = False
    return {"status": overall, "api": "ready", **components, "registered_sources": source_count, "langgraph_available": LANGGRAPH_AVAILABLE}


@app.get("/sources")
def sources():
    rows = source_register_rows()
    return {"sources": rows, "count": len(rows)}


@app.get("/audit/{trace_id}")
def audit_endpoint(trace_id: str):
    record = get_audit(trace_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit trace not found")
    return record


@app.post("/ingest")
async def ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"Unsupported file type. Allowed extensions: {', '.join(sorted(ALLOWED_SUFFIXES))}")
    raw = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Upload exceeds {MAX_UPLOAD_MB} MB limit")
    try:
        metadata_json = json.loads(metadata)
        if not isinstance(metadata_json, dict):
            raise ValueError("metadata must be a JSON object")
        missing = [key for key in SOURCE_FIELDS if key not in metadata_json]
        if missing:
            raise ValueError(f"Missing Source Register fields: {', '.join(missing)}")
        m = SourceMetadata.model_validate(metadata_json).model_dump()
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid source metadata: {exc}") from exc

    DOCUMENTS_PATH.mkdir(parents=True, exist_ok=True)
    final = DOCUMENTS_PATH / f"{m['doc_id']}{suffix}"
    temp = DOCUMENTS_PATH / f".{m['doc_id']}.upload{suffix}"
    backup = None
    old_row = None
    old_path_exists = final.exists()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        with connect() as conn:
            old_db = conn.execute("SELECT * FROM source_register WHERE doc_id=?", (m["doc_id"],)).fetchone()
            old_row = dict(old_db) if old_db else None
        if old_row and old_row.get("content_sha256") == sha and old_row.get("status") == "indexed":
            return {"doc_id": m["doc_id"], "chunks_indexed": old_row.get("indexed_chunks", 0), "status": "duplicate_unchanged"}

        temp.write_bytes(raw)
        extracted_text, _ = read_document(temp)
        if len(extracted_text.strip()) < 30:
            raise HTTPException(422, "Extracted text is empty or too short. For a scanned PDF, enable OCR and install Tesseract.")
        if final.exists():
            backup = final.with_suffix(final.suffix + ".backup")
            backup.unlink(missing_ok=True)
            os.replace(final, backup)
        os.replace(temp, final)
        chunks = ingest_path(extracted_text, m, source_path=str(final), reset=True)
        with connect() as conn:
            conn.execute("""INSERT INTO source_register
                (doc_id,title,issuer,authority_level,doc_type,version,effective_from,effective_to,supersedes,scope_programmes,scope_batches,provenance,retrieved_on,synthetic,content_sha256,indexed_chunks,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title,issuer=excluded.issuer,authority_level=excluded.authority_level,
                doc_type=excluded.doc_type,version=excluded.version,effective_from=excluded.effective_from,effective_to=excluded.effective_to,
                supersedes=excluded.supersedes,scope_programmes=excluded.scope_programmes,scope_batches=excluded.scope_batches,
                provenance=excluded.provenance,retrieved_on=excluded.retrieved_on,synthetic=excluded.synthetic,
                content_sha256=excluded.content_sha256,indexed_chunks=excluded.indexed_chunks,status=excluded.status""",
                (m["doc_id"],m["title"],m["issuer"],m["authority_level"],m["doc_type"],m["version"],m["effective_from"],m["effective_to"],m["supersedes"],m["scope_programmes"],m["scope_batches"],m["provenance"],m["retrieved_on"],m["synthetic"],sha,chunks,"indexed"))
        if backup:
            backup.unlink(missing_ok=True)
        _export_source_register()
        return {"doc_id": m["doc_id"], "chunks_indexed": chunks, "status": "indexed"}
    except HTTPException:
        temp.unlink(missing_ok=True)
        if backup and backup.exists():
            final.unlink(missing_ok=True); os.replace(backup, final)
        raise
    except Exception as exc:
        temp.unlink(missing_ok=True)
        try:
            delete_document(m["doc_id"])
        except Exception:
            pass
        if backup and backup.exists():
            final.unlink(missing_ok=True); os.replace(backup, final)
            if old_row:
                try:
                    old_text, _ = read_document(final)
                    from app.rag import ingest_path as restore_index
                    restore_index(old_text, old_row, source_path=str(final), reset=True)
                except Exception as restore_exc:
                    print(f"Could not restore previous index: {type(restore_exc).__name__}: {restore_exc}")
        elif not old_path_exists:
            final.unlink(missing_ok=True)
        if old_row is None:
            with connect() as conn:
                conn.execute("""INSERT OR REPLACE INTO source_register
                    (doc_id,title,issuer,authority_level,doc_type,version,effective_from,effective_to,supersedes,scope_programmes,scope_batches,provenance,retrieved_on,synthetic,content_sha256,indexed_chunks,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (m["doc_id"],m["title"],m["issuer"],m["authority_level"],m["doc_type"],m["version"],m["effective_from"],m["effective_to"],m["supersedes"],m["scope_programmes"],m["scope_batches"],m["provenance"],m["retrieved_on"],m["synthetic"],sha,0,"failed"))
        raise HTTPException(503, f"Ingestion failed; status is not indexed ({type(exc).__name__}). Check /health and logs.") from exc


@app.get("/admin/candidate-rules")
def candidate_rules():
    with connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT candidate_id,status,created_at,validation_message FROM candidate_rules ORDER BY created_at DESC")]
    return {"candidates": rows}
