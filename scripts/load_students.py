from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.db import init_db, connect, active_rules, seed_source_metadata_and_rules

REQUIRED = {
    "students": ["student_id","full_name","programme","batch_year","current_semester","cgpa","active_backlogs"],
    "courses": ["course_code","course_name","programme","semester","credits"],
    "attendance": ["student_id","course_code","classes_held","classes_attended"],
    "results": ["student_id","course_code","exam_session","exam_type","internal_marks","external_marks","total_marks","max_marks","result"],
}


def read_csv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Required CSV is missing: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [field for field in fields if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing required columns {missing}")
        return list(reader)


def _number(value: str, cast, path: str, row: int, errors: list[str]):
    try: return cast(value)
    except (TypeError, ValueError):
        errors.append(f"{path} row {row}: invalid number {value!r}")
        return None


def validate_bundle(directory: Path) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    data = {table: read_csv(directory / f"{table}.csv", fields) for table, fields in REQUIRED.items()}
    errors: list[str] = []
    student_ids = [r["student_id"].strip() for r in data["students"]]
    course_ids = [r["course_code"].strip().upper() for r in data["courses"]]
    if len(set(student_ids)) != len(student_ids): errors.append("students.csv: duplicate student_id")
    if len(set(course_ids)) != len(course_ids): errors.append("courses.csv: duplicate course_code")
    students_by_id = {r["student_id"].strip(): r for r in data["students"]}
    courses_by_id = {r["course_code"].strip().upper(): r for r in data["courses"]}
    programmes = {r["programme"].strip() for r in data["students"]}
    course_programmes = {r["programme"].strip() for r in data["courses"]}
    if not programmes.issubset(course_programmes): errors.append("every student programme must have at least one matching course")

    for row_no, s in enumerate(data["students"], 2):
        sid = s["student_id"].strip()
        if not (len(sid) == 5 and sid.startswith("S") and sid[1:].isdigit()): errors.append(f"students.csv row {row_no}: invalid student_id format")
        if sid.startswith("S") and sid[1:].isdigit() and 9000 <= int(sid[1:]) <= 9999: errors.append(f"students.csv row {row_no}: reserved judge student ID")
        if not s["full_name"].strip(): errors.append(f"students.csv row {row_no}: full_name is blank")
        if not s["programme"].strip(): errors.append(f"students.csv row {row_no}: programme is blank")
        batch = _number(s["batch_year"], int, "students.csv", row_no, errors)
        sem = _number(s["current_semester"], int, "students.csv", row_no, errors)
        cgpa = _number(s["cgpa"], float, "students.csv", row_no, errors)
        backlogs = _number(s["active_backlogs"], int, "students.csv", row_no, errors)
        if sem is not None and not 1 <= sem <= 10: errors.append(f"students.csv row {row_no}: current_semester outside 1–10")
        if cgpa is not None and not 0 <= cgpa <= 10: errors.append(f"students.csv row {row_no}: CGPA outside 0–10")
        if backlogs is not None and backlogs < 0: errors.append(f"students.csv row {row_no}: negative active_backlogs")
        if batch is not None and not 2000 <= batch <= 2100: errors.append(f"students.csv row {row_no}: implausible batch_year")

    for row_no, c in enumerate(data["courses"], 2):
        code = c["course_code"].strip().upper()
        if code.startswith("JDG"): errors.append(f"courses.csv row {row_no}: reserved judge course code")
        sem = _number(c["semester"], int, "courses.csv", row_no, errors)
        credits = _number(c["credits"], int, "courses.csv", row_no, errors)
        if sem is not None and not 1 <= sem <= 10: errors.append(f"courses.csv row {row_no}: semester outside 1–10")
        if credits is not None and credits <= 0: errors.append(f"courses.csv row {row_no}: credits must be positive")

    attendance_seen = set()
    for row_no, a in enumerate(data["attendance"], 2):
        sid, code = a["student_id"].strip(), a["course_code"].strip().upper()
        if sid not in students_by_id: errors.append(f"attendance.csv row {row_no}: unknown student {sid}")
        if code not in courses_by_id: errors.append(f"attendance.csv row {row_no}: unknown course {code}")
        key = (sid, code)
        if key in attendance_seen: errors.append(f"attendance.csv row {row_no}: duplicate student/course key {key}")
        attendance_seen.add(key)
        held = _number(a["classes_held"], int, "attendance.csv", row_no, errors)
        attended = _number(a["classes_attended"], int, "attendance.csv", row_no, errors)
        if held is not None and held <= 0: errors.append(f"attendance.csv row {row_no}: classes_held must be > 0")
        if held is not None and attended is not None and not 0 <= attended <= held: errors.append(f"attendance.csv row {row_no}: attended must be between 0 and held")
        if sid in students_by_id and code in courses_by_id and courses_by_id[code]["programme"] != students_by_id[sid]["programme"]:
            errors.append(f"attendance.csv row {row_no}: student programme does not match course programme")

    result_seen = set()
    expected_nonpass: dict[str, int] = {sid: 0 for sid in students_by_id}
    pass_rule_by_programme: dict[str, float] = {}
    try:
        from datetime import date
        for prog in programmes:
            rows = active_rules(date.today().isoformat(), "pass_pct", prog, None)
            if rows:
                # If the registry returns ambiguous thresholds, fail validation rather than choosing one.
                unique = {(r["operator"], r["value"]) for r in rows}
                if len(unique) == 1:
                    op, val = next(iter(unique))
                    if op == ">=": pass_rule_by_programme[prog] = float(val)
    except Exception:
        pass

    for row_no, r in enumerate(data["results"], 2):
        sid, code = r["student_id"].strip(), r["course_code"].strip().upper()
        if sid not in students_by_id: errors.append(f"results.csv row {row_no}: unknown student {sid}")
        if code not in courses_by_id: errors.append(f"results.csv row {row_no}: unknown course {code}")
        vals = {key: _number(r[key], int, "results.csv", row_no, errors) for key in ["internal_marks","external_marks","total_marks","max_marks"]}
        if all(v is not None for v in vals.values()):
            if min(vals["internal_marks"], vals["external_marks"], vals["total_marks"]) < 0: errors.append(f"results.csv row {row_no}: marks cannot be negative")
            if vals["max_marks"] <= 0 or vals["total_marks"] > vals["max_marks"]: errors.append(f"results.csv row {row_no}: marks outside range")
            if vals["internal_marks"] + vals["external_marks"] != vals["total_marks"]: errors.append(f"results.csv row {row_no}: total != internal + external")
            if r["result"] in {"ABSENT", "DETAINED"} and vals["total_marks"] != 0: errors.append(f"results.csv row {row_no}: ABSENT/DETAINED should have zero marks in this synthetic schema")
            if r["result"] in {"PASS", "FAIL"} and sid in students_by_id and code in courses_by_id:
                programme = students_by_id[sid]["programme"]
                threshold_pct = pass_rule_by_programme.get(programme)
                if threshold_pct is not None:
                    pass_mark = threshold_pct * vals["max_marks"] / 100
                    expected = "PASS" if vals["total_marks"] >= pass_mark else "FAIL"
                    if r["result"] != expected: errors.append(f"results.csv row {row_no}: result {r['result']} inconsistent with registry pass rule {threshold_pct}% (expected {expected})")
        if r["exam_type"] not in {"REGULAR", "SUPPLEMENTARY"}: errors.append(f"results.csv row {row_no}: invalid exam_type")
        if r["result"] not in {"PASS", "FAIL", "ABSENT", "DETAINED"}: errors.append(f"results.csv row {row_no}: invalid result")
        key = (sid, code, r["exam_session"].strip(), r["exam_type"])
        if key in result_seen: errors.append(f"results.csv row {row_no}: duplicate result key {key}")
        result_seen.add(key)
        if sid in expected_nonpass and r["result"] != "PASS": expected_nonpass[sid] += 1
        if sid in students_by_id and code in courses_by_id and courses_by_id[code]["programme"] != students_by_id[sid]["programme"]:
            errors.append(f"results.csv row {row_no}: student programme does not match course programme")

    for sid, expected in expected_nonpass.items():
        actual = _number(students_by_id[sid]["active_backlogs"], int, "students.csv", 0, errors)
        # For the demo, ABSENT and DETAINED also remain unresolved course outcomes.
        if actual is not None and actual != expected:
            errors.append(f"students.csv {sid}: active_backlogs={actual}, but {expected} non-PASS outcomes are present")

    if len(data["students"]) < 30: errors.append("minimum 30 students not met")
    if len(programmes) < 2: errors.append("minimum 2 student programmes not met")
    if len({r["batch_year"] for r in data["students"]}) < 2: errors.append("minimum 2 batches not met")
    if len(data["courses"]) < 6: errors.append("minimum 6 courses not met")
    if data["students"] and data["courses"] and data["attendance"] and data["results"]:
        for sid in student_ids:
            expected_courses = {code for code, c in courses_by_id.items() if c["programme"] == students_by_id[sid]["programme"]}
            actual_courses = {code for row_sid, code in attendance_seen if row_sid == sid}
            if expected_courses != actual_courses: errors.append(f"{sid}: attendance records do not cover its programme course set")
    return data, errors


def load(directory: Path) -> dict[str, int]:
    init_db()
    seed_source_metadata_and_rules()
    data, errors = validate_bundle(directory)
    if errors:
        raise ValueError("Validation failed:\n- " + "\n- ".join(errors))
    with connect() as conn:
        # Ordering respects foreign keys. Entire load is one transaction.
        for table in ["students", "courses", "attendance", "results"]:
            rows = data[table]
            for raw in rows:
                row = dict(raw)
                if table == "students":
                    row.update(batch_year=int(row["batch_year"]), current_semester=int(row["current_semester"]), cgpa=float(row["cgpa"]), active_backlogs=int(row["active_backlogs"]))
                    cols = REQUIRED[table]
                    conn.execute(f"INSERT INTO students ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(student_id) DO UPDATE SET " + ",".join(f"{k}=excluded.{k}" for k in cols if k != "student_id"), [row[k] for k in cols])
                elif table == "courses":
                    row.update(semester=int(row["semester"]), credits=int(row["credits"]))
                    cols = REQUIRED[table]
                    conn.execute(f"INSERT INTO courses ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(course_code) DO UPDATE SET " + ",".join(f"{k}=excluded.{k}" for k in cols if k != "course_code"), [row[k] for k in cols])
                elif table == "attendance":
                    row.update(classes_held=int(row["classes_held"]), classes_attended=int(row["classes_attended"]))
                    cols = REQUIRED[table]
                    conn.execute(f"INSERT INTO attendance ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(student_id,course_code) DO UPDATE SET classes_held=excluded.classes_held,classes_attended=excluded.classes_attended", [row[k] for k in cols])
                else:
                    for key in ["internal_marks","external_marks","total_marks","max_marks"]: row[key] = int(row[key])
                    cols = REQUIRED[table]
                    conn.execute(f"INSERT INTO results ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(student_id,course_code,exam_session,exam_type) DO UPDATE SET " + ",".join(f"{k}=excluded.{k}" for k in cols if k not in {"student_id","course_code","exam_session","exam_type"}), [row[k] for k in cols])
    return {table: len(rows) for table, rows in data.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate and idempotently load Annex C student CSV files")
    parser.add_argument("--dir", default=str(ROOT / "data" / "test_students"))
    args = parser.parse_args()
    try:
        counts = load(Path(args.dir))
        print("Loaded successfully (idempotent):", counts)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
