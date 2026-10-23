from __future__ import annotations
import json,sys
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.db import init_db,seed_source_metadata_and_rules,active_rules,source_register_rows
from scripts.load_students import validate_bundle

DATA=ROOT/"data"/"test_students"
def pick_rule(parameter:str,prefer_synthetic:bool=False):
    rows=active_rules(date.today().isoformat(),parameter,"B.Tech CSE",None)
    sources={s["doc_id"]:s for s in source_register_rows()}
    chosen=[r for r in rows if sources.get(r["source_doc_id"],{}).get("synthetic")==("Y" if prefer_synthetic else "N")]
    if not chosen:chosen=rows
    if len(chosen)!=1:
        unique={(r["rule_id"],r["operator"],r["value"],r["source_doc_id"]) for r in chosen}
        if len(unique)!=1:raise ValueError(f"Missing/ambiguous rule for {parameter}: {chosen}")
    return chosen[0]
def _read_rows(data,table):return data[table]
def validate(directory: Path = DATA):
    init_db();seed_source_metadata_and_rules()
    bundle,errors=validate_bundle(directory)
    students={x["student_id"]:x for x in bundle["students"]}
    atts={(x["student_id"],x["course_code"]):x for x in bundle["attendance"]}
    results={(x["student_id"],x["course_code"]):x for x in bundle["results"]}
    attendance_rule=pick_rule("min_attendance_pct")
    threshold=float(attendance_rule["value"])
    held1=int(atts[("S1001","CS201")]["classes_held"]);att1=int(atts[("S1001","CS201")]["classes_attended"])
    held2=int(atts[("S1002","CS201")]["classes_held"]);att2=int(atts[("S1002","CS201")]["classes_attended"])
    if abs(100*att1/held1-threshold)>1e-9:errors.append(f"edge case: S1001 attendance should equal source-linked registry threshold {threshold}%")
    if held2 != held1 or att2 != att1-1:errors.append("edge case: S1002 should be exactly one class below S1001 with same classes held")
    pass_rule=pick_rule("pass_pct");pass_pct=float(pass_rule["value"])
    s1003=results.get(("S1003","CS201"))
    expected_fail= (int(pass_pct) if pass_pct.is_integer() else int(pass_pct)+1)-1 if pass_rule["operator"]==">=" else int(pass_pct)
    if not s1003 or int(s1003["total_marks"])!=max(0,expected_fail) or s1003["result"]!="FAIL":errors.append("edge case: S1003 must fail one integer mark below the synthetic registered pass threshold")
    if not results.get(("S1004","CS201"),{}).get("result")=="ABSENT":errors.append("edge case: S1004 CS201 must be ABSENT")
    if not results.get(("S1005","CS201"),{}).get("result")=="DETAINED":errors.append("edge case: S1005 CS201 must be DETAINED")
    if int(students.get("S1006",{}).get("active_backlogs",0))<2:errors.append("edge case: S1006 must have multiple active backlogs")
    placement=active_rules(date.today().isoformat(),"placement_min_cgpa","B.Tech CSE",None)
    placement=[r for r in placement if r["rule_id"]=="PLACE-CGPA-01"]
    if placement:
        cutoff=float(placement[0]["value"])
        if abs(float(students.get("S1007",{}).get("cgpa",-1))-cutoff)>1e-9 or int(students.get("S1007",{}).get("active_backlogs",-1))!=0:errors.append("edge case: S1007 must be at the synthetic placement cutoff with zero backlogs")
    counts={"students":len(bundle["students"]),"courses":len(bundle["courses"]),"attendance_rows":len(bundle["attendance"]),"result_rows":len(bundle["results"]),"programmes":sorted({r["programme"] for r in bundle["students"]}),"batches":sorted({int(r["batch_year"]) for r in bundle["students"]}),"attendance_boundary_rule":attendance_rule["rule_id"],"attendance_threshold":threshold,"pass_rule":pass_rule["rule_id"],"pass_threshold":pass_pct,"placement_cutoff":float(placement[0]["value"]) if placement else None}
    return errors,counts
if __name__=="__main__":
    report=ROOT/"reports"/"data_validation.txt"
    try:
        import argparse
        parser=argparse.ArgumentParser(description="Validate the synthetic student CSV bundle and boundary cases")
        parser.add_argument("--dir",type=Path,default=DATA)
        args=parser.parse_args()
        errors,counts=validate(args.dir);body=("SYNTHETIC DATA VALIDATION: PASS\n" if not errors else "SYNTHETIC DATA VALIDATION: FAIL\n")+json.dumps(counts,indent=2)+"\n"+("Errors: none\n" if not errors else "Errors:\n"+"\n".join("- "+e for e in errors)+"\n")
        report.parent.mkdir(exist_ok=True);report.write_text(body,encoding="utf-8");print(body);sys.exit(0 if not errors else 1)
    except Exception as exc:
        body=f"SYNTHETIC DATA VALIDATION: ERROR\n{type(exc).__name__}: {exc}\n";report.parent.mkdir(exist_ok=True);report.write_text(body,encoding="utf-8");print(body,file=sys.stderr);sys.exit(2)
