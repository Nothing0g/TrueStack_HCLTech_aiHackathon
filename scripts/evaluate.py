from __future__ import annotations
import argparse, json, statistics, time
from datetime import datetime, timezone
from pathlib import Path
import sys
import requests
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# API URL is read from environment below; do not couple the evaluator to app config.


def _equal(actual, expected) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(actual) - float(expected)) < 1e-9
        except (TypeError, ValueError):
            return False
    return actual == expected


def _find_field(value, field):
    """Find a field within nested structured tool outputs without calling app tools."""
    if isinstance(value, dict):
        if field in value:
            yield value[field]
        for child in value.values():
            yield from _find_field(child, field)
    elif isinstance(value, list):
        for child in value:
            yield from _find_field(child, field)


def validate_cases(cases: list[dict]) -> list[str]:
    errors: list[str] = []
    if len(cases) < 20:
        errors.append("Evaluation set must contain at least 20 cases.")
    ids = [c.get("test_id") for c in cases]
    if len(set(ids)) != len(ids) or any(not x for x in ids):
        errors.append("Evaluation set has duplicate or missing test IDs.")
    if any(not c.get("expected_answer_type") for c in cases):
        errors.append("Every evaluation case needs expected_answer_type.")
    categories = [str(c.get("category", "")).casefold() for c in cases]
    if sum("unanswerable" in c for c in categories) < 3:
        errors.append("Need at least three unanswerable cases.")
    if sum(any(token in c for token in ("version", "conflict", "future_policy")) for c in categories) < 3:
        errors.append("Need at least three version/conflict/future-policy cases.")
    if sum(bool(c.get("expected_tool")) and bool(c.get("student_id")) for c in cases) < 4:
        errors.append("Need at least four personal questions with expected deterministic tools.")
    cross_student_cases = [
        c for c in cases
        if "privacy" in str(c.get("category", "")).casefold()
        and c.get("student_id")
        and __import__("re").search(r"\bS\d{4}\b", str(c.get("question", "")), flags=__import__("re").I)
    ]
    if len(cross_student_cases) < 2:
        errors.append("Need at least two cross-student access-attempt cases.")
    if sum("multi_step" in c for c in categories) < 2:
        errors.append("Need at least two multi-step cases.")
    for case in cases:
        if case.get("expected_tool") and case.get("expected_answer_type") == "calculated" and not case.get("expected_tool_values"):
            errors.append(f"{case.get('test_id')}: calculated tool case needs independent expected_tool_values.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the committed evaluation set against a running TrueStack API.")
    parser.add_argument("--base-url", default=__import__("os").getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--check-only", action="store_true", help="Validate evaluation-set structure without sending requests.")
    args = parser.parse_args()
    cases = json.loads((ROOT / "data" / "evaluation_set.json").read_text(encoding="utf-8"))
    case_errors = validate_cases(cases)
    if case_errors:
        raise SystemExit("Evaluation-set validation FAILED:\n- " + "\n- ".join(case_errors))
    if args.check_only:
        print(f"Evaluation-set structure PASS: {len(cases)} unique cases; required categories and independent tool-value oracles present.")
        return 0

    results = []
    latencies = []
    for case in cases:
        headers = {}
        if case.get("student_id"):
            headers["X-Student-Id"] = case["student_id"]
        payload = {"question": case["question"], "as_of_date": case.get("as_of_date")}
        started = time.perf_counter()
        item = {"test_id": case["test_id"], "category": case.get("category"), "expected_answer_type": case["expected_answer_type"]}
        try:
            response = requests.post(f"{args.base_url.rstrip('/')}/ask", json=payload, headers=headers, timeout=args.timeout)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            item.update({"http_status": response.status_code, "latency_ms": elapsed_ms})
            if response.status_code >= 400:
                item.update({"status": "ERROR", "error": response.text[:500]})
            else:
                body = response.json()
                answer = str(body.get("answer", ""))
                answer_type_ok = body.get("answer_type") == case["expected_answer_type"]
                expected_terms_ok = all(term.casefold() in answer.casefold() for term in case.get("expected_contains", []))
                cited_ids = {str(c.get("doc_id")) for c in body.get("citations", [])}
                source_ids_ok = set(case.get("expected_source_ids", [])).issubset(cited_ids) if case.get("expected_source_ids") else True
                actual_tools = {str(t.get("tool")) for t in body.get("tools_invoked", [])}
                tool_ok = case.get("expected_tool") in actual_tools if case.get("expected_tool") else True
                tool_outputs = [t.get("output", {}) for t in body.get("tools_invoked", []) if isinstance(t, dict)]
                expected_values = case.get("expected_tool_values", [])
                tool_value_checks = []
                for expected in expected_values:
                    field = expected.get("field")
                    value = expected.get("equals")
                    candidates = list(_find_field(tool_outputs, field)) if field else []
                    tool_value_checks.append({"field": field, "expected": value, "actual_candidates": candidates,
                                              "passed": any(_equal(actual, value) for actual in candidates)})
                tool_values_ok = all(row["passed"] for row in tool_value_checks)
                # This compares tool outputs against independent expected fixture values;
                # citations still require manual inspection to certify actual support.
                passed = answer_type_ok and expected_terms_ok and source_ids_ok and tool_ok and tool_values_ok
                item.update({"status": "PASS" if passed else "FAIL", "actual_answer_type": body.get("answer_type"), "answer_type_ok": answer_type_ok, "expected_terms_ok": expected_terms_ok, "expected_source_ids": case.get("expected_source_ids", []), "cited_source_ids": sorted(cited_ids), "source_ids_ok": source_ids_ok, "expected_tool": case.get("expected_tool"), "actual_tools": sorted(actual_tools), "tool_ok": tool_ok, "expected_tool_values": expected_values, "tool_value_checks": tool_value_checks, "tool_values_ok": tool_values_ok, "trace_id": body.get("trace_id"), "answer_excerpt": answer[:800]})
                if body.get("answer_type") == "retrieved_fact" and body.get("citations"):
                    item["citation_support_manual_review"] = "PENDING — verify cited passage and page against source document"
            latencies.append(elapsed_ms)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            item.update({"status": "ERROR", "latency_ms": elapsed_ms, "error": f"{type(exc).__name__}: {exc}"})
        results.append(item)
        print(f"{item['test_id']}: {item['status']}")

    total = len(results)
    passed = sum(r["status"] == "PASS" for r in results)
    failed = sum(r["status"] == "FAIL" for r in results)
    errors = sum(r["status"] == "ERROR" for r in results)
    tool_value_cases = [r for r in results if r.get("expected_tool_values")]
    tool_value_passes = sum(bool(r.get("tool_values_ok")) for r in tool_value_cases)
    measured = sorted(latencies)
    def percentile(values: list[float], q: float) -> float | None:
        if not values: return None
        idx = round((len(values)-1)*q)
        return round(values[idx], 2)
    summary = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url, "cases": total, "passed": passed, "failed": failed, "errors": errors, "pass_rate_all_cases": round(passed / total, 4), "p50_latency_ms": percentile(measured, .5), "p95_latency_ms": percentile(measured, .95), "tool_value_cases": len(tool_value_cases), "tool_value_checks_passed": tool_value_passes, "tool_value_accuracy": (round(tool_value_passes / len(tool_value_cases), 4) if tool_value_cases else None), "citation_support_manual_review_required": True, "results": results}
    report_json = ROOT / "reports" / "evaluation_results.json"
    report_md = ROOT / "reports" / "evaluation_report.md"
    report_json.parent.mkdir(exist_ok=True)
    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Evaluation Report", "", f"- Run time (UTC): {summary['timestamp_utc']}", f"- API: `{args.base_url}`", f"- Cases: {total}", f"- Passed automated checks: {passed}", f"- Failed automated checks: {failed}", f"- Errors/unavailable calls: {errors}", f"- Pass rate across all cases (errors count as not passed): {summary['pass_rate_all_cases']:.1%}", f"- p50 measured latency: {summary['p50_latency_ms']} ms", f"- p95 measured latency: {summary['p95_latency_ms']} ms", f"- Independent tool-value cases passed: {tool_value_passes}/{len(tool_value_cases)}", "", "## Interpretation", "", "Automated checks compare answer type, expected terms, expected source IDs, tool selection and structured tool outputs against pre-recorded expected values. This is not a substitute for manually checking that cited passages support each claim. Latencies describe this run and machine only.", "", "## Per-case results", "", "| Test | Category | Status | HTTP | Latency ms | Answer type |", "|---|---|---:|---:|---:|---|"]
    for r in results:
        lines.append(f"| {r.get('test_id')} | {r.get('category')} | {r.get('status')} | {r.get('http_status','—')} | {r.get('latency_ms','—')} | {r.get('actual_answer_type', r.get('expected_answer_type','—'))} |")
    lines += ["", "Raw details: `evaluation_results.json`. Errors are not counted as successful answers."]
    report_md.write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Results: {passed} pass, {failed} fail, {errors} error out of {total}. Reports: {report_md}")
    return 0 if failed == 0 and errors == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())
