from __future__ import annotations
from datetime import date
from typing import Any
from app.db import connect, active_rules, source_register_rows, scope_matches, batch_matches


class ToolProblem(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def _student(student_id: str | None) -> dict[str, Any]:
    if not student_id:
        raise ToolProblem("missing_identity", "A trusted X-Student-Id header is required for personal questions.")
    with connect() as c:
        row = c.execute("SELECT * FROM students WHERE student_id=?", (student_id.upper(),)).fetchone()
    if not row:
        raise ToolProblem("student_not_found", "The synthetic student record could not be found.")
    return dict(row)


def get_student_profile(student_id: str | None) -> dict[str, Any]:
    return _student(student_id)


def get_attendance(student_id: str | None, course_code: str) -> dict[str, Any]:
    student = _student(student_id)
    with connect() as c:
        row = c.execute("""SELECT a.*, c.course_name, c.programme AS course_programme
            FROM attendance a JOIN courses c USING(course_code)
            WHERE a.student_id=? AND a.course_code=?""", (student_id.upper(), course_code.upper())).fetchone()
    if not row:
        raise ToolProblem("record_not_found", f"No attendance record was found for {course_code.upper()}.")
    result = dict(row)
    result["attendance_pct"] = round(100 * result["classes_attended"] / result["classes_held"], 2)
    result["student_programme"] = student["programme"]
    return result


def get_course_result(student_id: str | None, course_code: str, exam_type: str | None = None) -> dict[str, Any]:
    _student(student_id)
    with connect() as c:
        query = """SELECT r.*, c.course_name FROM results r JOIN courses c USING(course_code)
                   WHERE r.student_id=? AND r.course_code=?"""
        args: list[Any] = [student_id.upper(), course_code.upper()]
        if exam_type:
            query += " AND r.exam_type=?"
            args.append(exam_type.upper())
        query += " ORDER BY r.exam_session DESC, CASE r.exam_type WHEN 'SUPPLEMENTARY' THEN 1 ELSE 0 END DESC LIMIT 1"
        row = c.execute(query, args).fetchone()
    if not row:
        raise ToolProblem("record_not_found", f"No result record was found for {course_code.upper()}.")
    return dict(row)


def get_cgpa(student_id: str | None) -> dict[str, Any]:
    student = _student(student_id)
    return {"student_id": student_id.upper(), "cgpa": student["cgpa"], "programme": student["programme"], "batch_year": student["batch_year"]}


def get_active_backlogs(student_id: str | None) -> dict[str, Any]:
    student = _student(student_id)
    return {"student_id": student_id.upper(), "active_backlogs": student["active_backlogs"]}


def _rule_precedence(candidates: list[dict[str, Any]], programme: str, batch_year: int, as_of_date: str) -> dict[str, Any]:
    """Resolve overlapping rule rows using the Source Precedence Policy, or fail closed."""
    sources = {source["doc_id"]: source for source in source_register_rows()}
    live: list[dict[str, Any]] = []
    for rule in candidates:
        source = sources.get(rule["source_doc_id"])
        if not source:
            continue
        if not ((source.get("effective_from") or "0001-01-01") <= as_of_date <= (source.get("effective_to") or "9999-12-31")):
            continue
        if not scope_matches(source.get("scope_programmes", "ALL"), programme) or not batch_matches(source.get("scope_batches", "ALL"), batch_year):
            continue
        live.append({**rule, "_source": source})
    if not live:
        raise ToolProblem("rule_not_found", f"No valid source-linked rule exists for {candidates[0].get('parameter', 'the requested parameter')} on {as_of_date}.")
    if len(live) == 1:
        return live[0]

    candidate_ids = {r["source_doc_id"] for r in live}
    removed: set[str] = set()
    for rule in live:
        source = rule["_source"]
        if int(source.get("authority_level", 5)) > 2:
            continue
        for item in str(source.get("supersedes", "")).split(";"):
            target = item.strip()
            if not target:
                continue
            target_doc, _, target_clause = target.partition("#")
            for older in live:
                if older["source_doc_id"] != target_doc:
                    continue
                if target_clause and older.get("source_section") != target_clause:
                    continue
                if older["source_doc_id"] != rule["source_doc_id"]:
                    removed.add(older["rule_id"])
    remaining = [r for r in live if r["rule_id"] not in removed]
    best_level = min(int(r["_source"].get("authority_level", 5)) for r in remaining)
    remaining = [r for r in remaining if int(r["_source"].get("authority_level", 5)) == best_level]
    latest = max(str(r["_source"].get("effective_from") or "0001-01-01") for r in remaining)
    remaining = [r for r in remaining if str(r["_source"].get("effective_from") or "0001-01-01") == latest]
    if len(remaining) != 1:
        raise ToolProblem("rule_conflict", "Multiple applicable rules remain after supersession, authority and recency checks.")
    return remaining[0]


def get_rule(parameter: str, student: dict[str, Any], as_of_date: str) -> dict[str, Any]:
    candidates = active_rules(as_of_date, parameter, student["programme"], int(student["batch_year"]))
    if not candidates:
        raise ToolProblem("rule_not_found", f"No active, source-linked rule exists for {parameter} on {as_of_date}.")
    return _rule_precedence(candidates, student["programme"], int(student["batch_year"]), as_of_date)


def compare(value: Any, operator: str, target: str) -> bool:
    if operator == "between":
        parts = [float(x.strip()) for x in target.split(",")]
        if len(parts) != 2:
            raise ToolProblem("invalid_rule", "The 'between' rule must contain two comma-separated numbers.")
        numeric_value = float(value)
        return parts[0] <= numeric_value <= parts[1]
    if operator in {"==", "!="}:
        try:
            left, right = float(value), float(target)
            equal = left == right
        except (TypeError, ValueError):
            equal = str(value).strip().casefold() == str(target).strip().casefold()
        return equal if operator == "==" else not equal
    try:
        left, right = float(value), float(target)
    except (TypeError, ValueError) as exc:
        raise ToolProblem("invalid_rule", "A numeric rule contains a non-numeric value.") from exc
    ops = {">=": left >= right, ">": left > right, "<=": left <= right, "<": left < right}
    if operator not in ops:
        raise ToolProblem("invalid_rule", f"Unsupported operator: {operator}")
    return ops[operator]


def check_exam_eligibility(student_id: str | None, course_code: str, as_of_date: str) -> dict[str, Any]:
    student = _student(student_id)
    attendance = get_attendance(student_id, course_code)
    rule = get_rule("min_attendance_pct", student, as_of_date)
    eligible = compare(attendance["attendance_pct"], rule["operator"], rule["value"])
    return {"student_id": student_id.upper(), "course_code": course_code.upper(), "attendance_pct": attendance["attendance_pct"], "eligible": eligible, "result": "ELIGIBLE" if eligible else "NOT_ELIGIBLE", "rule_id": rule["rule_id"], "threshold": f"{rule['operator']} {rule['value']}%", "source_doc_id": rule["source_doc_id"], "source_section": rule["source_section"], "synthetic": sources_is_synthetic(rule["source_doc_id"])}


def sources_is_synthetic(doc_id: str) -> bool:
    with connect() as c:
        row = c.execute("SELECT synthetic FROM source_register WHERE doc_id=?", (doc_id,)).fetchone()
    return bool(row and row["synthetic"] == "Y")


def check_placement_eligibility(student_id: str | None, as_of_date: str, hypothetical_backlogs: int | None = None, hypothetical_cgpa: float | None = None) -> dict[str, Any]:
    student = _student(student_id)
    cgpa_rule = get_rule("placement_min_cgpa", student, as_of_date)
    backlog_rule = get_rule("placement_max_backlogs", student, as_of_date)
    cgpa = float(hypothetical_cgpa if hypothetical_cgpa is not None else student["cgpa"])
    backlogs = int(hypothetical_backlogs if hypothetical_backlogs is not None else student["active_backlogs"])
    cgpa_ok = compare(cgpa, cgpa_rule["operator"], cgpa_rule["value"])
    backlog_ok = compare(backlogs, backlog_rule["operator"], backlog_rule["value"])
    rules = [{"rule_id": r["rule_id"], "value": f"{r['operator']} {r['value']}", "source_doc_id": r["source_doc_id"], "source_section": r["source_section"], "synthetic": sources_is_synthetic(r["source_doc_id"])} for r in [cgpa_rule, backlog_rule]]
    return {"student_id": student_id.upper(), "cgpa": cgpa, "active_backlogs": backlogs, "eligible": cgpa_ok and backlog_ok, "result": "ELIGIBLE" if cgpa_ok and backlog_ok else "NOT_ELIGIBLE", "rules": rules, "hypothetical": hypothetical_backlogs is not None or hypothetical_cgpa is not None}


def check_supplementary_eligibility(student_id: str | None, course_code: str, as_of_date: str) -> dict[str, Any]:
    student = _student(student_id)
    result = get_course_result(student_id, course_code)
    rule = get_rule("supplementary_eligible_result", student, as_of_date)
    eligible = compare(result["result"], rule["operator"], rule["value"])
    if result["result"] in {"ABSENT", "DETAINED"}:
        eligible = False
    return {"student_id": student_id.upper(), "course_code": course_code.upper(), "latest_result": result["result"], "eligible": eligible, "result": "ELIGIBLE_DEMO_ONLY" if eligible else "NOT_INDICATED_AS_ELIGIBLE", "reason": "Synthetic demo rule compares the latest result with the source-linked supplementary condition; real procedure must be verified against official documents.", "rule_id": rule["rule_id"], "source_doc_id": rule["source_doc_id"], "source_section": rule["source_section"], "synthetic": sources_is_synthetic(rule["source_doc_id"])}
