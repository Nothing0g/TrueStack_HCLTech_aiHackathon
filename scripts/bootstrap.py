from __future__ import annotations
import csv, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db import init_db, seed_sources_and_rules, source_register_rows
from app.main import _export_source_register

def main() -> int:
    init_db()
    try:
        seed_sources_and_rules()
        _export_source_register()
        rows=source_register_rows()
        print(f"Bootstrap complete: {len(rows)} source(s) registered.")
        print("Synthetic demo rules seeded from the bundled synthetic documents; no official DTU threshold is being claimed.")
        return 0
    except Exception as exc:
        print(f"Bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Ensure dependencies are installed and the embedding model can be loaded.", file=sys.stderr)
        return 1

if __name__=="__main__": raise SystemExit(main())
