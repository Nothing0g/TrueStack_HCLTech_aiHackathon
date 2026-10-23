from __future__ import annotations
import argparse, json, re, sys
from datetime import date, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db import init_db, connect, source_register_rows
from app.rag import search_document
ALLOWED_OPS={">=",">","<=","<","==","!=","between"}

def clause_is_indexed(section: str, chunks: list[dict]) -> bool:
    """Verify a real clause or page anchor without requiring citation notes to be verbatim.

    Rule rows may keep human-readable notes after a semicolon, for example
    ``R.1(B).22; PDF page 25``. Check the clause token and page anchor separately.
    """
    token = section.strip().casefold()
    if not token:
        return False
    blob = "\n".join([c.get("text", "") + " " + str(c.get("metadata", {}).get("section", "")) for c in chunks]).casefold()
    clauses = [part.strip() for part in token.split(";") if part.strip()]
    for clause in clauses:
        page_match = re.fullmatch(r"(?:pdf\s*)?page\s*(\d+)", clause)
        if page_match and any(str(c.get("metadata", {}).get("page", "")) == page_match.group(1) for c in chunks):
            return True
        # Normalize punctuation so OCR spacing such as R. I(B).22 is still checkable.
        compact_clause = re.sub(r"[^a-z0-9]", "", clause)
        compact_blob = re.sub(r"[^a-z0-9]", "", blob)
        if compact_clause and compact_clause in compact_blob:
            return True
    return False

def validate_payload(payload: dict, source: dict, candidate_sources: dict) -> list[str]:
    errors=[]
    if source.get("status") not in {"indexed", "registered"}: errors.append("source is not registered as usable")
    if source.get("synthetic")=="Y" and "SYNTHETIC DEMO" not in str(source.get("title","")).upper(): errors.append("synthetic source title must display SYNTHETIC DEMO")
    if payload["operator"] not in ALLOWED_OPS: errors.append(f"unsupported operator {payload['operator']!r}")
    if not str(payload["parameter"]).strip() or not str(payload["value"]).strip(): errors.append("parameter and value must be non-empty")
    try:
        start=date.fromisoformat(payload["effective_from"])
        end=date.fromisoformat(payload["effective_to"]) if payload.get("effective_to") else None
        if end and end < start: errors.append("effective_to cannot be before effective_from")
    except ValueError: errors.append("rule dates must use YYYY-MM-DD")
    for key in ["scope_programmes","scope_batches"]:
        if not str(payload.get(key,"ALL")).strip(): errors.append(f"{key} must be ALL or a non-empty scope")
    if payload.get("supersedes") and not source.get("supersedes"):
        errors.append("candidate mentions supersession but source metadata does not; update Source Register metadata first")
    return errors

def main() -> int:
    parser=argparse.ArgumentParser(description="Validate a candidate rule's source, clause, dates and supersession before activation")
    parser.add_argument("candidate_id"); args=parser.parse_args(); init_db()
    with connect() as conn:
        row=conn.execute("SELECT * FROM candidate_rules WHERE candidate_id=?",(args.candidate_id,)).fetchone()
    if not row: raise SystemExit(f"Candidate not found: {args.candidate_id}")
    if row["status"]=="active": raise SystemExit("Candidate is already active")
    payload=json.loads(row["payload_json"]); sources={s["doc_id"]:s for s in source_register_rows()}
    source=sources.get(payload.get("source_doc_id"))
    if not source: errors=[f"source_doc_id {payload.get('source_doc_id')} does not exist in Source Register"]
    else:
        errors=validate_payload(payload,source,sources)
        try:
            chunks=search_document(source["doc_id"])
            if not chunks: errors.append("source has no indexed chunks")
            elif not clause_is_indexed(payload.get("source_section",""),chunks): errors.append("source_section cannot be verified in indexed source text/page metadata")
        except Exception as exc: errors.append(f"source retrieval failed: {type(exc).__name__}")
    with connect() as conn:
        conn.execute("UPDATE candidate_rules SET status=?,validation_message=? WHERE candidate_id=?",("rejected" if errors else "validated", "; ".join(errors) if errors else "Source and clause validated; waiting for this explicit activation command", args.candidate_id))
        if errors:
            print("Rule remains inactive:")
            for err in errors: print("-",err)
            return 1
        # Any replacement is linked to explicit source-register supersedes metadata; do not infer from values alone.
        supersedes=str(source.get("supersedes", ""))
        cutoff=(date.fromisoformat(payload["effective_from"])-timedelta(days=1)).isoformat()
        for item in [x.strip() for x in supersedes.split(";") if x.strip()]:
            old_doc, _, old_clause=item.partition("#")
            query="SELECT rule_id, source_section, effective_from FROM rule_registry WHERE source_doc_id=? AND parameter=? AND active=1"
            params=[old_doc,payload["parameter"]]
            for old in conn.execute(query,params).fetchall():
                if old_clause and old["source_section"] != old_clause: continue
                if old["effective_from"] < payload["effective_from"]:
                    conn.execute("UPDATE rule_registry SET effective_to=? WHERE rule_id=?",(cutoff,old["rule_id"]))
        # Rule data is stored as explicit inputs; no PDF-extracted number is activated automatically.
        rule_id=str(payload.get("rule_id") or "RULE-"+args.candidate_id.removeprefix("CAND-"))
        conn.execute("INSERT INTO rule_registry (rule_id,description,parameter,operator,value,scope_programmes,scope_batches,effective_from,effective_to,source_doc_id,source_section,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",(
            rule_id,payload["description"],payload["parameter"],payload["operator"],str(payload["value"]),payload.get("scope_programmes","ALL"),payload.get("scope_batches","ALL"),payload["effective_from"],payload.get("effective_to",""),payload["source_doc_id"],payload["source_section"]))
        conn.execute("UPDATE candidate_rules SET status='active',validation_message=? WHERE candidate_id=?",(f"Activated as {rule_id}; original source clause preserved",args.candidate_id))
    print(json.dumps({"candidate_id":args.candidate_id,"rule_id":rule_id,"status":"active","source_doc_id":source["doc_id"],"source_section":payload["source_section"]},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
