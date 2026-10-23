from __future__ import annotations

import re
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, TypedDict

from app.config import MOCK_LLM, OLLAMA_MODEL
from app.db import audit, connect
from app.llm import LLMUnavailable, explain
from app.policy import resolve_sources
from app.rag import search, search_document
from app.tools import (
    ToolProblem, check_exam_eligibility, check_placement_eligibility,
    check_supplementary_eligibility, get_active_backlogs, get_attendance,
    get_cgpa, get_course_result, get_student_profile,
)

NOT_FOUND = "I could not find this information in the authorised university sources."
COURSES_PATTERN = re.compile(r"\b([A-Z]{2,4}\d{3,4})\b", re.I)
STUDENT_ID_PATTERN = re.compile(r"\bS\d{4}\b", re.I)
DATA_TERMS = ("grade", "marks", "cgpa", "attendance", "backlog", "student record", "result", "profile")
STOPWORDS = {
    "what", "does", "do", "the", "is", "a", "an", "i", "my", "me", "to", "for", "of", "in", "on", "at", "and", "or", "it", "this", "that", "with", "from", "how", "can", "could", "would", "should", "tell", "show", "please", "about", "current", "policy", "rule", "rules", "information", "required", "need", "minimum", "say", "says", "there", "any", "are", "be", "am", "if", "will", "based", "under", "myself", "university", "student", "services", "assistant", "which", "meets", "meet", "doesn"
}

try:
    from langgraph.graph import END, START, StateGraph
    LANGGRAPH_AVAILABLE = True
except Exception:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class WorkflowState(TypedDict, total=False):
    question: str
    student_id: str | None
    as_of_date: str
    trace_id: str
    started: float
    category: str
    course: str | None
    student_context: dict[str, Any]
    sources: list[dict[str, Any]]
    selected: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    decision: str
    query: str
    tool_result: dict[str, Any]
    response: dict[str, Any]
    error_category: str
    model: str
    llm_calls: int
    tokens: int | str


def classify(question: str) -> tuple[str, str | None]:
    q = question.casefold()
    course_match = COURSES_PATTERN.search(question)
    course = course_match.group(1).upper() if course_match else None
    ids = STUDENT_ID_PATTERN.findall(question)
    data_terms = any(term in q for term in DATA_TERMS)
    if ids and data_terms and not any(k in q for k in ("id format", "student id format")):
        if any(k in q for k in ("cgpa", "backlog", "profile", "semester")):
            return "personal_profile", course
        if "attendance" in q:
            return "personal_attendance", course
        return "personal_result", course
    if any(x in q for x in ("if i pass", "what if i pass", "suppose i pass", "if i clear", "if i pass my supplementary")):
        return "what_if_placement", course
    if any(x in q for x in ("eligible for placement", "placement eligibility", "qualify for placement", "placement cutoff", "placement cut-off")):
        return "placement_eligibility", course
    if any(x in q for x in ("eligible for supplementary", "supplementary eligibility", "supplementary exam", "supplementary examination")):
        return "supplementary_eligibility", course
    if any(x in q for x in ("eligible for the exam", "eligible for exam", "eligible to sit", "exam eligibility", "eligible to appear", "attendance requirement for me", "can i appear")):
        return "exam_eligibility", course
    if any(x in q for x in ("my attendance", "attendance in", "attendance for", "show my attendance")):
        return "personal_attendance", course
    if any(x in q for x in ("my cgpa", "what is my cgpa", "my backlogs", "active backlogs", "my profile", "my semester")):
        return "personal_profile", course
    if any(x in q for x in ("my result", "my marks", "did i pass", "my grade", "result in", "marks in")):
        return "personal_result", course
    if q.strip().rstrip("?.! ") in {"am i eligible", "am i eligible for"}:
        return "ambiguous", course

    # Route institution-specific policy claims to RAG. Generic definitions and
    # ordinary knowledge questions use Qwen directly, even if they mention a broad topic.
    policy_indicators = (
        "dtu", "delhi technological university", "policy", "policies", "ordinance",
        "regulation", "circular", "eligibility", "admission criteria", "admission process",
        "minimum attendance", "attendance requirement", "exam eligibility",
        "examination eligibility", "placement cutoff", "placement cut-off",
        "placement eligibility", "scholarship policy", "fee policy", "hostel policy",
        "supplementary exam", "supplementary examination", "reappear", "back paper",
        "course registration", "cgpa cutoff", "cgpa cut-off", "student record",
        "academic rule", "at my university", "our university", "university's", "university’s",
        "in university policy",
    )
    if any(term in q for term in policy_indicators):
        return "policy", course
    return "general_knowledge", course

