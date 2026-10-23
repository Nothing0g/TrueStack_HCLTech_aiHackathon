from __future__ import annotations
import argparse, json, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db import init_db, connect
REQUIRED={"description","parameter","operator","value","scope_programmes","scope_batches","effective_from","effective_to","source_doc_id","source_section"}

def main() -> int:
    parser=argparse.ArgumentParser(description="Create an inactive candidate rule from explicit, reviewable fields")
    parser.add_argument("--input",required=True,help="JSON file containing one candidate rule")
    args=parser.parse_args(); payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    missing=REQUIRED-set(payload)
    if missing: raise SystemExit(f"Missing fields: {sorted(missing)}")
    candidate_id="CAND-"+uuid.uuid4().hex[:10].upper(); init_db()
    with connect() as conn:
        conn.execute("INSERT INTO candidate_rules (candidate_id,payload_json,status,created_at,validation_message) VALUES (?,?,?,?,?)",(candidate_id,json.dumps(payload,ensure_ascii=False),"candidate",datetime.now(timezone.utc).isoformat(),"Not yet validated; inactive"))
    print(json.dumps({"candidate_id":candidate_id,"status":"candidate","message":"Rule is inactive. Validate and activate only after checking the source clause."},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
