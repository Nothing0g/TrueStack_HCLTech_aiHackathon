from __future__ import annotations
import argparse,csv,json,sys
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.db import init_db,seed_source_metadata_and_rules,active_rules,source_register_rows


def _fields_csv(path:Path,rows:list[dict],fields:list[str])->None:
    with path.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=fields);w.writeheader();w.writerows(rows)

def _rule(parameter:str,as_of_date:str,programme:str="B.Tech CSE",prefer_synthetic:bool=False):
    rows=active_rules(as_of_date,parameter,programme,None)
    sources={x["doc_id"]:x for x in source_register_rows()}
    candidates=[r for r in rows if sources.get(r["source_doc_id"],{}).get("synthetic")==("Y" if prefer_synthetic else "N")]
    if not candidates: candidates=rows
    if len(candidates)!=1:
        uniq={(r["rule_id"],r["operator"],r["value"],r["source_doc_id"]) for r in candidates}
        if len(uniq)!=1: raise ValueError(f"Missing or ambiguous rule for {parameter}: {candidates}")
    return candidates[0]

def patch(directory:Path,as_of_date:str)->dict:
    init_db();seed_source_metadata_and_rules()
    attendance_rule=_rule("min_attendance_pct",as_of_date)
    pass_rule=_rule("pass_pct",as_of_date)
    placement_rows=active_rules(as_of_date,"placement_min_cgpa","B.Tech CSE",None)
    placement=[r for r in placement_rows if r["rule_id"]=="PLACE-CGPA-01"]
    att_path=directory/"attendance.csv";res_path=directory/"results.csv";stu_path=directory/"students.csv"
    def read(path):
        with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
    atts=read(att_path);results=read(res_path);students=read(stu_path)
    # Exact attendance boundaries use 100 held classes so fractional rounding cannot
    # accidentally put the one-class-below case above the threshold.
    threshold=float(attendance_rule["value"]);attended_exact=round(threshold)
    if attendance_rule["operator"] not in {">=",">"}:raise ValueError("Edge patch expects a minimum-attendance operator for the current dataset")
    if attendance_rule["operator"]==">":attended_exact=int(threshold)+1
    if not 0<=attended_exact<=100:raise ValueError("Attendance threshold is not a valid percentage")
    for r in atts:
        if r["student_id"]=="S1001" and r["course_code"]=="CS201":r.update(classes_held="100",classes_attended=str(attended_exact))
        if r["student_id"]=="S1002" and r["course_code"]=="CS201":r.update(classes_held="100",classes_attended=str(max(0,attended_exact-1)))
    pass_pct=float(pass_rule["value"]);operator=pass_rule["operator"]
    if operator not in {">=",">"}:raise ValueError("Synthetic pass-edge patch expects >= or > rule")
    # `floor` works for the >= threshold; one mark less than the smallest integer
    # that passes the rule is a guaranteed FAIL boundary.
    pass_min=(int(pass_pct) if pass_pct.is_integer() else int(pass_pct)+1) if operator==">=" else int(pass_pct)+1
    fail_total=max(0,pass_min-1)
    for r in results:
        if r["student_id"]=="S1003" and r["course_code"]=="CS201":r.update(internal_marks=str(min(20,fail_total)),external_marks=str(max(0,fail_total-min(20,fail_total))),total_marks=str(fail_total),max_marks="100",result="FAIL")
        if r["student_id"]=="S1004" and r["course_code"]=="CS201":r.update(internal_marks="0",external_marks="0",total_marks="0",max_marks="100",result="ABSENT")
        if r["student_id"]=="S1005" and r["course_code"]=="CS201":r.update(internal_marks="0",external_marks="0",total_marks="0",max_marks="100",result="DETAINED")
        if r["student_id"]=="S1006" and r["course_code"].startswith("CS"):
            # Deliberately mark this student's three CSE courses failed for the multi-backlog edge case.
            r.update(internal_marks=str(min(10,fail_total)),external_marks=str(max(0,fail_total-min(10,fail_total))),total_marks=str(fail_total),max_marks="100",result="FAIL")
        if r["student_id"]=="S1007":r.update(internal_marks="25",external_marks="35",total_marks="60",max_marks="100",result="PASS")
    # Profiles must reflect relational results rather than a profile seed's stale backlog field.
    counts={s["student_id"]:sum(r["student_id"]==s["student_id"] and r["result"]!="PASS" for r in results) for s in students}
    for s in students:
        s["active_backlogs"]=str(counts[s["student_id"]])
        if s["student_id"]=="S1007" and placement:s["cgpa"]=str(float(placement[0]["value"]))
    _fields_csv(att_path,atts,["student_id","course_code","classes_held","classes_attended"])
    _fields_csv(res_path,results,["student_id","course_code","exam_session","exam_type","internal_marks","external_marks","total_marks","max_marks","result"])
    _fields_csv(stu_path,students,["student_id","full_name","programme","batch_year","current_semester","cgpa","active_backlogs"])
    summary={"attendance_rule":attendance_rule["rule_id"],"attendance_threshold":threshold,"exact_case":{"student":"S1001","course":"CS201","held":100,"attended":attended_exact},"one_class_below":{"student":"S1002","course":"CS201","held":100,"attended":max(0,attended_exact-1)},"pass_rule":pass_rule["rule_id"],"pass_percent":pass_pct,"one_mark_below_pass_result":{"student":"S1003","course":"CS201","total_marks":fail_total},"absent":"S1004/CS201","detained":"S1005/CS201","multiple_backlogs":"S1006","placement_boundary_student":"S1007","placement_cutoff":float(placement[0]["value"]) if placement else None,"note":"Boundary rows were applied in Python using current source-linked registry rules; the profile seed does not claim to generate the exact boundaries."}
    return summary

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Patch exact synthetic data edge cases using validated source-linked rules")
    parser.add_argument("--dir",default=str(ROOT/"data"/"test_students"));parser.add_argument("--as-of-date",default=date.today().isoformat());args=parser.parse_args()
    try:
        summary=patch(Path(args.dir),args.as_of_date);out=ROOT/"reports"/"edge_case_patch.json";out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(summary,indent=2),encoding="utf-8");print(json.dumps(summary,indent=2))
    except Exception as exc: print(f"EDGE CASE PATCH FAILED: {type(exc).__name__}: {exc}",file=sys.stderr);sys.exit(1)