def citation_from(passage: dict[str, Any]) -> dict[str, Any]:
    m = passage.get("metadata", {})
    synthetic = str(m.get("synthetic", "N")).upper() == "Y"
    title = str(m.get("title") or m.get("doc_id") or "Unknown source")
    if synthetic and "SYNTHETIC DEMO" not in title.upper():
        title = f"SYNTHETIC DEMO — {title}"
    provenance = str(m.get("provenance") or "")
    effective_from = m.get("effective_from") or ""
    # The B.Tech 2025 scan does not state a precise effective date. Its catalogue
    # anchor is used internally for sorting only, and must not appear as a factual date.
    if "exact issue/effective day is not explicitly recorded" in provenance and effective_from == "2025-01-01":
        effective_from = None
    return {
        "doc_id": m.get("doc_id", ""), "title": title,
        "section": m.get("section") or None, "page": m.get("page") or None,
        "version": m.get("version") or "", "effective_from": effective_from,
        "synthetic": synthetic, "provenance": provenance,
    }


def _citations(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for passage in passages:
        c = citation_from(passage)
        key = (c["doc_id"], c["section"], c["page"])
        if c["doc_id"] and key not in seen:
            result.append(c)
            seen.add(key)
    return result


def _response(state: WorkflowState, answer: str, answer_type: str, *, citations=None, explanation=None, conflicts=None) -> dict[str, Any]:
    return {
        "trace_id": state.get("trace_id", uuid.uuid4().hex[:12]),
        "answer": answer,
        "answer_type": answer_type,
        "citations": citations or [],
        "tools_invoked": state.get("tools", []),
        "applied_rules": state.get("rules", []),
        "conflicts_detected": conflicts if conflicts is not None else state.get("conflicts", []),
        "explanation": explanation if explanation is not None else answer,
        "as_of_date": state.get("as_of_date", date.today().isoformat()),
    }


def _set_response(state: WorkflowState, answer: str, answer_type: str, *, error: str = "", **kwargs) -> WorkflowState:
    state["response"] = _response(state, answer, answer_type, **kwargs)
    if error:
        state["error_category"] = error
    return state


def _is_personal(category: str) -> bool:
    return category.startswith("personal_") or category in {
        "exam_eligibility", "placement_eligibility", "supplementary_eligibility", "what_if_placement"
    }


def _intake(state: WorkflowState) -> WorkflowState:
    state.setdefault("trace_id", uuid.uuid4().hex[:12])
    state.setdefault("as_of_date", date.today().isoformat())
    state.setdefault("started", time.perf_counter())
    state.setdefault("sources", []); state.setdefault("selected", []); state.setdefault("tools", [])
    state.setdefault("rules", []); state.setdefault("conflicts", []); state.setdefault("decision", "")
    state.setdefault("llm_calls", 0); state.setdefault("tokens", "unavailable")
    state.setdefault("model", f"mock:{OLLAMA_MODEL}" if MOCK_LLM else OLLAMA_MODEL)
    category, course = classify(state.get("question", ""))
    state["category"], state["course"] = category, course
    return state


def _authorize(state: WorkflowState) -> WorkflowState:
    question = state.get("question", "")
    student_id = (state.get("student_id") or "").upper() or None
    mentioned_ids = {s.upper() for s in STUDENT_ID_PATTERN.findall(question)}
    contains_record_request = any(term in question.casefold() for term in DATA_TERMS)
    if _is_personal(state.get("category", "")) and not student_id:
        return _set_response(state, "A trusted X-Student-Id header is required for personal questions.", "refused", error="missing_identity")
    if contains_record_request and mentioned_ids and any(target != student_id for target in mentioned_ids):
        return _set_response(state, "I cannot access another student's personal records.", "refused", error="cross_student_access")
    return state


def _clarify(state: WorkflowState) -> WorkflowState:
    question = state.get("question", "").casefold()
    if "course" in question or "attendance" in question or "result" in question or "marks" in question:
        message = "Which course code should I check (for example, CS201)?"
    else:
        message = "Do you mean eligibility for the end-semester examination or for placement?"
    return _set_response(state, message, "clarification_needed")


def _guard_synthetic_rule_fallback(state: WorkflowState, parameters: list[str], topic_query: str) -> None:
    """Never use a synthetic rule when an indexed official passage covers the same topic.

    If an official policy passage is present but its numeric rule has not been reviewed
    and activated in rule_registry, fail closed instead of silently applying demo values.
    Explicit questions about the labelled synthetic scenario bypass this guard.
    """
    if "synthetic demo" in state.get("question", "").casefold() or "fictional demo" in state.get("question", "").casefold():
        return
    passages = search(topic_query)
    official = [p for p in passages if str(p.get("metadata", {}).get("synthetic", "N")).upper() != "Y"]
    if not official or not _evidence_is_relevant(topic_query, official):
        return
    official_ids = {p.get("metadata", {}).get("doc_id") for p in official}
    with connect() as conn:
        rows = conn.execute(
            f"SELECT parameter, source_doc_id FROM rule_registry WHERE active=1 AND parameter IN ({','.join('?' for _ in parameters)})",
            parameters,
        ).fetchall()
    activated = {(r["parameter"], r["source_doc_id"]) for r in rows}
    missing = [param for param in parameters if not any((param, doc_id) in activated for doc_id in official_ids)]
    if missing:
        raise ToolProblem(
            "official_rule_not_activated",
            "An official policy passage covers this topic, but its source-linked calculation rule has not been validated and activated. The synthetic demo threshold was not used. Review the rule and activate it with scripts/activate_rule.py.",
        )


def _tool_node(state: WorkflowState) -> WorkflowState:
    cat = state["category"]
    course = state.get("course")
    sid = state.get("student_id")
    as_of = state["as_of_date"]
    try:
        if cat == "personal_attendance":
            if not course:
                return _set_response(state, "Which course code should I check (for example, CS201)?", "clarification_needed")
            result = get_attendance(sid, course)
            state["tools"].append({"tool": "get_attendance", "input": {"course_code": course}, "output": result, "status": "ok"})
            return _set_response(state, f"Your attendance in {course} is {result['classes_attended']} of {result['classes_held']} classes ({result['attendance_pct']}%).", "calculated", explanation="Attendance percentage was computed in Python from the recorded classes attended and held.")
        if cat == "personal_profile":
            q = state["question"].casefold()
            if "cgpa" in q:
                result = get_cgpa(sid); tool = "get_cgpa"
                answer = f"Your CGPA is {float(result['cgpa']):.2f}."
            elif "backlog" in q:
                result = get_active_backlogs(sid); tool = "get_active_backlogs"
                answer = f"Your active backlogs: {result['active_backlogs']}."
            else:
                result = get_student_profile(sid); tool = "get_student_profile"
                answer = f"Your synthetic demo profile: {result['programme']}, batch {result['batch_year']}, semester {result['current_semester']}, CGPA {float(result['cgpa']):.2f}, active backlogs {result['active_backlogs']}."
            state["tools"].append({"tool": tool, "input": {}, "output": result, "status": "ok"})
            return _set_response(state, answer, "calculated")
        if cat == "personal_result":
            if not course:
                return _set_response(state, "Which course code should I check (for example, CS201)?", "clarification_needed")
            result = get_course_result(sid, course)
            state["tools"].append({"tool": "get_course_result", "input": {"course_code": course}, "output": result, "status": "ok"})
            return _set_response(state, f"Your latest recorded result in {course} is {result['result']} ({result['total_marks']}/{result['max_marks']}).", "calculated")
        if cat == "exam_eligibility":
            if not course:
                return _set_response(state, "Which course should I check for examination eligibility?", "clarification_needed")
            _guard_synthetic_rule_fallback(state, ["min_attendance_pct"], "attendance examination eligibility minimum attendance")
            result = check_exam_eligibility(sid, course, as_of)
            state["tools"].append({"tool": "check_exam_eligibility", "input": {"course_code": course, "as_of_date": as_of}, "output": result, "status": "ok"})
            state["rules"].append({"rule_id": result["rule_id"], "value": result["threshold"], "source_doc_id": result["source_doc_id"], "source_section": result["source_section"], "synthetic": result.get("synthetic", False)})
            state["tool_result"] = result; state["student_context"] = get_student_profile(sid)
            state["query"] = f"{result['source_doc_id']} {result['source_section']} minimum attendance examination eligibility {course}"
            return state
        if cat == "placement_eligibility":
            _guard_synthetic_rule_fallback(state, ["placement_min_cgpa", "placement_max_backlogs"], "placement CGPA cutoff backlog eligibility")
            result = check_placement_eligibility(sid, as_of)
            state["tools"].append({"tool": "check_placement_eligibility", "input": {"as_of_date": as_of}, "output": result, "status": "ok"})
            state["rules"].extend(result["rules"]); state["tool_result"] = result; state["student_context"] = get_student_profile(sid)
            state["query"] = "placement eligibility minimum CGPA active backlog policy"
            return state
        if cat == "supplementary_eligibility":
            if not course:
                return _set_response(state, "Which course should I check for supplementary-exam eligibility?", "clarification_needed")
            _guard_synthetic_rule_fallback(state, ["supplementary_eligible_result"], "supplementary examination eligibility procedure")
            result = check_supplementary_eligibility(sid, course, as_of)
            state["tools"].append({"tool": "check_supplementary_eligibility", "input": {"course_code": course, "as_of_date": as_of}, "output": result, "status": "ok"})
            state["rules"].append({"rule_id": result["rule_id"], "value": "== FAIL", "source_doc_id": result["source_doc_id"], "source_section": result["source_section"], "synthetic": result["synthetic"]})
            state["tool_result"] = result; state["student_context"] = get_student_profile(sid)
            state["query"] = f"{result['source_doc_id']} {result['source_section']} supplementary examination policy {course}"
            return state
        if cat == "what_if_placement":
            if not course:
                return _set_response(state, "Which course should I use for the hypothetical supplementary-pass scenario?", "clarification_needed")
            _guard_synthetic_rule_fallback(state, ["placement_min_cgpa", "placement_max_backlogs", "supplementary_eligible_result"], "supplementary examination placement CGPA backlog eligibility")
            current = get_course_result(sid, course)
            state["tools"].append({"tool": "get_course_result", "input": {"course_code": course}, "output": current, "status": "ok"})
            if current["result"] not in {"FAIL", "ABSENT", "DETAINED"}:
                return _set_response(state, f"The latest result for {course} is {current['result']}. This scenario expects an unresolved result to be replaced by a supplementary pass; please clarify the starting assumption.", "clarification_needed")
            student = get_student_profile(sid)
            new_backlogs = max(0, int(student["active_backlogs"]) - 1)
            result = check_placement_eligibility(sid, as_of, hypothetical_backlogs=new_backlogs)
            state["tools"].append({"tool": "check_placement_eligibility", "input": {"hypothetical_backlogs": new_backlogs, "as_of_date": as_of}, "output": result, "status": "ok"})
            supplementary = check_supplementary_eligibility(sid, course, as_of)
            state["rules"].extend(result["rules"])
            state["rules"].append({"rule_id": supplementary["rule_id"], "value": "== FAIL", "source_doc_id": supplementary["source_doc_id"], "source_section": supplementary["source_section"], "synthetic": supplementary["synthetic"]})
            state["tool_result"] = {**result, "course_code": course, "current_result": current["result"], "supplementary_rule": supplementary, "assumption": "Assuming a supplementary PASS clears one backlog and CGPA remains unchanged; this is a synthetic what-if calculation."}
            state["student_context"] = student; state["query"] = "supplementary examination eligibility placement policy CGPA backlog"
            return state
        return _set_response(state, NOT_FOUND, "not_found")
    except ToolProblem as exc:
        if exc.code == "rule_conflict":
            return _set_response(state, exc.message, "conflict_flagged", error=exc.code)
        if exc.code in {"missing_identity"}:
            return _set_response(state, exc.message, "refused", error=exc.code)
        if exc.code in {"rule_not_found", "student_not_found", "record_not_found", "official_rule_not_activated"}:
            return _set_response(state, f"The required record or source-linked rule could not be found: {exc.message}", "not_found", error=exc.code)
        return _set_response(state, exc.message, "not_found", error=exc.code)


def _retrieve(state: WorkflowState) -> WorkflowState:
    try:
        if state.get("tool_result"):
            # Retrieve citation passages for each exact rule clause. Do not cite the first
            # arbitrary chunk from a source when a rule is stored on a later page/section.
            passages = []
            seen = set()
            for rule in state.get("rules", []):
                doc_id = rule.get("source_doc_id")
                if not doc_id:
                    continue
                target = str(rule.get("source_section") or "").casefold()
                all_doc = search_document(doc_id)
                def matches(p):
                    meta = p.get("metadata", {})
                    section = str(meta.get("section") or "").casefold()
                    body = str(p.get("text") or "").casefold()
                    if not target:
                        return False
                    compact = lambda v: re.sub(r"[^a-z0-9]", "", v.casefold())
                    needle = compact(target)
                    return bool(needle and (needle in compact(section) or needle in compact(body)))
                found = next((p for p in all_doc if matches(p)), None)
                if not found:
                    query = f"{doc_id} {target} {rule.get('parameter', '')} {state.get('question','')}"
                    found = next((p for p in search(query, top_k=10) if p.get("metadata", {}).get("doc_id") == doc_id), None)
                if found:
                    key = (doc_id, found.get("metadata", {}).get("page"), found.get("metadata", {}).get("chunk_index"))
                    if key not in seen:
                        passages.append(found); seen.add(key)
            state["sources"] = passages
        else:
            query = state.get("query") or state["question"]
            passages = search(query)
            # Synthetic policies are isolated to clearly requested demo scenarios.
            # For normal university questions, real sources remain in the corpus and
            # win through the documented source-precedence procedure where applicable.
            explicit_demo = any(term in state.get("question", "").casefold() for term in ("synthetic demo", "demo policy", "fictional policy", "demo-only rule"))
            if explicit_demo:
                passages = [p for p in passages if str(p.get("metadata", {}).get("synthetic", "N")).upper() == "Y"]
            state["sources"] = passages
    except Exception as exc:
        state["error_category"] = "retrieval_unavailable"
        state["response"] = {"_http_status": 503, "detail": f"Policy retrieval unavailable ({type(exc).__name__}). Check ChromaDB and the embedding model."}
    return state

def _resolve(state: WorkflowState) -> WorkflowState:
    from app.db import source_register_rows
    passages = state.get("sources", [])
    if state.get("tool_result"):
        required_ids = {r.get("source_doc_id") for r in state.get("rules", []) if r.get("source_doc_id")}
        available_ids = {p.get("metadata", {}).get("doc_id") for p in passages}
        if required_ids - available_ids:
            return _set_response(state, NOT_FOUND + " The active rule's supporting passage is not indexed, so an authoritative eligibility answer was not returned.", "not_found", error="rule_citation_missing")
        ctx = state.get("student_context", {})
        selected, decision, conflicts = resolve_sources(passages, state["as_of_date"], ctx.get("programme", "ALL"), ctx.get("batch_year"))
        # For the tool's exact rule citation, retain chunks of the validated source rule itself.
        selected_ids = {p.get("metadata", {}).get("doc_id") for p in selected}
        if required_ids - selected_ids:
            return _set_response(state, NOT_FOUND + " The rule source was not applicable after source precedence checks.", "not_found", error="rule_precedence_mismatch")
        state["selected"], state["decision"], state["conflicts"] = selected, decision, conflicts
        if conflicts:
            return _set_response(state, "Applicable rules remain in conflict after scope, supersession, authority and effective-date checks. Please contact the issuing office before acting on this result.", "conflict_flagged", citations=_citations(selected), explanation=decision, conflicts=conflicts)
        return state
    # Synthetic policy samples are fallbacks for uncovered topics, never substitutes for an applicable
    # official passage. The demo conflict can still be explored when explicitly requested as synthetic.
    explicit_synthetic = any(token in state.get("question", "").casefold() for token in ("synthetic demo", "fictional demo"))
    official_passages = [p for p in passages if str(p.get("metadata", {}).get("synthetic", "N")).upper() != "Y"]
    if explicit_synthetic:
        # Keep fictional precedence tests isolated from real university sources. Synthetic
        # demo rules can demonstrate version resolution, but cannot supersede DTU policy.
        passages = [p for p in passages if str(p.get("metadata", {}).get("synthetic", "N")).upper() == "Y"]
    elif official_passages and _evidence_is_relevant(state.get("query") or state["question"], official_passages):
        passages = official_passages
    ctx = state.get("student_context", {})
    selected, decision, conflicts = resolve_sources(passages, state["as_of_date"], ctx.get("programme", "ALL"), ctx.get("batch_year"))
    state["selected"], state["decision"], state["conflicts"] = selected, decision, conflicts
    if not selected or not _evidence_is_relevant(state.get("query") or state["question"], selected):
        return _set_response(state, NOT_FOUND, "not_found")
    if conflicts:
        return _set_response(state, "The applicable sources remain in conflict after checking scope, supersession, authority and effective dates. Please contact the issuing office before acting on either rule.", "conflict_flagged", citations=_citations(selected), explanation=decision, conflicts=conflicts)
    return state


def _evidence_is_relevant(question: str, passages: list[dict[str, Any]]) -> bool:
    """Reject semantically adjacent but wrong policy documents before generation."""
    if not passages:
        return False
    q = question.casefold()
    topic_groups = {
        "admission": {"admission", "admissions", "admit", "entrance", "jee", "counselling", "counseling"},
        "attendance": {"attendance", "attend", "classes attended", "classes held"},
        "placement": {"placement", "recruitment", "company", "cgpa cutoff", "backlog"},
        "scholarship": {"scholarship", "financial aid", "stipend", "fee waiver"},
        "hostel": {"hostel", "residence", "mess", "accommodation"},
        "fee": {"fee", "fees", "tuition", "refund", "payment"},
        "examination": {"examination", "exam", "exams", "assessment", "end-semester", "end semester"},
        "supplementary": {"supplementary", "reappear", "back paper"},
        "grading": {"grade", "grading", "marks", "cgpa", "sgpa", "result"},
    }
    passage_text = "\n".join(str(p.get("text", "")) for p in passages).casefold()
    passage_text = re.sub(r"[^a-z0-9%]+", " ", passage_text)
    for topic, aliases in topic_groups.items():
        if topic in q or any(alias in q for alias in aliases):
            if not any(re.sub(r"[^a-z0-9%]+", " ", alias).strip() in passage_text for alias in aliases):
                return False
    generic = STOPWORDS | {"dtu", "university", "college", "criteria", "criterion", "information", "policy", "policies"}
    terms = {_normalise(t) for t in re.findall(r"[a-zA-Z]{3,}", q) if t.casefold() not in generic}
    if not terms:
        return True
    passage_terms = {_normalise(t) for t in re.findall(r"[a-zA-Z]{3,}", passage_text)}
    overlap = terms & passage_terms
    required = 1 if len(terms) <= 2 else 2
    return len(overlap) >= required and len(overlap) / max(1, len(terms)) >= 0.2

def _normalise(term: str) -> str:
    aliases = {"exams": "examination", "exam": "examination", "examinations": "examination", "eligibility": "eligible", "requirements": "requirement", "required": "requirement", "backlogs": "backlog", "marks": "mark", "placements": "placement"}
    return aliases.get(term.casefold(), term.casefold())


def _passage_excerpt(passages: list[dict[str, Any]], limit: int = 700) -> str:
    if not passages:
        return NOT_FOUND
    # Keep the answer grounded by quoting retrieved text and leave exact provenance to the citation object.
    text = re.sub(r"^\[PAGE \d+\]\s*", "", str(passages[0].get("text", "")).strip())
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _tool_answer(result: dict[str, Any], category: str) -> str:
    synthetic = any(bool(x.get("synthetic")) for x in result.get("rules", [])) or bool(result.get("synthetic"))
    prefix = "Synthetic demo result (not an official DTU decision): " if synthetic else "Verified result: "
    if category == "exam_eligibility":
        return f"{prefix}attendance for {result['course_code']} is {result['attendance_pct']}%. The applicable rule is {result['threshold']} (rule {result['rule_id']}). Outcome: {result['result']}."
    if category == "placement_eligibility":
        return f"{prefix}CGPA {result['cgpa']:.2f} and active backlogs {result['active_backlogs']} were checked against the listed source-linked rules. Outcome: {result['result']}."
    if category == "supplementary_eligibility":
        return f"{prefix}the latest recorded result for {result['course_code']} is {result['latest_result']}. Outcome: {result['result']}."
    if category == "what_if_placement":
        return f"{prefix}assuming a supplementary PASS in {result['course_code']}, one backlog is cleared and CGPA remains unchanged. With CGPA {result['cgpa']:.2f} and {result['active_backlogs']} hypothetical active backlog(s), the placement demo outcome is {result['result']}. This is a hypothetical result, not a change to your record."
    return NOT_FOUND


def _synthesize(state: WorkflowState) -> WorkflowState:
    selected = state.get("selected", [])
    citations = _citations(selected)
    if state.get("tool_result"):
        result = state["tool_result"]
        answer = _tool_answer(result, state["category"])
        evidence = json_safe_text({"tool_result": result, "policy_passages": [p.get("text", "") for p in selected]})
        try:
            explanation, model, tokens = explain(state["question"], evidence, "calculated", mock_template=answer)
        except LLMUnavailable as exc:
            state["response"] = {"_http_status": 503, "detail": str(exc)}
            state["error_category"] = "llm_unavailable"
            return state
        state["model"] = model; state["tokens"] = tokens; state["llm_calls"] += 0 if MOCK_LLM else 1
        return _set_response(state, answer, "calculated", citations=citations, explanation=answer if MOCK_LLM else explanation)
    excerpt = _passage_excerpt(selected)
    evidence = "\\n\\n".join(p.get("text", "") for p in selected)
    try:
        explanation, model, tokens = explain(state["question"], evidence, "retrieved_fact", mock_template=excerpt)
    except LLMUnavailable as exc:
        state["response"] = {"_http_status": 503, "detail": str(exc)}
        state["error_category"] = "llm_unavailable"
        return state
    state["model"] = model; state["tokens"] = tokens; state["llm_calls"] += 0 if MOCK_LLM else 1
    # Real inference should return the grounded plain-language synthesis, not the raw source chunk.
    answer = explanation.strip() if not MOCK_LLM and explanation.strip() else excerpt
    if not answer or answer == NOT_FOUND:
        return _set_response(state, NOT_FOUND, "not_found", error="empty_grounded_answer")
    return _set_response(state, answer, "retrieved_fact", citations=citations, explanation=answer)


def json_safe_text(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)


def _validate(state: WorkflowState) -> WorkflowState:
    response = state.get("response", {})
    if response.get("_http_status"):
        return state
    if response.get("answer_type") in {"retrieved_fact", "calculated"} and not response.get("citations") and state.get("category") not in {"personal_attendance", "personal_profile", "personal_result"}:
        return _set_response(state, NOT_FOUND, "not_found", error="citation_validation_failed")
    valid_types = {"retrieved_fact", "calculated", "general_answer", "not_found", "clarification_needed", "refused", "conflict_flagged"}
    if response.get("answer_type") not in valid_types:
        return _set_response(state, NOT_FOUND, "not_found", error="invalid_answer_type")
    return state


def _audit_node(state: WorkflowState) -> WorkflowState:
    response = state.get("response", {})
    latency = round((time.perf_counter() - state.get("started", time.perf_counter())) * 1000)
    try:
        audit({
            "trace_id": state.get("trace_id", ""), "timestamp": datetime.now(timezone.utc).isoformat(),
            "question_category": state.get("category", "unknown"), "student_id": state.get("student_id") or "",
            "sources_retrieved": [{"doc_id": citation_from(p).get("doc_id"), "section": citation_from(p).get("section"), "page": citation_from(p).get("page"), "score": p.get("score")} for p in state.get("sources", [])],
            "precedence_decision": state.get("decision", ""), "tools_invoked": state.get("tools", []),
            "applied_rules": state.get("rules", []), "conflicts_detected": state.get("conflicts", []),
            "answer_type": response.get("answer_type", "not_found"), "model": state.get("model", "unknown"),
            "llm_calls": state.get("llm_calls", 0), "tokens": state.get("tokens", "unavailable"),
            "latency_ms": latency, "error_category": state.get("error_category", ""),
        })
    except Exception:
        # Audit failure must not turn a successful answer into fabricated output, but is retained in response metadata.
        response["audit_warning"] = "Audit record could not be persisted. Check local logs."
    return state


def _process_after_authorize(state: WorkflowState) -> WorkflowState:
    if state.get("response"):
        return state
    if state["category"] == "ambiguous":
        return _clarify(state)
    if state["category"] == "general_knowledge":
        # General questions may use pretrained Qwen knowledge, but never claim the answer is official policy.
        try:
            answer, model, tokens = explain(state["question"], "", "general_answer")
        except LLMUnavailable as exc:
            state["response"] = {"_http_status": 503, "detail": str(exc)}
            state["error_category"] = "llm_unavailable"
            return state
        state["model"] = model
        state["tokens"] = tokens
        state["llm_calls"] += 0 if MOCK_LLM else 1
        if not answer.strip():
            answer = "I could not generate a response. Please try again."
        return _set_response(state, answer, "general_answer", explanation=answer)
    if state["category"] == "policy":
        state = _retrieve(state)
        if not state.get("response", {}).get("_http_status"):
            state = _resolve(state)
        if not state.get("response"):
            state = _synthesize(state)
    else:
        state = _tool_node(state)
        if not state.get("response"):
            state = _retrieve(state)
            if not state.get("response", {}).get("_http_status"):
                state = _resolve(state)
            if not state.get("response"):
                state = _synthesize(state)
    if not state.get("response"):
        state = _set_response(state, NOT_FOUND, "not_found", error="empty_workflow_response")
    if not state.get("response", {}).get("_http_status"):
        state = _validate(state)
    return state


def _audit_graph_node(state: WorkflowState) -> WorkflowState:
    return _audit_node(state)


def _build_graph():
    if not LANGGRAPH_AVAILABLE:
        return None
    graph = StateGraph(WorkflowState)
    graph.add_node("intake", _intake)
    graph.add_node("authorize", _authorize)
    graph.add_node("process", _process_after_authorize)
    graph.add_node("audit", _audit_graph_node)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "authorize")
    graph.add_conditional_edges(
        "authorize",
        lambda s: "audit" if s.get("response") else "process",
        {"audit": "audit", "process": "process"},
    )
    graph.add_edge("process", "audit")
    graph.add_edge("audit", END)
    return graph.compile()


