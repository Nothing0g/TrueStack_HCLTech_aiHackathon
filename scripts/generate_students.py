from __future__ import annotations
import argparse, json, random, sys
from datetime import date, datetime, timezone
from pathlib import Path
import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.db import init_db, seed_source_metadata_and_rules, active_rules, source_register_rows

PROGRAMMES = ["B.Tech CSE", "B.Tech Mechanical Engineering"]
COURSES = [
    {"course_code":"CS201","course_name":"Data Structures","programme":"B.Tech CSE","semester":4,"credits":4},
    {"course_code":"CS202","course_name":"Database Systems","programme":"B.Tech CSE","semester":4,"credits":3},
    {"course_code":"CS203","course_name":"Operating Systems","programme":"B.Tech CSE","semester":5,"credits":4},
    {"course_code":"ME201","course_name":"Thermodynamics","programme":"B.Tech Mechanical Engineering","semester":3,"credits":4},
    {"course_code":"ME202","course_name":"Fluid Mechanics","programme":"B.Tech Mechanical Engineering","semester":4,"credits":4},
    {"course_code":"ME203","course_name":"Manufacturing Technology","programme":"B.Tech Mechanical Engineering","semester":5,"credits":3},
]
STUDENT_FIELDS=["student_id","full_name","programme","batch_year","current_semester","cgpa","active_backlogs"]
COURSE_FIELDS=["course_code","course_name","programme","semester","credits"]
ATT_FIELDS=["student_id","course_code","classes_held","classes_attended"]
RESULT_FIELDS=["student_id","course_code","exam_session","exam_type","internal_marks","external_marks","total_marks","max_marks","result"]

class StrictModel(BaseModel):
    model_config=ConfigDict(extra="forbid")
class Profile(StrictModel):
    student_id:str=Field(pattern=r"^S\d{4}$")
    full_name:str=Field(min_length=2,max_length=100)
    programme:str
    batch_year:int
    current_semester:int=Field(ge=1,le=10)
    cgpa:float=Field(ge=0,le=10)
    active_backlogs:int=Field(ge=0)
class Profiles(StrictModel):
    students:list[Profile]

def write_csv(path:Path, rows:list[dict], fields:list[str])->None:
    import csv
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=fields);w.writeheader();w.writerows(rows)

def get_rule(parameter:str, today:str, programme:str="B.Tech CSE") -> dict:
    rows=active_rules(today,parameter,programme,None)
    sources={s["doc_id"]:s for s in source_register_rows()}
    # Use an official source-backed rule when one exists; otherwise a synthetic
    # demo rule may support clearly labelled demo calculations.
    official=[r for r in rows if sources.get(r["source_doc_id"],{}).get("synthetic")=="N"]
    chosen=official if official else [r for r in rows if sources.get(r["source_doc_id"],{}).get("synthetic")=="Y"]
    if len(chosen)!=1:
        unique={(r["rule_id"],r["operator"],r["value"],r["source_doc_id"]) for r in chosen}
        if len(unique)!=1: raise ValueError(f"Missing or ambiguous active source-linked rule: {parameter}: {chosen}")
    return chosen[0]

def ollama_profiles(prompt:str)->tuple[Profiles,str]:
    response=requests.post(f"{OLLAMA_BASE_URL}/api/generate",json={"model":OLLAMA_MODEL,"prompt":prompt,"stream":False,"format":"json","options":{"temperature":0.25,"num_ctx":8192}},timeout=180)
    response.raise_for_status(); payload=response.json()
    raw=str(payload.get("response","")).strip()
    if not raw: raise ValueError("Ollama returned an empty response")
    return Profiles.model_validate(json.loads(raw)), str(payload.get("model") or OLLAMA_MODEL)

def load_seed_profiles(path:Path)->Profiles:
    raw=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw,list): raise ValueError("Bundled AI-generated profile seed must be a JSON list")
    return Profiles(students=[Profile.model_validate(x) for x in raw])

