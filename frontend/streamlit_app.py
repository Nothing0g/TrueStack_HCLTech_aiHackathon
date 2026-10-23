from __future__ import annotations
import os
import json
from datetime import date
import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
NOT_FOUND = "I could not find this information in the authorised university sources."

st.set_page_config(page_title="TrueStack · Student Services", page_icon="🎓", layout="wide")
st.markdown("""
<style>
:root { color-scheme:light; --ink:#172b28; --muted:#62736e; --line:#dfe7e2; --paper:#f6f8f5; --accent:#1e6b5c; --accent-soft:#e7f2ed; }
html, body, [data-testid="stAppViewContainer"], .stApp { background:var(--paper) !important; color:var(--ink) !important; }
[data-testid="stHeader"] { background:rgba(246,248,245,.94) !important; }
.block-container { padding-top:1.7rem !important; padding-bottom:7rem !important; max-width:1160px !important; }
section[data-testid="stSidebar"] { background:#edf3ef !important; border-right:1px solid var(--line) !important; }
section[data-testid="stSidebar"] * { color:var(--ink); }
.ts-kicker { color:var(--accent); font-size:.72rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; }
.ts-title { color:var(--ink) !important; font-size:2.15rem; font-weight:750; line-height:1.12; letter-spacing:-.045em; margin:.35rem 0 .55rem; }
.ts-sub { color:var(--muted) !important; font-size:1rem; max-width:760px; line-height:1.6; }
.ts-panel { border:1px solid var(--line); border-radius:14px; background:#fff; padding:16px 18px; }
.ts-chip { display:inline-block; border:1px solid var(--line); background:#fff; border-radius:999px; padding:5px 10px; font-size:.78rem; color:#34584f; }
div[data-testid="stChatMessage"] { border:1px solid var(--line) !important; border-radius:14px !important; background:#fff !important; padding:1rem 1.15rem !important; box-shadow:0 2px 8px rgba(21,45,38,.035); }
div[data-testid="stChatMessage"] p, div[data-testid="stChatMessage"] li { color:var(--ink) !important; line-height:1.65 !important; }
.stButton button { border-radius:10px !important; border:1px solid #d5e2db !important; min-height:2.65rem; color:#214b40 !important; background:#fff !important; font-weight:600 !important; }
.stButton button:hover { border-color:var(--accent) !important; background:var(--accent-soft) !important; }
button[kind="primary"], [data-testid="stFormSubmitButton"] button { background:var(--accent) !important; color:#fff !important; border-color:var(--accent) !important; }
[data-testid="stChatInput"] { background:#fff !important; border:1px solid #cddbd3 !important; border-radius:14px !important; }
[data-testid="stChatInput"] textarea { color:var(--ink) !important; }
[data-testid="stExpander"] { border:1px solid var(--line) !important; border-radius:12px !important; background:#fff !important; }
[data-testid="stCaptionContainer"] { color:var(--muted) !important; }
hr { border-color:var(--line) !important; }
</style>
""", unsafe_allow_html=True)

if "messages" not in st.session_state: st.session_state.messages = []
if "student_id" not in st.session_state: st.session_state.student_id = "S1001"