_GRAPH = None
_GRAPH_ERROR = None


def _execute_request(initial: dict[str, Any]) -> dict[str, Any]:
    state: WorkflowState = dict(initial)  # type: ignore[assignment]
    state = _intake(state)
    state = _authorize(state)
    state = _process_after_authorize(state)
    state = _audit_node(state)
    response = state.get("response", _response(state, NOT_FOUND, "not_found"))
    if response.get("_http_status"):
        response["_error_detail"] = response.pop("detail", "Assistant component unavailable")
    return response

def run_workflow(question: str, student_id: str | None, as_of_date: str | None = None) -> dict[str, Any]:
    """Invoke LangGraph's controlled workflow; direct execution is a lightweight test fallback."""
    global _GRAPH, _GRAPH_ERROR
    if _GRAPH is None and _GRAPH_ERROR is None and LANGGRAPH_AVAILABLE:
        try:
            _GRAPH = _build_graph()
        except Exception as exc:
            _GRAPH_ERROR = f"{type(exc).__name__}: {exc}"
    payload = {"question": question, "student_id": student_id, "as_of_date": as_of_date or date.today().isoformat()}
    if _GRAPH is None:
        return _execute_request(payload)
    result = _GRAPH.invoke(payload)
    response = result.get("response", _response({"as_of_date": payload["as_of_date"]}, NOT_FOUND, "not_found"))
    if response.get("_http_status"):
        response["_error_detail"] = response.pop("detail", "Assistant component unavailable")
    return response
