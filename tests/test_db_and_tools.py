from __future__ import annotations

from app import db
from app.tools import (
    ToolProblem,
    check_exam_eligibility,
    compare,
    get_attendance,
    get_rule,
)


def test_undated_official_rule_is_available_without_fabricating_a_date(isolated_db):
    rows = db.active_rules("2026-10-23", "min_attendance_pct", "B.Tech CSE", 2023)
    assert any(r["rule_id"] == "ATT-DTU-ORD-R1B22" for r in rows)
    rule = get_rule("min_attendance_pct", {"programme": "B.Tech CSE", "batch_year": 2023}, "2026-10-23")
    assert rule["value"] == "75"
    assert rule["source_doc_id"] == "DTU-BTECH-ORD-2025"
    assert db.source_register_rows()[0]["doc_id"]  # source register initialised


def test_attendance_is_calculated_from_counts(isolated_db):
    assert get_attendance("S1001", "CS201")["attendance_pct"] == 75.0
    assert get_attendance("S1002", "CS201")["attendance_pct"] == 74.0


def test_exam_eligibility_uses_source_linked_rule(isolated_db):
    eligible = check_exam_eligibility("S1001", "CS201", "2026-10-23")
    below = check_exam_eligibility("S1002", "CS201", "2026-10-23")
    assert eligible["eligible"] is True
    assert below["eligible"] is False
    assert eligible["rule_id"] == "ATT-DTU-ORD-R1B22"
    assert eligible["synthetic"] is False


def test_comparison_operators_and_boundaries():
    assert compare(75, ">=", "75") is True
    assert compare(74, ">=", "75") is False
    assert compare(35, ">", "35") is False
    assert compare(35, "between", "35,40") is True
    assert compare("FAIL", "==", "FAIL") is True


def test_missing_student_does_not_become_zero(isolated_db):
    try:
        get_attendance("S9998", "CS201")
    except ToolProblem as exc:
        assert exc.code == "student_not_found"
    else:
        raise AssertionError("missing student should raise ToolProblem")
