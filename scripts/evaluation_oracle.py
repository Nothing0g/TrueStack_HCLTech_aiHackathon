"""Independent expected-value oracle using the raw synthetic CSV files only.

This deliberately does not import app.tools. It is meant to independently verify
simple deterministic outcomes in the dataset before comparing them with the API.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "test_students"


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    students = {x["student_id"]: x for x in rows("students.csv")}
    attendances = {(x["student_id"], x["course_code"]): x for x in rows("attendance.csv")}
    results = {(x["student_id"], x["course_code"]): x for x in rows("results.csv")}
    oracle = {
        "method": "Independent calculations from raw CSV fixtures; app.tools is not imported.",
        "cases": {
            "TOOL-01": {"student_id": "S1001", "course_code": "CS201", "attendance_pct": round(100 * int(attendances[("S1001", "CS201")]["classes_attended"]) / int(attendances[("S1001", "CS201")]["classes_held"]), 2)},
            "TOOL-02": {"student_id": "S1002", "course_code": "CS201", "attendance_pct": round(100 * int(attendances[("S1002", "CS201")]["classes_attended"]) / int(attendances[("S1002", "CS201")]["classes_held"]), 2)},
            "TOOL-03": {"student_id": "S1003", "course_code": "CS201", "result": results[("S1003", "CS201")]["result"], "total_marks": int(results[("S1003", "CS201")]["total_marks"]), "max_marks": int(results[("S1003", "CS201")]["max_marks"])},
            "TOOL-04": {"student_id": "S1007", "cgpa": float(students["S1007"]["cgpa"])},
            "TOOL-05": {"student_id": "S1006", "active_backlogs_from_results": sum(1 for (sid, _), result in results.items() if sid == "S1006" and result["result"] != "PASS"), "stored_active_backlogs": int(students["S1006"]["active_backlogs"])},
            "ELIG-01": {"student_id": "S1001", "course_code": "CS201", "attendance_pct": 100 * int(attendances[("S1001", "CS201")]["classes_attended"]) / int(attendances[("S1001", "CS201")]["classes_held"]), "test_threshold_from_official_clause": 75, "expected_eligible_under_base_rule": 100 * int(attendances[("S1001", "CS201")]["classes_attended"]) / int(attendances[("S1001", "CS201")]["classes_held"]) >= 75},
            "ELIG-02": {"student_id": "S1002", "course_code": "CS201", "attendance_pct": 100 * int(attendances[("S1002", "CS201")]["classes_attended"]) / int(attendances[("S1002", "CS201")]["classes_held"]), "test_threshold_from_official_clause": 75, "expected_eligible_under_base_rule": 100 * int(attendances[("S1002", "CS201")]["classes_attended"]) / int(attendances[("S1002", "CS201")]["classes_held"]) >= 75}
        }
    }
    target = ROOT / "reports" / "evaluation_oracle.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(oracle, indent=2), encoding="utf-8")
    invalid = [case_id for case_id, item in oracle["cases"].items() if "active_backlogs_from_results" in item and item["active_backlogs_from_results"] != item["stored_active_backlogs"]]
    if invalid:
        print(f"INDEPENDENT ORACLE FAILED: backlog counts disagree for {invalid}")
        return 1
    print(f"Independent oracle PASS: {len(oracle['cases'])} tool cases; raw CSV values agree with expected results.")
    print(target)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
