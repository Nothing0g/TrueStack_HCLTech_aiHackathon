from __future__ import annotations
from app import db
from app.tools import check_exam_eligibility, check_placement_eligibility, get_attendance, get_course_result
from scripts.load_students import validate_bundle
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_fixture_meets_annex_c_minimums(test_db):
    bundle, errors = validate_bundle(ROOT / "data" / "test_students")
    assert errors == []
    assert len(bundle["students"]) >= 30
    assert len(bundle["courses"]) >= 6
    assert len({r["programme"] for r in bundle["students"]}) >= 2
    assert len({r["batch_year"] for r in bundle["students"]}) >= 2


def test_attendance_percentage_and_boundary(test_db):
    exact = get_attendance("S1001", "CS201")
    below = get_attendance("S1002", "CS201")
    assert exact["attendance_pct"] == 75.0
    assert below["attendance_pct"] == 74.0
    assert exact["classes_held"] == below["classes_held"] == 100


def test_exam_eligibility_uses_registry_threshold(test_db):
    # At 75%: >= 75 passes. One class below fails.
    assert check_exam_eligibility("S1001", "CS201", "2026-10-23")["eligible"] is True
    assert check_exam_eligibility("S1002", "CS201", "2026-10-23")["eligible"] is False
    # Change only the registry threshold, not Python code, to prove it's data-driven.
    with db.connect() as conn:
        conn.execute("UPDATE rule_registry SET value='76' WHERE rule_id='ATT-DTU-ORD-R1B22'")
    result = check_exam_eligibility("S1001", "CS201", "2026-10-23")
    assert result["threshold"] == ">= 76%"
    assert result["eligible"] is False


def test_placement_demo_rule_is_explicitly_synthetic(test_db):
    result = check_placement_eligibility("S1007", "2026-10-23")
    assert result["cgpa"] == 6.0
    assert result["eligible"] is True
    assert all(rule["synthetic"] for rule in result["rules"])


def test_result_edge_cases_are_present(test_db):
    assert get_course_result("S1003", "CS201")["result"] == "FAIL"
    assert get_course_result("S1004", "CS201")["result"] == "ABSENT"
    assert get_course_result("S1005", "CS201")["result"] == "DETAINED"
