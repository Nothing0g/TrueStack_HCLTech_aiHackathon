from __future__ import annotations

from app.policy import resolve_sources
from app.db import source_register_rows


def _passage(doc_id: str, text: str, section: str, page: int = 1) -> dict:
    source = next(x for x in source_register_rows() if x["doc_id"] == doc_id)
    return {
        "text": text,
        "score": 0.9,
        "metadata": {
            **source,
            "doc_id": doc_id,
            "section": section,
            "page": page,
            "chunk_index": page,
        },
    }


def test_synthetic_circular_supersedes_only_synthetic_baseline(isolated_db):
    passages = [
        _passage("SYN-DEMO-REG-001", "7.1 Baseline attendance threshold is 75% for this synthetic demo.", "7.1 Baseline attendance threshold"),
        _passage("SYN-DEMO-CIRC-002", "1.1 From 2026-08-01 the synthetic demo attendance threshold is 80%.", "1.1 Synthetic amendment"),
    ]
    selected, decision, conflicts = resolve_sources(passages, "2026-10-23")
    assert [p["metadata"]["doc_id"] for p in selected] == ["SYN-DEMO-CIRC-002"]
    assert "supersedes" in decision
    assert not conflicts


def test_future_synthetic_amendment_does_not_apply_early(isolated_db):
    passages = [
        _passage("SYN-DEMO-REG-001", "7.1 Baseline attendance threshold is 75% for this synthetic demo.", "7.1 Baseline attendance threshold"),
        _passage("SYN-DEMO-CIRC-002", "1.1 From 2026-08-01 the synthetic demo attendance threshold is 80%.", "1.1 Synthetic amendment"),
    ]
    selected, _, _ = resolve_sources(passages, "2025-12-31")
    assert {p["metadata"]["doc_id"] for p in selected} == {"SYN-DEMO-REG-001"}


def test_unresolved_same_authority_policy_conflict_is_flagged(isolated_db):
    with __import__("app.db", fromlist=["connect"]).connect() as conn:
        conn.execute("""INSERT INTO source_register
            (doc_id,title,issuer,authority_level,doc_type,version,effective_from,effective_to,supersedes,scope_programmes,scope_batches,provenance,retrieved_on,synthetic,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("SYN-DEMO-CIRC-OTHER", "SYNTHETIC DEMO — Other Attendance Circular", "Synthetic", 2, "circular", "1", "2026-08-01", "", "", "ALL", "ALL", "Synthetic test fixture", "2026-10-23", "Y", "indexed"))
    a = _passage("SYN-DEMO-CIRC-002", "Attendance threshold is 80% under this fictional circular.", "1.1")
    b = _passage("SYN-DEMO-CIRC-OTHER", "Attendance threshold is 85% under this fictional circular.", "1.2")
    selected, decision, conflicts = resolve_sources([a, b], "2026-10-23")
    assert len(selected) == 2
    assert conflicts
    assert "unresolved" in decision
