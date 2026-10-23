from __future__ import annotations

import hashlib
import json
from datetime import date

from fastapi.testclient import TestClient


def metadata(doc_id: str = "LIVE-TEST-01") -> dict:
    return {
        "doc_id": doc_id,
        "title": "Live ingestion test notice",
        "issuer": "Test issuer",
        "authority_level": 2,
        "doc_type": "notice",
        "version": "1.0-test",
        "effective_from": date.today().isoformat(),
        "effective_to": "",
        "supersedes": "",
        "scope_programmes": "ALL",
        "scope_batches": "ALL",
        "provenance": "Synthetic automated ingestion test fixture",
        "retrieved_on": date.today().isoformat(),
        "synthetic": "N",
    }


def client_for_test(monkeypatch, tmp_path, indexed_chunks: int = 2):
    from app import main

    monkeypatch.setattr(main, "startup", lambda: None)
    monkeypatch.setattr(main, "DOCUMENTS_PATH", tmp_path / "documents")
    monkeypatch.setattr(main, "_export_source_register", lambda: None)
    monkeypatch.setattr(main, "ingest_path", lambda text, meta, source_path="", reset=False: indexed_chunks)
    monkeypatch.setattr(main, "delete_document", lambda doc_id: 0)
    return TestClient(main.app), main


def test_ingest_registers_source_and_is_idempotent(isolated_db, monkeypatch, tmp_path):
    client, main = client_for_test(monkeypatch, tmp_path)
    body = b"Test policy clause 4.2 says the fictional office opens at 09:00 each weekday."
    fields = {"metadata": json.dumps(metadata())}
    try:
        response = client.post("/ingest", files={"file": ("notice.md", body, "text/markdown")}, data=fields)
        assert response.status_code == 200, response.text
        assert response.json() == {"doc_id": "LIVE-TEST-01", "chunks_indexed": 2, "status": "indexed"}
        assert (tmp_path / "documents" / "LIVE-TEST-01.md").read_bytes() == body
        with main.connect() as conn:
            row = conn.execute("SELECT status, indexed_chunks, content_sha256 FROM source_register WHERE doc_id=?", ("LIVE-TEST-01",)).fetchone()
        assert row["status"] == "indexed"
        assert row["indexed_chunks"] == 2
        assert row["content_sha256"] == hashlib.sha256(body).hexdigest()

        duplicate = client.post("/ingest", files={"file": ("notice.md", body, "text/markdown")}, data=fields)
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "duplicate_unchanged"
    finally:
        client.close()


def test_ingest_rejects_missing_required_metadata(isolated_db, monkeypatch, tmp_path):
    client, _ = client_for_test(monkeypatch, tmp_path)
    bad = {k: v for k, v in metadata().items() if k != "provenance"}
    try:
        response = client.post(
            "/ingest",
            files={"file": ("notice.md", b"A long enough readable policy body for extraction.", "text/markdown")},
            data={"metadata": json.dumps(bad)},
        )
        assert response.status_code == 422
        assert "provenance" in response.text
    finally:
        client.close()


def test_ingest_does_not_claim_success_when_indexing_fails(isolated_db, monkeypatch, tmp_path):
    client, main = client_for_test(monkeypatch, tmp_path)

    def fail_index(*args, **kwargs):
        raise RuntimeError("simulated vector-store failure")

    monkeypatch.setattr(main, "ingest_path", fail_index)
    try:
        response = client.post(
            "/ingest",
            files={"file": ("notice.md", b"A readable policy clause for testing index failure.", "text/markdown")},
            data={"metadata": json.dumps(metadata("LIVE-FAIL-01"))},
        )
        assert response.status_code == 503
        assert "status is not indexed" in response.text
        with main.connect() as conn:
            row = conn.execute("SELECT status FROM source_register WHERE doc_id=?", ("LIVE-FAIL-01",)).fetchone()
        assert row["status"] == "failed"
        assert not (tmp_path / "documents" / "LIVE-FAIL-01.md").exists()
    finally:
        client.close()


def test_ingest_rejects_unsupported_suffix(isolated_db, monkeypatch, tmp_path):
    client, _ = client_for_test(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/ingest",
            files={"file": ("script.exe", b"not a policy", "application/octet-stream")},
            data={"metadata": json.dumps(metadata())},
        )
        assert response.status_code == 415
    finally:
        client.close()
