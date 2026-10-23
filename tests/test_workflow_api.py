from __future__ import annotations
from fastapi.testclient import TestClient
from app.workflow import _authorize, _intake, run_workflow


def test_personal_request_without_identity_is_refused_before_data_access(test_db):
    response = run_workflow("What is my attendance in CS201?", None, "2026-10-23")
    assert response["answer_type"] == "refused"
    assert response["tools_invoked"] == []


def test_cross_student_request_is_refused_before_tool_call(test_db):
    response = run_workflow("Show S1002's attendance in CS201", "S1001", "2026-10-23")
    assert response["answer_type"] == "refused"
    assert response["tools_invoked"] == []


def test_personal_lookup_via_api_uses_header_and_calculates(test_db, monkeypatch):
    # Bypass startup's optional vector indexing; this test covers a DB-only request path.
    from app import main
    monkeypatch.setattr(main, "startup", lambda: None)
    with TestClient(main.app) as client:
        resp = client.post("/ask", json={"question": "What is my attendance in CS201?", "as_of_date": "2026-10-23"}, headers={"X-Student-Id": "S1001"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer_type"] == "calculated"
        assert "75.0%" in body["answer"]
        assert body["tools_invoked"][0]["tool"] == "get_attendance"


def test_api_rejects_blank_question(test_db, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "startup", lambda: None)
    with TestClient(main.app) as client:
        resp = client.post("/ask", json={"question": "  "})
        assert resp.status_code == 422


def test_api_source_register_endpoint(test_db, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "startup", lambda: None)
    with TestClient(main.app) as client:
        resp = client.get("/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 5
        assert any(s["doc_id"] == "DTU-BTECH-ORD-2025" for s in data["sources"])
