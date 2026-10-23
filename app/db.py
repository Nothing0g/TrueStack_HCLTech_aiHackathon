from __future__ import annotations
import csv, json, sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any
from app.config import DATABASE_PATH, ROOT

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS students (
 student_id TEXT PRIMARY KEY CHECK(length(student_id)=5 AND substr(student_id,1,1)='S'),
 full_name TEXT NOT NULL, programme TEXT NOT NULL, batch_year INTEGER NOT NULL,
 current_semester INTEGER NOT NULL CHECK(current_semester BETWEEN 1 AND 10),
 cgpa REAL NOT NULL CHECK(cgpa BETWEEN 0 AND 10), active_backlogs INTEGER NOT NULL CHECK(active_backlogs>=0)
);
CREATE TABLE IF NOT EXISTS courses (
 course_code TEXT PRIMARY KEY, course_name TEXT NOT NULL, programme TEXT NOT NULL,
 semester INTEGER NOT NULL, credits INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance (
 student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
 course_code TEXT NOT NULL REFERENCES courses(course_code) ON DELETE CASCADE,
 classes_held INTEGER NOT NULL CHECK(classes_held>0),
 classes_attended INTEGER NOT NULL CHECK(classes_attended>=0 AND classes_attended<=classes_held),
 PRIMARY KEY(student_id, course_code)
);
CREATE TABLE IF NOT EXISTS results (
 student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
 course_code TEXT NOT NULL REFERENCES courses(course_code) ON DELETE CASCADE,
 exam_session TEXT NOT NULL, exam_type TEXT NOT NULL CHECK(exam_type IN ('REGULAR','SUPPLEMENTARY')),
 internal_marks INTEGER NOT NULL, external_marks INTEGER NOT NULL, total_marks INTEGER NOT NULL,
 max_marks INTEGER NOT NULL CHECK(max_marks>0), result TEXT NOT NULL CHECK(result IN ('PASS','FAIL','ABSENT','DETAINED')),
 PRIMARY KEY(student_id, course_code, exam_session, exam_type)
);
CREATE TABLE IF NOT EXISTS source_register (
 doc_id TEXT PRIMARY KEY, title TEXT NOT NULL, issuer TEXT NOT NULL, authority_level INTEGER NOT NULL CHECK(authority_level BETWEEN 1 AND 5),
 doc_type TEXT NOT NULL, version TEXT NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT DEFAULT '',
 supersedes TEXT DEFAULT '', scope_programmes TEXT NOT NULL DEFAULT 'ALL', scope_batches TEXT NOT NULL DEFAULT 'ALL',
 provenance TEXT NOT NULL DEFAULT '', retrieved_on TEXT NOT NULL, synthetic TEXT NOT NULL CHECK(synthetic IN ('Y','N')),
 content_sha256 TEXT DEFAULT '', indexed_chunks INTEGER DEFAULT 0, status TEXT NOT NULL DEFAULT 'registered'
);
CREATE TABLE IF NOT EXISTS rule_registry (
 rule_id TEXT PRIMARY KEY, description TEXT NOT NULL, parameter TEXT NOT NULL, operator TEXT NOT NULL, value TEXT NOT NULL,
 scope_programmes TEXT NOT NULL DEFAULT 'ALL', scope_batches TEXT NOT NULL DEFAULT 'ALL', effective_from TEXT NOT NULL,
 effective_to TEXT DEFAULT '', source_doc_id TEXT NOT NULL REFERENCES source_register(doc_id), source_section TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS candidate_rules (
 candidate_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate', created_at TEXT NOT NULL,
 validation_message TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_records (
 trace_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, question_category TEXT NOT NULL, student_id TEXT DEFAULT '',
 sources_retrieved_json TEXT NOT NULL, precedence_decision TEXT DEFAULT '', tools_invoked_json TEXT NOT NULL,
 applied_rules_json TEXT NOT NULL, conflicts_detected_json TEXT NOT NULL, answer_type TEXT NOT NULL,
 model TEXT NOT NULL, llm_calls INTEGER DEFAULT 0, tokens TEXT DEFAULT 'unavailable', latency_ms INTEGER DEFAULT 0,
 error_category TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_results_student ON results(student_id);
CREATE INDEX IF NOT EXISTS idx_rules_parameter ON rule_registry(parameter, active);
"""

@contextmanager
def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)

def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None

def seed_source_metadata_and_rules() -> None:
    """Register supplied DTU sources and explicitly labelled synthetic demo sources.

    Source dates are recorded only where the document states them. The B.Tech
    ordinance copy does not expose a precise effective-from date in the inspected
    clause, so its effective_from remains blank rather than inventing a date.
    """
    metadata = [
      {"doc_id":"DTU-BTECH-ORD-2025","title":"Ordinance, Regulations, Scheme of Teaching & Examinations — B.Tech Program 2025","issuer":"Delhi Technological University","authority_level":1,"doc_type":"regulation","version":"2025","effective_from":"","effective_to":"","supersedes":"","scope_programmes":"B.Tech","scope_batches":"ALL","provenance":"https://www.dtu.ac.in/Web/Academics/ordinance.php (local supplied copy: data/documents/official/DTU_BTech_Ordinance_2025.pdf)","retrieved_on":date.today().isoformat(),"synthetic":"N"},
      {"doc_id":"DTU-EXAM-ODD-2026-27","title":"Eligibility for assessment, examination & evaluation of courses — Odd Semester AY 2026–2027","issuer":"Controller of Examinations, Delhi Technological University","authority_level":2,"doc_type":"notice","version":"2026-08-24","effective_from":"2026-08-24","effective_to":"","supersedes":"","scope_programmes":"ALL","scope_batches":"ALL","provenance":"https://exam.dtu.ac.in/Notices/Notice_Studnt_O26_240826.pdf (local supplied copy)","retrieved_on":date.today().isoformat(),"synthetic":"N"},
      {"doc_id":"DTU-TNP-PLACEMENT-2025-26","title":"Placement Policy 2025-26","issuer":"Department of Training and Placement, Delhi Technological University","authority_level":2,"doc_type":"notice","version":"2025-26","effective_from":"2025-07-03","effective_to":"","supersedes":"","scope_programmes":"ALL","scope_batches":"2025-26 passing-out batch","provenance":"https://tnp.dtu.ac.in/docs/policy.pdf (local supplied copy; explicitly for the 2025-26 passing-out batch; no universal CGPA cutoff stated; cohort is not mapped to admission year in this dataset)","retrieved_on":date.today().isoformat(),"synthetic":"N"},
      {"doc_id":"SYN-DEMO-REG-001","title":"SYNTHETIC DEMO — University Academic Baseline Rules and FAQ","issuer":"Synthetic demonstration authoring team","authority_level":4,"doc_type":"faq","version":"1.0-demo","effective_from":"2025-07-01","effective_to":"","supersedes":"","scope_programmes":"ALL","scope_batches":"ALL","provenance":"Bundled synthetic demonstration document; not issued by DTU","retrieved_on":date.today().isoformat(),"synthetic":"Y"},
      {"doc_id":"SYN-DEMO-CIRC-002","title":"SYNTHETIC DEMO — Attendance Amendment Circular","issuer":"Synthetic demonstration authoring team","authority_level":2,"doc_type":"circular","version":"2.0-demo","effective_from":"2026-08-01","effective_to":"","supersedes":"SYN-DEMO-REG-001#7.1","scope_programmes":"ALL","scope_batches":"ALL","provenance":"Bundled synthetic demonstration document; not issued by DTU","retrieved_on":date.today().isoformat(),"synthetic":"Y"},
    ]
    with connect() as c:
        for m in metadata:
            c.execute("""INSERT INTO source_register
                (doc_id,title,issuer,authority_level,doc_type,version,effective_from,effective_to,supersedes,
                 scope_programmes,scope_batches,provenance,retrieved_on,synthetic,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title, issuer=excluded.issuer,
                authority_level=excluded.authority_level, doc_type=excluded.doc_type,
                version=excluded.version, effective_from=excluded.effective_from,
                effective_to=excluded.effective_to, supersedes=excluded.supersedes,
                scope_programmes=excluded.scope_programmes, scope_batches=excluded.scope_batches,
                provenance=excluded.provenance, retrieved_on=excluded.retrieved_on,
                synthetic=excluded.synthetic""",
                (*[m[k] for k in ["doc_id","title","issuer","authority_level","doc_type","version","effective_from","effective_to","supersedes","scope_programmes","scope_batches","provenance","retrieved_on","synthetic"]], "registered"))
        rules = [
          # The actual 75% clause appears in the supplied B.Tech ordinance at R.1(B).22.
          # The source copy does not state an exact effective-from date for this clause;
          # leave it blank and retain the true source reference rather than inventing a date.
          ("ATT-DTU-ORD-R1B22","Minimum attendance for B.Tech end-term examination eligibility","min_attendance_pct",">=","75","B.Tech","ALL","","","DTU-BTECH-ORD-2025","R.1(B).22",1),
          # The synthetic 80% attendance amendment remains searchable for a labelled demo,
          # but is inactive as an authoritative calculation rule because it is not DTU policy.
          ("ATT-MIN-01","Synthetic demo attendance amendment only; inactive for normal eligibility","min_attendance_pct",">=","80","ALL","ALL","2026-08-01","","SYN-DEMO-CIRC-002","1.1",0),
          ("PASS-DTU-ORD-TABLE4","Lower grade cutoff for pass/fail boundary tests; the full grade formula remains applicable","pass_pct",">=","35","B.Tech","ALL","","","DTU-BTECH-ORD-2025","Table 4: Structure for Grading of Academic Performance",1),
          ("PLACE-CGPA-01","Placement demo minimum CGPA (synthetic demo only)","placement_min_cgpa",">=","6.0","ALL","ALL","2025-07-01","","SYN-DEMO-REG-001","9.1",1),
          ("PLACE-BACKLOG-01","Placement demo maximum active backlogs (synthetic demo only)","placement_max_backlogs","<=","0","ALL","ALL","2025-07-01","","SYN-DEMO-REG-001","9.2",1),
          ("SUPP-ELIG-DEMO-01","Supplementary demo: latest FAIL result can be treated as eligible to apply","supplementary_eligible_result","==","FAIL","ALL","ALL","2025-07-01","","SYN-DEMO-REG-001","8.1",1),
        ]
        c.execute("UPDATE rule_registry SET active=0 WHERE rule_id='PASS-MIN-01'")
        for rule in rules:
            c.execute("""INSERT INTO rule_registry
                (rule_id,description,parameter,operator,value,scope_programmes,scope_batches,effective_from,effective_to,source_doc_id,source_section,active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(rule_id) DO UPDATE SET description=excluded.description,parameter=excluded.parameter,
                operator=excluded.operator,value=excluded.value,scope_programmes=excluded.scope_programmes,
                scope_batches=excluded.scope_batches,effective_from=excluded.effective_from,effective_to=excluded.effective_to,
                source_doc_id=excluded.source_doc_id,source_section=excluded.source_section""", rule)


def seed_sources_and_rules() -> None:
    """Register and persistently index the bundled demo policies and extracted DTU sources.

    Official PDFs are kept locally by the project owner. `scripts/ingest_official_sources.py`
    creates page-anchored text extracts (including OCR for scanned pages), which are indexed
    here without repeating OCR or embedding work on each restart.
    """
    import hashlib
    from app.rag import ingest_path
    docs_dir = ROOT / "data" / "documents"
    extracted_dir = ROOT / "data" / "extracted"
    seed_source_metadata_and_rules()
    # Prefer the complete page-anchored extract in the local full bundle. A GitHub
    # source checkout may contain only these shorter page-anchored excerpts to avoid
    # checking large OCR output into the public repository; it still starts with a
    # useful, honestly scoped corpus and can ingest fuller documents later.
    documents = [
        ("SYN-DEMO-REG-001", docs_dir / "synthetic_baseline_policy.md", None),
        ("SYN-DEMO-CIRC-002", docs_dir / "synthetic_attendance_amendment.md", None),
        ("DTU-BTECH-ORD-2025", extracted_dir / "DTU_BTech_Ordinance_2025.txt", docs_dir / "DTU_BTech_Ordinance_2025_excerpt.md"),
        ("DTU-EXAM-ODD-2026-27", extracted_dir / "DTU_Exam_Eligibility_Odd_Sem_2026-27.txt", docs_dir / "DTU_Exam_Notice_OddSemester_2026_27.md"),
        ("DTU-TNP-PLACEMENT-2025-26", extracted_dir / "DTU_Placement_Policy_2025-26.txt", docs_dir / "DTU_Placement_Policy_2025_26.md"),
    ]
    for doc_id, primary_path, fallback_path in documents:
        path = primary_path if primary_path.exists() else fallback_path
        if path is None or not path.exists():
            continue
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        with connect() as c:
            existing = c.execute("SELECT content_sha256,status FROM source_register WHERE doc_id=?", (doc_id,)).fetchone()
        if existing and existing["content_sha256"] == sha and existing["status"] == "indexed":
            continue
        text = raw.decode("utf-8", errors="replace")
        metadata = next(x for x in source_register_rows() if x["doc_id"] == doc_id)
        chunks = ingest_path(text, metadata, source_path=str(path), reset=True)
        with connect() as c:
            c.execute("UPDATE source_register SET content_sha256=?, indexed_chunks=?, status='indexed' WHERE doc_id=?", (sha, chunks, doc_id))


def source_register_rows() -> list[dict[str, Any]]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM source_register ORDER BY effective_from DESC, doc_id")]

def active_rules(as_of_date: str, parameter: str | None = None, programme: str = "ALL", batch_year: int | None = None) -> list[dict[str, Any]]:
    with connect() as c:
        q = "SELECT * FROM rule_registry WHERE active=1 AND COALESCE(NULLIF(effective_from, ''), '0001-01-01')<=? AND (effective_to='' OR effective_to>=?)"
        params: list[Any] = [as_of_date, as_of_date]
        if parameter:
            q += " AND parameter=?"; params.append(parameter)
        rows = [dict(r) for r in c.execute(q, params)]
    return [r for r in rows if scope_matches(r.get("scope_programmes", "ALL"), programme) and batch_matches(r.get("scope_batches", "ALL"), batch_year)]

def scope_matches(scope: str, programme: str) -> bool:
    if not scope or scope.strip().upper() == "ALL": return True
    values = [x.strip().casefold() for x in scope.split(";") if x.strip()]
    p = (programme or "").casefold()
    return p in values or any(v in p or p in v for v in values)

def batch_matches(scope: str, year: int | None) -> bool:
    if not scope or scope.strip().upper() == "ALL" or year is None: return True
    for token in [x.strip() for x in scope.split(";") if x.strip()]:
        try:
            if token.endswith("+") and year >= int(token[:-1]): return True
            if "-" in token:
                lo, hi = token.split("-", 1)
                if int(lo) <= year <= int(hi): return True
            if int(token) == year: return True
        except ValueError:
            continue
    return False

def audit(record: dict[str, Any]) -> None:
    with connect() as c:
        c.execute("""INSERT OR REPLACE INTO audit_records (trace_id,timestamp,question_category,student_id,sources_retrieved_json,precedence_decision,tools_invoked_json,applied_rules_json,conflicts_detected_json,answer_type,model,llm_calls,tokens,latency_ms,error_category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            record["trace_id"], record["timestamp"], record.get("question_category","unknown"), record.get("student_id",""),
            json.dumps(record.get("sources_retrieved",[]), ensure_ascii=False), record.get("precedence_decision",""),
            json.dumps(record.get("tools_invoked",[]), ensure_ascii=False), json.dumps(record.get("applied_rules",[]), ensure_ascii=False),
            json.dumps(record.get("conflicts_detected",[]), ensure_ascii=False), record.get("answer_type","not_found"), record.get("model","unknown"),
            int(record.get("llm_calls",0)), str(record.get("tokens","unavailable")), int(record.get("latency_ms",0)), record.get("error_category","")
        ))

def get_audit(trace_id: str) -> dict[str, Any] | None:
    with connect() as c: r = c.execute("SELECT * FROM audit_records WHERE trace_id=?", (trace_id,)).fetchone()
    if not r: return None
    d = dict(r)
    for source, target in [("sources_retrieved_json","sources_retrieved"),("tools_invoked_json","tools_invoked"),("applied_rules_json","applied_rules"),("conflicts_detected_json","conflicts_detected")]:
        d[target] = json.loads(d.pop(source) or "[]")
    return d