with st.sidebar:
    st.markdown('<div class="ts-kicker">TRUESTACK · HACKATHON DEMO</div>', unsafe_allow_html=True)
    st.markdown("### Student services")
    st.caption("A local-first assistant for general questions, sourced university policies, and demo student records.")
    st.divider()
    try:
        health = requests.get(f"{API}/health", timeout=3).json()
        st.success("API reachable" if health.get("api") == "ready" else "API degraded")
        st.caption(f"Retrieval: {health.get('chromadb', {}).get('status', 'unknown')}")
        st.caption(f"LLM: {health.get('llm', 'unknown')}")
    except Exception:
        health = {}
        st.error("API not reachable")
        st.caption("Start the backend using the README instructions.")
    st.divider()
    st.markdown("**Demo identity**")
    identity_options = ["S1001 — Aarav Mehta", "S1002 — Ananya Rao", "S1003 — Ishaan Verma", "S1004 — Mira Kapoor", "S1005 — Kabir Sinha", "S1006 — Diya Nair", "S1007 — Reyansh Bhatia", "No student / general question"]
    current = next((x for x in identity_options if x.startswith(st.session_state.student_id + " —")), "S1001 — Aarav Mehta") if st.session_state.student_id else "No student / general question"
    chosen = st.selectbox("Synthetic student", identity_options, index=identity_options.index(current))
    st.session_state.student_id = None if chosen.startswith("No student") else chosen.split(" — ")[0]
    st.caption("Synthetic identities only. The selector sends the chosen ID as X-Student-Id for local demo requests.")
    if st.button("New conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.markdown("<span class='ts-chip'>Local data · SQLite + ChromaDB</span>", unsafe_allow_html=True)

st.markdown('<div class="ts-kicker">University knowledge, clearly sourced</div>', unsafe_allow_html=True)
st.markdown('<div class="ts-title">Your student services, in one place.</div>', unsafe_allow_html=True)
st.markdown('<div class="ts-sub">Ask general questions, ask about university policies and procedures, or check synthetic student records. Policy answers cite retrieved sources; calculations come from deterministic Python tools.</div>', unsafe_allow_html=True)
st.write("")

with st.expander("Add a policy document", expanded=False):
    st.caption("Upload a document to the running API. New text becomes searchable after successful indexing. Uploaded synthetic policies must be clearly labelled; indexing does not automatically activate calculation rules.")
    with st.form("document_ingestion_form", clear_on_submit=False):
        uploaded = st.file_uploader("Policy file (PDF, DOCX, Markdown or TXT)", type=["pdf", "docx", "md", "txt"], key="policy_upload")
        st.markdown("**Optional document details**")
        st.caption("Only choose a file to get started. Leave details blank if you do not know them; sensible defaults will be generated. Examples are shown under each field.")
        c1, c2 = st.columns(2)
        with c1:
            doc_id = st.text_input("Document ID (optional)", placeholder="Example: DTU-EXAM-2026-001", help="A short unique label. Leave blank to generate one from the filename.")
            title = st.text_input("Document title (optional)", placeholder="Example: Examination Eligibility Notice", help="The document's heading or a descriptive title. Leave blank to use the filename.")
            issuer = st.text_input("Issuing authority (optional)", placeholder="Example: DTU Examination Branch", help="Who published it, if known. Leave blank to mark the issuer as not provided.")
            authority_level = st.selectbox("Authority level", [1, 2, 3, 4, 5], index=2, help="1 = highest authority, 5 = unofficial/lowest. If unsure, keep the default and verify later.")
            doc_type = st.selectbox("Document type", ["regulation", "circular", "notice", "faq", "handbook", "unofficial"])
            version = st.text_input("Version (optional)", placeholder="Example: 2026-08-24 or v2", help="Use the date/version printed on the document. Leave blank to use upload date.")
        with c2:
            effective_from = st.text_input("Effective from (optional)", placeholder="Example: 2026-08-24", help="YYYY-MM-DD. Leave blank if the document does not state this.")
            effective_to = st.text_input("Effective to (optional)", placeholder="Example: 2027-06-30", help="YYYY-MM-DD. Leave blank if no expiry is stated.")
            scope_programmes = st.text_input("Programme scope", value="ALL", help="Example: ALL or BTech; MTech. Keep ALL if unsure.")
            scope_batches = st.text_input("Batch scope", value="ALL", help="Example: ALL, 2024, 2023+ or 2022;2023. Keep ALL if unsure.")
            supersedes = st.text_input("Supersedes document/clause (optional)", placeholder="Example: DTU-OLD-REG-2024#7.2", help="Fill only when this document explicitly replaces an older rule.")
            provenance = st.text_input("Source URL or provenance (optional)", placeholder="Example: DTU website URL or 'PDF provided by user'", help="Where it came from. Leave blank to record that it was user-uploaded.")
            synthetic = st.selectbox("Source status", ["N", "Y"], format_func=lambda x: "Official / non-synthetic" if x == "N" else "Synthetic demo", help="Choose Synthetic demo for invented/test documents. Do not label an unverified upload as officially verified.")
        upload_submitted = st.form_submit_button("Validate and index document", type="primary", use_container_width=True)
    if upload_submitted:
        if uploaded is None:
            st.error("Choose a file before submitting.")
        else:
            from pathlib import Path
            import re
            today = date.today().isoformat()
            filename_stem = Path(uploaded.name).stem
            safe_stem = re.sub(r"[^A-Za-z0-9]+", "-", filename_stem).strip("-").upper()[:48] or "UPLOADED-DOCUMENT"
            resolved_doc_id = doc_id.strip() or f"UPLOAD-{safe_stem}-{today.replace('-', '')}"
            resolved_title = title.strip() or filename_stem.replace("_", " ").replace("-", " ").strip() or uploaded.name
            resolved_issuer = issuer.strip() or "Not provided in upload metadata"
            resolved_version = version.strip() or f"uploaded-{today}"
            resolved_provenance = provenance.strip() or f"User-uploaded file: {uploaded.name}"
            title_value = resolved_title
            if synthetic == "Y" and "SYNTHETIC DEMO" not in title_value.upper():
                title_value = "SYNTHETIC DEMO — " + title_value
            metadata = {
                "doc_id": resolved_doc_id, "title": title_value, "issuer": resolved_issuer,
                "authority_level": int(authority_level), "doc_type": doc_type, "version": resolved_version,
                "effective_from": effective_from.strip(), "effective_to": effective_to.strip(),
                "supersedes": supersedes.strip(), "scope_programmes": scope_programmes.strip() or "ALL",
                "scope_batches": scope_batches.strip() or "ALL", "provenance": resolved_provenance,
                "retrieved_on": today, "synthetic": synthetic,
            }
            try:
                upload_headers = {"X-Student-Id": st.session_state.student_id} if st.session_state.student_id else {}
                with st.spinner("Validating source metadata and indexing document…"):
                    result = requests.post(
                        f"{API}/ingest", files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
                        data={"metadata": __import__("json").dumps(metadata)}, timeout=240,
                    )
                if result.status_code >= 400:
                    detail = result.json().get("detail", result.text) if "application/json" in result.headers.get("content-type", "") else result.text
                    st.error(f"Ingestion failed (HTTP {result.status_code}): {detail}")
                else:
                    st.success(f"Ingestion result: {result.json()}")
                    st.caption("If this document introduces a numeric eligibility threshold, validate and activate that rule separately; uploaded text alone cannot change calculator behaviour.")
            except requests.RequestException as exc:
                st.error(f"Could not reach the ingestion API: {exc}")


sample_questions = [
    "What is the minimum attendance requirement for exam eligibility?",
    "What is my attendance in CS201?",
    "Am I eligible to sit the exam for CS201?",
    "What does the placement policy say about CGPA cutoffs?",
]
cols = st.columns(4)
for i, q in enumerate(sample_questions):
    if cols[i].button(q, key=f"sample_{i}", use_container_width=True, help="Submits this question to the live backend"):
        st.session_state.pending_question = q
if st.button("Try general Q&A · Explain machine learning in simple terms", key="sample_general", use_container_width=True, help="Uses Qwen directly without policy retrieval"):
    st.session_state.pending_question = "Explain machine learning in simple terms."

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("response"):
            resp = msg["response"]
            for c in resp.get("citations", []):
                synthetic = c.get("synthetic", False)
                label = "SYNTHETIC DEMO — NOT OFFICIAL DTU POLICY" if synthetic else "Official source"
                st.caption(f"{label} · {c.get('title') or c.get('doc_id')} · Section {c.get('section') or 'not identified'} · Page {c.get('page') or 'not identified'} · Version {c.get('version') or 'not recorded'} · Effective {c.get('effective_from') or 'not recorded'}")
            with st.expander("Trace and verification details"):
                st.json({k: resp.get(k) for k in ["trace_id", "answer_type", "tools_invoked", "applied_rules", "conflicts_detected", "as_of_date"]})

question = st.chat_input("Ask a general question, university policy question, or student-record question…")
if not question and st.session_state.get("pending_question"):
    question = st.session_state.pop("pending_question")

if question:
    st.session_state.messages.append({"role":"user", "content":question})
    with st.chat_message("user"): st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Checking authorised sources and records…"):
            try:
                headers = {"X-Student-Id": st.session_state.student_id} if st.session_state.student_id else {}
                r = requests.post(f"{API}/ask", json={"question":question}, headers=headers, timeout=120)
                if r.status_code >= 400:
                    body = r.json() if "application/json" in r.headers.get("content-type", "") else {"detail":r.text}
                    st.error(f"The request could not be completed (HTTP {r.status_code}). {body.get('detail', body)}")
                    st.session_state.messages.append({"role":"assistant", "content":f"The request could not be completed (HTTP {r.status_code})."})
                else:
                    resp = r.json()
                    answer = resp.get("answer", NOT_FOUND)
                    st.markdown(answer)
                    if resp.get("answer_type") == "not_found": st.info(NOT_FOUND)
                    for c in resp.get("citations", []):
                        label = "SYNTHETIC DEMO — NOT OFFICIAL DTU POLICY" if c.get("synthetic") else "Source"
                        st.caption(f"{label} · {c.get('title') or c.get('doc_id')} · Section {c.get('section') or 'not identified'} · Page {c.get('page') or 'not identified'} · Version {c.get('version') or 'not recorded'} · Effective {c.get('effective_from') or 'not recorded'}")
                    with st.expander("Trace and verification details"):
                        st.json({k: resp.get(k) for k in ["trace_id", "answer_type", "tools_invoked", "applied_rules", "conflicts_detected", "as_of_date"]})
                    st.session_state.messages.append({"role":"assistant", "content":answer, "response":resp})
            except requests.RequestException:
                st.error("Could not connect to the API. Check the backend and its /health endpoint.")
                st.session_state.messages.append({"role":"assistant", "content":"Could not connect to the API. Check backend health."})