def normalise_profiles(profiles:Profiles)->list[Profile]:
    students=profiles.students
    expected=[f"S{i:04d}" for i in range(1001,1031)]
    by_id={s.student_id:s for s in students}
    if set(by_id)!=set(expected) or len(by_id)!=len(students): raise ValueError("LLM/profile seed must contain each expected unique ID S1001-S1030")
    normal=[]
    for sid in expected:
        p=by_id[sid]; n=int(sid[1:])
        if 9000<=n<=9999: raise ValueError("Reserved judge IDs may not be used in the team's own dataset")
        # Programme/batch assignments are schema controls, not policy answers. Two
        # balanced programmes and batches are guaranteed regardless of LLM drift.
        programme=PROGRAMMES[0] if n<=1015 else PROGRAMMES[1]
        batch_year=2023 if n%2 else 2024
        normal.append(Profile(student_id=sid,full_name=p.full_name.strip(),programme=programme,batch_year=batch_year,
                              current_semester=p.current_semester,cgpa=p.cgpa,active_backlogs=p.active_backlogs))
    return normal

def main()->int:
    parser=argparse.ArgumentParser(description="Generate fictional university dataset using an LLM profile step plus deterministic relational-data generation.")
    parser.add_argument("--dir",default=str(ROOT/"data"/"test_students"));parser.add_argument("--provider",choices=["auto","ollama","seed"],default="auto")
    parser.add_argument("--seed",type=int,default=23026);args=parser.parse_args()
    init_db();seed_source_metadata_and_rules(); today=date.today().isoformat()
    run_dir=ROOT/"reports";run_dir.mkdir(exist_ok=True)
    try:
        attendance_rule=get_rule("min_attendance_pct",today)
        pass_rule=get_rule("pass_pct",today)
        placement_rows=active_rules(today,"placement_min_cgpa","B.Tech CSE",None)
        placement_rule=placement_rows[0] if len(placement_rows)==1 else None
        prompt_path=ROOT/"data"/"prompts"/"student_data_generation_prompt.md"
        generation_prompt=prompt_path.read_text(encoding="utf-8")
        model_used="GPT-6 (AI-authored bundled fictional profile seed; exact deployment identifier unavailable)"
        provider_used="bundled_ai_profile_seed"
        profile_seed=ROOT/"data"/"test_students"/"ai_profiles_seed.json"
        if args.provider != "seed":
            try:
                profiles, model_used=ollama_profiles(generation_prompt);provider_used="Ollama LLM"
            except Exception as exc:
                if args.provider=="ollama": raise RuntimeError(f"Ollama generation failed: {type(exc).__name__}: {exc}") from exc
                profiles=load_seed_profiles(profile_seed)
                provider_used="bundled_ai_profile_seed_fallback"
                (run_dir/"data_generation_fallback.txt").write_text(f"Ollama generation was not available: {type(exc).__name__}: {exc}\nUsed the bundled AI-authored fictional profile seed instead. Relational records and edge cases were generated/adjusted in Python.\n",encoding="utf-8")
        else: profiles=load_seed_profiles(profile_seed)
        students=normalise_profiles(profiles)
        rng=random.Random(args.seed)
        courses=COURSES
        courses_by_programme={p:[c for c in courses if c["programme"]==p] for p in PROGRAMMES}
        student_rows=[];attendance_rows=[];result_rows=[]
        pass_pct=float(pass_rule["value"]); pass_op=pass_rule["operator"]
        def is_pass(total:int,max_marks:int)->bool:
            pct=100*total/max_marks
            return pct>=pass_pct if pass_op==">=" else pct>pass_pct if pass_op==">" else pct<=pass_pct if pass_op=="<=" else pct<pass_pct if pass_op=="<" else pct==pass_pct if pass_op=="==" else False
        for profile in students:
            n=int(profile.student_id[1:]); p=courses_by_programme[profile.programme]
            for c in p:
                held=40
                attended=rng.randint(25,40)
                attendance_rows.append({"student_id":profile.student_id,"course_code":c["course_code"],"classes_held":held,"classes_attended":attended})
                total=rng.randint(20,100)
                internal=min(30,round(total*0.4));external=total-internal
                if total>100: total=100;external=total-internal
                result="PASS" if is_pass(total,100) else "FAIL"
                result_rows.append({"student_id":profile.student_id,"course_code":c["course_code"],"exam_session":"2026-MAY","exam_type":"REGULAR","internal_marks":internal,"external_marks":external,"total_marks":total,"max_marks":100,"result":result})
            student_rows.append({"student_id":profile.student_id,"full_name":profile.full_name,"programme":profile.programme,"batch_year":profile.batch_year,"current_semester":profile.current_semester,"cgpa":profile.cgpa,"active_backlogs":0})
        # Backlog count is derived from the results rather than trusting the profile seed.
        counts={s["student_id"]:sum(r["student_id"]==s["student_id"] and r["result"]!="PASS" for r in result_rows) for s in student_rows}
        for s in student_rows:s["active_backlogs"]=counts[s["student_id"]]
        out=Path(args.dir);out.mkdir(parents=True,exist_ok=True)
        write_csv(out/"students.csv",student_rows,STUDENT_FIELDS);write_csv(out/"courses.csv",courses,COURSE_FIELDS)
        write_csv(out/"attendance.csv",attendance_rows,ATT_FIELDS);write_csv(out/"results.csv",result_rows,RESULT_FIELDS)
        (run_dir/"generation_prompt_used.md").write_text(generation_prompt,encoding="utf-8")
        log={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"provider":provider_used,"model":model_used,"configured_ollama_model":OLLAMA_MODEL,"student_profiles_model_generated":provider_used=="Ollama LLM","bundled_seed_is_ai_authored":provider_used!="Ollama LLM","seed":args.seed,"students":len(student_rows),"courses":len(courses),"attendance_rows":len(attendance_rows),"result_rows":len(result_rows),"attendance_rule":{"rule_id":attendance_rule["rule_id"],"operator":attendance_rule["operator"],"value":attendance_rule["value"],"source_doc_id":attendance_rule["source_doc_id"],"source_section":attendance_rule["source_section"]},"pass_rule":{"rule_id":pass_rule["rule_id"],"operator":pass_op,"value":pass_pct,"source_doc_id":pass_rule["source_doc_id"],"source_section":pass_rule["source_section"]},"placement_rule":{"rule_id":placement_rule["rule_id"],"value":placement_rule["value"],"source_doc_id":placement_rule["source_doc_id"],"source_section":placement_rule["source_section"]} if placement_rule else None,"notes":"The LLM generates fictional profile fields when Ollama is available; otherwise the bundled AI-authored profile seed is used. Python generates relational attendance/result rows and patches exact boundary cases from validated source-linked rules. No real student data is used."}
        (run_dir/"data_generation_run.json").write_text(json.dumps(log,indent=2,ensure_ascii=False),encoding="utf-8")
        if args.provider=="ollama": print(f"LLM generated {len(student_rows)} profiles using {model_used}.")
        else: print(f"Prepared {len(student_rows)} synthetic profiles using {provider_used}; relational records are created in Python.")
        import subprocess
        subprocess.run([sys.executable,str(ROOT/"scripts"/"patch_edge_cases.py"),"--dir",str(out),"--as-of-date",today],check=True)
        subprocess.run([sys.executable,str(ROOT/"scripts"/"validate_students.py"),"--dir",str(out)],check=True)
        print("Dataset generation and validation completed. Load it with: python scripts/load_students.py --dir",out)
        return 0
    except Exception as exc:
        print(f"GENERATION FAILED: {type(exc).__name__}: {exc}",file=sys.stderr);return 1
if __name__=="__main__": raise SystemExit(main())
