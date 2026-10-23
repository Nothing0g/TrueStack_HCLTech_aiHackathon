from __future__ import annotations
from datetime import date
from typing import Any
from app.db import source_register_rows, scope_matches, batch_matches


def doc_applicable(doc: dict[str, Any], as_of_date: str, programme: str = "ALL", batch_year: int | None = None) -> bool:
    start = doc.get("effective_from") or "0001-01-01"
    end = doc.get("effective_to") or "9999-12-31"
    return start <= as_of_date <= end and scope_matches(doc.get("scope_programmes","ALL"), programme) and batch_matches(doc.get("scope_batches","ALL"), batch_year)

def _section_matches(target: str, passage: dict[str, Any]) -> bool:
    """Match an explicit superseded clause to the retrieved passage, not the whole document."""
    target = target.strip().casefold()
    if not target:
        return True
    meta = passage.get("metadata", {})
    section = str(meta.get("section") or "").casefold()
    body = str(passage.get("text") or "").casefold()
    # Clause IDs often have OCR spaces; compact punctuation/whitespace for a stable comparison.
    import re
    compact = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
    needle = compact(target)
    return bool(needle and (needle in compact(section) or needle in compact(body)))


def resolve_sources(passages: list[dict[str, Any]], as_of_date: str, programme: str = "ALL", batch_year: int | None = None) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Apply Annex A order: applicability, explicit supersession, authority, recency.

    Supersession is clause-aware: a fictional or real amendment to one clause must not
    discard every other passage from the superseded document.
    """
    registry = {d["doc_id"]: d for d in source_register_rows()}
    candidates = []
    for passage in passages:
        meta = passage.get("metadata", {})
        doc_id = str(meta.get("doc_id", ""))
        doc = registry.get(doc_id, meta)
        if not doc_applicable(doc, as_of_date, programme, batch_year):
            continue
        item = {**passage, "metadata": {**meta, **doc}}
        # De-duplicate only identical chunk ids, not an entire document. Multiple clauses
        # from one source may support a multi-part answer.
        key = (doc_id, meta.get("page"), meta.get("chunk_index"), meta.get("section"))
        if all(x.get("_candidate_key") != key for x in candidates):
            item["_candidate_key"] = key
            candidates.append(item)
    if not candidates:
        return [], "No applicable source candidates", []

    # Explicit supersession: only an authority level 1 or 2 document may supersede,
    # and a #clause reference removes only passages that match that clause.
    removed_keys: set[tuple[Any, ...]] = set()
    supersession_notes: list[str] = []
    candidate_doc_by_id: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        candidate_doc_by_id.setdefault(str(candidate["metadata"].get("doc_id", "")), []).append(candidate)
    for item in candidates:
        m = item["metadata"]
        try:
            authority = int(m.get("authority_level", 5))
        except (TypeError, ValueError):
            authority = 5
        if authority > 2:
            continue
        for token in str(m.get("supersedes", "")).split(";"):
            token = token.strip()
            if not token:
                continue
            target_doc, sep, target_clause = token.partition("#")
            for older in candidate_doc_by_id.get(target_doc, []):
                if older is item:
                    continue
                if target_clause and not _section_matches(target_clause, older):
                    continue
                removed_keys.add(older.get("_candidate_key"))
                supersession_notes.append(f"{m.get('doc_id')} supersedes {target_doc}" + (f"#{target_clause}" if sep else ""))
    remaining = [x for x in candidates if x.get("_candidate_key") not in removed_keys]
    if not remaining:
        return [], "All passages were superseded or not applicable", []

    decision = "Applicable sources filtered by date and scope"
    if supersession_notes:
        decision += "; explicit supersession applied: " + "; ".join(dict.fromkeys(supersession_notes))

    # Pick higher authority when the retrieved candidates address the same requested
    # subject. Retrieval has already narrowed the candidates to the current question.
    if len(remaining) > 1:
        best_authority = min(int(x["metadata"].get("authority_level", 5)) for x in remaining)
        authority_group = [x for x in remaining if int(x["metadata"].get("authority_level", 5)) == best_authority]
        if len(authority_group) < len(remaining):
            decision += f"; authority level {best_authority} prevailed over lower-authority source(s)"
            remaining = authority_group
        if len(remaining) > 1:
            latest = max(str(x["metadata"].get("effective_from", "0001-01-01")) for x in remaining)
            latest_group = [x for x in remaining if str(x["metadata"].get("effective_from", "0001-01-01")) == latest]
            if len(latest_group) < len(remaining):
                decision += f"; later effective date {latest} prevailed within the same authority level"
                remaining = latest_group

    # Same-authority, same-date candidates are only an unresolved conflict when they
    # make competing claims about the same policy concept. Multiple supporting passages
    # from one document or different clauses are not a conflict by themselves.
    if len({x["metadata"].get("doc_id") for x in remaining}) > 1 and len(remaining) > 1:
        bodies = [str(x.get("text", "")) for x in remaining]
        common_concepts = {"attendance", "supplementary", "placement", "backlog", "cgpa", "pass mark", "eligibility", "registration", "fee", "scholarship", "hostel"}
        shared = [c for c in common_concepts if all(c in body.casefold() for body in bodies)]
        numeric_values = []
        import re
        for body in bodies:
            numeric_values.append(set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*%?", body)))
        competing_numbers = any(numeric_values[i] != numeric_values[j] and bool(numeric_values[i] & numeric_values[j]) is False for i in range(len(numeric_values)) for j in range(i+1, len(numeric_values)))
        if shared and competing_numbers:
            conflicts = [{"doc_id": x["metadata"].get("doc_id"), "title": x["metadata"].get("title"), "section": x["metadata"].get("section", "")} for x in remaining]
            return remaining, decision + "; unresolved competing policy claims remain", conflicts
    return remaining, decision, []

