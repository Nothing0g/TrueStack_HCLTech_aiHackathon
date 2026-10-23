from __future__ import annotations
import csv, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db import source_register_rows
FIELDS=["doc_id","title","issuer","authority_level","doc_type","version","effective_from","effective_to","supersedes","scope_programmes","scope_batches","provenance","retrieved_on","synthetic"]
rows=source_register_rows(); target=ROOT/"data"/"source_register.csv"; target.parent.mkdir(parents=True,exist_ok=True)
with target.open("w",newline="",encoding="utf-8") as fh:
    writer=csv.DictWriter(fh,fieldnames=FIELDS,extrasaction="ignore"); writer.writeheader()
    for row in rows: writer.writerow({k:row.get(k,"") for k in FIELDS})
print(f"Exported {len(rows)} source records to {target}")
