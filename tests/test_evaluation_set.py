from __future__ import annotations
import json
from pathlib import Path
from scripts.evaluate import validate_cases

ROOT = Path(__file__).resolve().parents[1]

def test_committed_evaluation_set_has_required_coverage_and_independent_oracles():
    cases = json.loads((ROOT / "data" / "evaluation_set.json").read_text(encoding="utf-8"))
    assert len(cases) >= 20
    assert validate_cases(cases) == []
    for case in cases:
        if case.get("expected_tool") and case.get("expected_answer_type") == "calculated":
            assert case.get("expected_tool_values"), case["test_id"]
