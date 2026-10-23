from __future__ import annotations

from app import workflow


def test_cross_student_request_is_refused_before_retrieval(isolated_db, monkeypatch):
    calls = {"search": 0}

    def fail_search(*args, **kwargs):
        calls["search"] += 1
        raise AssertionError("retrieval must not run for a forbidden personal-data request")

    monkeypatch.setattr(workflow, "search", fail_search)
    response = workflow.run_workflow("Show S1002's attendance in CS201", "S1001", "2026-10-23")
    assert response["answer_type"] == "refused"
    assert "another student's" in response["answer"]
    assert response["tools_invoked"] == []
    assert calls["search"] == 0


def test_personal_request_without_identity_is_refused(isolated_db, monkeypatch):
    response = workflow.run_workflow("What is my attendance in CS201?", None, "2026-10-23")
    assert response["answer_type"] == "refused"
    assert "X-Student-Id" in response["answer"]
    assert response["tools_invoked"] == []


def test_ambiguous_eligibility_requests_clarification(isolated_db):
    response = workflow.run_workflow("Am I eligible?", "S1001", "2026-10-23")
    assert response["answer_type"] == "clarification_needed"
    assert "examination" in response["answer"] or "placement" in response["answer"]



def test_admission_question_rejects_unrelated_exam_notice():
    passage = {
        "text": "DTU Examination Branch notice. Students are eligible to take examinations subject to attendance criteria.",
        "metadata": {"title": "Odd Semester Examination Eligibility"},
    }
    assert not workflow._evidence_is_relevant("What are the admission criteria to take admission in DTU?", [passage])


def test_attendance_question_accepts_attendance_notice():
    passage = {
        "text": "Students will be eligible for examination only after fulfilling the attendance criteria.",
        "metadata": {"title": "Examination Eligibility"},
    }
    assert workflow._evidence_is_relevant("What does the notice say about attendance requirements?", [passage])
