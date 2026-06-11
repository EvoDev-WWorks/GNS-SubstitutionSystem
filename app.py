"""
Teacher Substitution System — Gyan Niketan School
=========================================================
Single file: UI + Backend + OR-Tools + Report + Admin Panel

HOW TO RUN:
  Double-click  START.bat
  Then open:    http://localhost:8000
"""

import httpx
from datetime import date
from collections import defaultdict
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from ortools.sat.python import cp_model
import uvicorn, socket

# ─────────────────────────────────────────────────────────────
# SUPABASE — connects via HTTPS (REST API), no DNS issues
# ─────────────────────────────────────────────────────────────

import os

for _p in [r"D:\EvoDoc\GNS-SubstitutionSystem\.env", r"D:\SubstitutionSystem\.env",
           os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
           os.path.join(os.getcwd(), ".env")]:
    if os.path.exists(_p):
        with open(_p) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
        break

SUPABASE_PROJECT_URL = os.environ["SUPABASE_PROJECT_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

_HEADERS = {
    "apikey":        SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type":  "application/json",
}

def _get(table: str, params: dict | None = None) -> list:
    p = {"limit": "20000", **(params or {})}
    r = httpx.get(f"{SUPABASE_PROJECT_URL}/rest/v1/{table}",
                  headers=_HEADERS, params=p, verify=False, timeout=30)
    r.raise_for_status()
    return r.json()

def _post(table: str, data: dict | list, upsert_on: str | None = None) -> list:
    headers = {**_HEADERS, "Prefer": "return=representation"}
    if upsert_on:
        headers["Prefer"] = "resolution=ignore-duplicates,return=representation"
    r = httpx.post(f"{SUPABASE_PROJECT_URL}/rest/v1/{table}",
                   headers=headers, json=data, verify=False, timeout=30)
    if r.status_code == 409:
        raise ValueError("This teacher is already assigned to another class during this period. Please choose a different teacher.")
    if r.status_code not in (200, 201, 204):
        r.raise_for_status()
    return r.json() if r.content else []

def _patch(table: str, filters: dict, data: dict) -> list:
    headers = {**_HEADERS, "Prefer": "return=representation"}
    r = httpx.patch(f"{SUPABASE_PROJECT_URL}/rest/v1/{table}",
                    headers=headers, params=filters, json=data, verify=False, timeout=30)
    if r.status_code == 409:
        raise ValueError("This teacher is already assigned to another class during this period. Please choose a different teacher.")
    r.raise_for_status()
    return r.json()

def _delete(table: str, filters: dict) -> bool:
    r = httpx.delete(f"{SUPABASE_PROJECT_URL}/rest/v1/{table}",
                     headers=_HEADERS, params=filters, verify=False, timeout=30)
    r.raise_for_status()
    return True

def _rpc(func: str, params: dict | None = None) -> list:
    r = httpx.post(f"{SUPABASE_PROJECT_URL}/rest/v1/rpc/{func}",
                   headers=_HEADERS, json=params or {}, verify=False, timeout=30)
    r.raise_for_status()
    return r.json()


app = FastAPI(title="Teacher Substitution System")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

PERIOD_ORDER = ["alpha1","alpha2","P1","P2","P3","P4","P5","P6","P7","P8"]
PERIOD_LABEL = {
    "alpha1":"α1","alpha2":"α2",
    "P1":"1st","P2":"2nd","P3":"3rd","P4":"4th",
    "P5":"5th","P6":"6th","P7":"7th","P8":"8th",
}
BAND_ORDER = {"NURSERY":0,"LOWER":1,"MIDDLE":2,"HIGHER":3}

# ─────────────────────────────────────────────────────────────
# OR-TOOLS ENGINE
# ─────────────────────────────────────────────────────────────

def run_substitution(absent_teacher_ids: list, absence_date: date):
    day = absence_date.strftime("%A")

    rows = _get("period_config", {"select":"grade_band,period_name,is_active"})
    active_periods = defaultdict(set)
    for r in rows:
        if r["is_active"]:
            active_periods[r["grade_band"]].add(r["period_name"])

    rows = _get("teachers", {"select":"id,full_name,designation,subject,is_excluded"})
    all_teachers = {r["id"]: r for r in rows}

    rows = _get("subjects", {"select":"id,code"})
    subj_code_map = {r["id"]: r["code"] for r in rows}

    rows = _get("teacher_subjects", {"select":"teacher_id,subject_id"})
    teacher_subjects = defaultdict(set)
    for r in rows:
        teacher_subjects[r["teacher_id"]].add(r["subject_id"])

    rows = _rpc("get_teacher_grades")
    teacher_grades = defaultdict(set)
    teacher_bands  = defaultdict(set)
    for r in rows:
        teacher_bands[r["teacher_id"]].add(r["grade_band"])
        if r["grade"]:
            teacher_grades[r["teacher_id"]].add(r["grade"])

    rows = _rpc("get_weekly_load")
    weekly_load = {r["teacher_id"]: r["cnt"] for r in rows}

    rows = _get("timetable", {
        "select":     "teacher_id,period_name",
        "day":        f"eq.{day}",
        "teacher_id": "not.is.null",
    })
    busy = defaultdict(set)
    for r in rows:
        busy[r["teacher_id"]].add(r["period_name"])
    daily_count = {tid: len(periods) for tid, periods in busy.items()}

    vacancies   = []
    no_schedule = []

    for tid in absent_teacher_ids:
        tname = all_teachers.get(tid, {}).get("full_name", "")
        rows = _get("timetable", {
            "select":     "class_id,period_name,subject_id,room_type,"
                          "classes(name,grade_band,grade),subjects(code)",
            "teacher_id": f"eq.{tid}",
            "day":        f"eq.{day}",
        })
        if not rows:
            no_schedule.append(tname)
        for r in rows:
            cls    = r.get("classes") or {}
            sbj    = r.get("subjects") or {}
            gband  = cls.get("grade_band", "")
            period = r["period_name"]
            if active_periods and period not in active_periods.get(gband, {period}):
                continue
            vacancies.append({
                "class_id":            r["class_id"],
                "period_name":         period,
                "subject_id":          r["subject_id"],
                "room_type":           r["room_type"],
                "class_name":          cls.get("name", ""),
                "grade_band":          gband,
                "grade":               cls.get("grade"),
                "subject_code":        sbj.get("code"),
                "absent_teacher_id":   tid,
                "absent_teacher_name": tname,
            })

    if not vacancies:
        return {"day":day,"date":absence_date.strftime("%d %B %Y"),
                "report":[],"no_schedule":no_schedule}

    def score(cand_id, v):
        s = 0
        vband  = v.get("grade_band","")
        vgrade = v.get("grade") or 0
        if v["subject_id"] and v["subject_id"] in teacher_subjects.get(cand_id,set()):
            s += 35
        if vband == "HIGHER" and "HIGHER" in teacher_bands.get(cand_id,set()):
            s += 40
            
        # Cross-stream penalty for 11/12
        if vgrade >= 11:
            cand_dept = all_teachers[cand_id].get("subject", "") or ""
            v_subj = v.get("subject_code", "") or ""
            
            def get_stream(subj):
                s_str = subj.upper()
                if any(x in s_str for x in ["SCIENCE", "MATH", "COMPUTER", "ROBOTICS"]): return "SCIENCE"
                if "COMMERCE" in s_str: return "COMMERCE"
                if any(x in s_str for x in ["ART", "POL", "SOCIAL", "HIST", "GEO"]): return "ARTS"
                return "GENERAL"
                
            c_stream = get_stream(cand_dept)
            v_stream = get_stream(v_subj)
            if c_stream != "GENERAL" and v_stream != "GENERAL" and c_stream != v_stream:
                s -= 100

        if vband and vband in teacher_bands.get(cand_id,set()):
            s += 25
        if vgrade and teacher_grades.get(cand_id):
            cand_grades = teacher_grades[cand_id]
            min_diff = min(abs(vgrade-g) for g in cand_grades)
            
            # Strict rule for 11th/12th: Do not assign anyone who teaches only below 9th
            if vgrade >= 11 and max(cand_grades) < 9:
                return -9999
                
            # STRICT RULE: Identify 'junior teachers' who might have one or two senior classes 
            # by checking if the majority of the grades they teach are below 8th.
            junior_count = sum(1 for g in cand_grades if g < 8)
            senior_count = sum(1 for g in cand_grades if g >= 8)
            
            if vgrade >= 8 and junior_count > senior_count:
                return -9999
            else:
                s += 20 if min_diff<=2 else (5 if min_diff<=4 else -15)
        cand_bands = teacher_bands.get(cand_id,set())
        if cand_bands:
            cand_max = max(BAND_ORDER.get(b,0) for b in cand_bands)
            if cand_max > BAND_ORDER.get(vband,0):
                s -= 5
        cand_subjs = teacher_subjects.get(cand_id,set())
        is_pt = any("PT" in (subj_code_map.get(sid,"") or "").upper() for sid in cand_subjs)
        if is_pt and vgrade in (10,11,12):
            s -= 30
        s -= daily_count.get(cand_id,0)*8
        if weekly_load.get(cand_id,0) > 35:
            s -= 10
        return s

    cands_per = []
    for v in vacancies:
        period   = v["period_name"]
        eligible = []
        for cid, meta in all_teachers.items():
            if meta["is_excluded"]:            continue
            if cid in absent_teacher_ids:      continue
            if period in busy.get(cid,set()):  continue
            if daily_count.get(cid,0) >= 7:    continue
            s = score(cid, v)
            if s == -9999:                     continue
            eligible.append({"id":cid,"name":meta["full_name"],"score":s})
        eligible.sort(key=lambda x: x["score"], reverse=True)
        cands_per.append(eligible)

    model   = cp_model.CpModel()
    n       = len(vacancies)
    all_ids = sorted({c["id"] for cands in cands_per for c in cands})

    if not all_ids:
        return {"day":day,"date":absence_date.strftime("%d %B %Y"),
                "report":[{"period":v["period_name"],
                            "period_label":PERIOD_LABEL.get(v["period_name"],v["period_name"]),
                            "class_name":v["class_name"],"grade_band":v.get("grade_band",""),
                            "subject":v.get("subject_code") or "—","absent_teacher":v["absent_teacher_name"],
                            "substitute":"No substitute available","reason":"No eligible teacher found",
                            "alternatives":[],"score":0} for v in vacancies],
                "no_schedule":no_schedule}

    x = {}
    for i in range(n):
        eid_set = {c["id"] for c in cands_per[i]}
        for j in all_ids:
            x[(i,j)] = model.NewBoolVar(f"x_{i}_{j}")
            if j not in eid_set:
                model.Add(x[(i,j)] == 0)

    for i in range(n):
        if cands_per[i]: model.Add(sum(x[(i,j)] for j in all_ids) == 1)
        else:            model.Add(sum(x[(i,j)] for j in all_ids) == 0)

    for j in all_ids:
        existing = daily_count.get(j,0)
        model.Add(sum(x[(i,j)] for i in range(n)) <= max(0,7-existing))
        model.Add(sum(x[(i,j)] for i in range(n)) <= 2)

    score_map = {}
    for i,cands in enumerate(cands_per):
        for c in cands:
            score_map[(i,c["id"])] = max(1, c["score"]+100)

    used = {}
    for j in all_ids:
        used[j] = model.NewIntVar(0,n,f"used_{j}")
        model.Add(used[j] == sum(x[(i,j)] for i in range(n)))

    model.Maximize(
        sum(score_map.get((i,j),0)*x[(i,j)] for i in range(n) for j in all_ids)
        - sum(25*used[j] for j in all_ids)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    status = solver.Solve(model)

    report = []
    for i,v in enumerate(vacancies):
        assigned_id   = None
        assigned_name = "No substitute available"
        assigned_score = 0
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for j in all_ids:
                if solver.Value(x[(i,j)]) == 1:
                    assigned_id    = j
                    assigned_name  = all_teachers[j]["full_name"]
                    assigned_score = next((c["score"] for c in cands_per[i] if c["id"]==j),0)
                    break

        reasons = []
        if assigned_id:
            vband  = v.get("grade_band","")
            vgrade = v.get("grade") or 0
            if v["subject_id"] and v["subject_id"] in teacher_subjects.get(assigned_id,set()):
                reasons.append("Same subject")
            if vband == "HIGHER" and "HIGHER" in teacher_bands.get(assigned_id,set()):
                reasons.append("Same stream (11/12)")
            elif vband and vband in teacher_bands.get(assigned_id,set()):
                reasons.append("Same level")
            else:
                cb = teacher_bands.get(assigned_id,set())
                if cb and max(BAND_ORDER.get(b,0) for b in cb) > BAND_ORDER.get(vband,0):
                    reasons.append("Senior teacher to junior class")
            if v.get("room_type") == "SMART_CLASS":
                reasons.append("Smart lab treated as classroom")
            a_subjs = teacher_subjects.get(assigned_id,set())
            if any("PT" in (subj_code_map.get(sid,"") or "").upper() for sid in a_subjs) and vgrade in (10,11,12):
                reasons.append("PT teacher (last resort)")

        report.append({
            "period":        v["period_name"],
            "period_label":  PERIOD_LABEL.get(v["period_name"],v["period_name"]),
            "class_name":    v["class_name"],
            "grade_band":    v.get("grade_band",""),
            "subject":       v.get("subject_code") or "—",
            "absent_teacher":v["absent_teacher_name"],
            "substitute":    assigned_name,
            "reason":        " · ".join(reasons) if reasons else "Best available",
            "alternatives":  [c["name"] for c in cands_per[i] if c["id"]!=assigned_id][:3],
            "score":         assigned_score,
        })

    report.sort(key=lambda r:(
        PERIOD_ORDER.index(r["period"]) if r["period"] in PERIOD_ORDER else 99,
        r["class_name"]
    ))

    for tid in absent_teacher_ids:
        try:
            _post("absences",{"teacher_id":tid,"absence_date":absence_date.isoformat(),"day_of_week":day},
                  upsert_on="teacher_id,absence_date")
        except Exception:
            pass

    return {"day":day,"date":absence_date.strftime("%d %B %Y"),
            "weekday":day,"report":report,"no_schedule":no_schedule}

# ─────────────────────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────────────────────

class ReportRequest(BaseModel):
    absent_teacher_ids: List[int]
    absence_date: str

class TeacherCreate(BaseModel):
    teacher_no: str
    full_name: str
    subject: Optional[str] = None
    designation: str = "TEACHER"
    abbreviation: Optional[str] = None
    is_excluded: bool = False

class TeacherUpdate(BaseModel):
    full_name: Optional[str] = None
    subject: Optional[str] = None
    designation: Optional[str] = None
    abbreviation: Optional[str] = None
    is_excluded: Optional[bool] = None

class SubjectCreate(BaseModel):
    code: str

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    grade: Optional[int] = None
    section: Optional[str] = None
    grade_band: Optional[str] = None

class TimetableUpdate(BaseModel):
    teacher_id: Optional[int] = None
    subject_id: Optional[int] = None
    day: Optional[str] = None
    period_name: Optional[str] = None
    room_type: Optional[str] = None
    is_practical: Optional[bool] = None

class TimetableCreate(BaseModel):
    class_id: int
    teacher_id: Optional[int] = None
    subject_id: Optional[int] = None
    day: str
    period_name: str
    room_type: str = "CLASSROOM"
    is_practical: bool = False
    lab_section: Optional[str] = None

class PeriodConfigUpdate(BaseModel):
    is_active: bool

# ─────────────────────────────────────────────────────────────
# REPORT ROUTES
# ─────────────────────────────────────────────────────────────

@app.get("/api/teachers")
def get_teachers():
    return _get("teachers", {
        "select":      "id,full_name,designation",
        "order":       "full_name.asc",
    })

@app.post("/api/generate-report")
def generate_report(req: ReportRequest):
    try:
        d = date.fromisoformat(req.absence_date)
        return JSONResponse(content=run_substitution(req.absent_teacher_ids, d))
    except Exception as e:
        import traceback
        return JSONResponse(content={"error":str(e),"detail":traceback.format_exc()}, status_code=500)

@app.get("/api/health")
def health():
    try:
        rows = _get("teachers", {"select":"id","limit":"1"})
        return {"status":"ok","db":"connected"}
    except Exception as e:
        return {"status":"error","db":str(e)}

# ─────────────────────────────────────────────────────────────
# ADMIN — TEACHERS
# ─────────────────────────────────────────────────────────────

@app.get("/api/admin/teachers")
def admin_get_teachers():
    return _get("teachers", {"select":"*","order":"teacher_no.asc"})

@app.post("/api/admin/teachers")
def admin_create_teacher(t: TeacherCreate):
    try:
        result = _post("teachers", t.dict())
        return result[0] if result else {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.put("/api/admin/teachers/{tid}")
def admin_update_teacher(tid: int, t: TeacherUpdate):
    try:
        data = {k: v for k, v in t.dict().items() if v is not None}
        result = _patch("teachers", {"id": f"eq.{tid}"}, data)
        return result[0] if result else {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.delete("/api/admin/teachers/{tid}")
def admin_delete_teacher(tid: int):
    try:
        _delete("teachers", {"id": f"eq.{tid}"})
        return {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# ─────────────────────────────────────────────────────────────
# ADMIN — CLASSES
# ─────────────────────────────────────────────────────────────

@app.get("/api/admin/classes")
def admin_get_classes():
    return _get("classes", {"select":"*","order":"grade.asc,name.asc"})

@app.put("/api/admin/classes/{cid}")
def admin_update_class(cid: int, c: ClassUpdate):
    try:
        data = {k: v for k, v in c.dict().items() if v is not None}
        result = _patch("classes", {"id": f"eq.{cid}"}, data)
        return result[0] if result else {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# ─────────────────────────────────────────────────────────────
# ADMIN — CLASS TEACHERS
# ─────────────────────────────────────────────────────────────

@app.get("/api/admin/class-teachers")
def admin_get_class_teachers():
    return _get("class_teachers", {
        "select": "class_id,teacher_id,classes(id,name,grade,section),teachers(id,full_name)",
        "order":  "classes(grade).asc,classes(name).asc"
    })

class ClassTeacherUpdate(BaseModel):
    teacher_id: int

@app.put("/api/admin/class-teachers/{class_id}")
def admin_update_class_teacher(class_id: int, body: ClassTeacherUpdate):
    try:
        teacher_id = body.teacher_id
        # Check if entry exists
        existing = _get("class_teachers", {"class_id": f"eq.{class_id}", "select": "class_id"})
        if existing:
            result = _patch("class_teachers", {"class_id": f"eq.{class_id}"}, {"teacher_id": teacher_id})
        else:
            result = _post("class_teachers", {"class_id": class_id, "teacher_id": teacher_id})
        return result[0] if result else {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.delete("/api/admin/class-teachers/{class_id}")
def admin_delete_class_teacher(class_id: int):
    try:
        _delete("class_teachers", {"class_id": f"eq.{class_id}"})
        return {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# ─────────────────────────────────────────────────────────────
# ADMIN — SUBJECTS
# ─────────────────────────────────────────────────────────────

@app.get("/api/admin/subjects")
def admin_get_subjects():
    return _get("subjects", {"select":"*","order":"code.asc"})

@app.post("/api/admin/subjects")
def admin_create_subject(s: SubjectCreate):
    try:
        result = _post("subjects", {"code": s.code})
        return result[0] if result else {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.delete("/api/admin/subjects/{sid}")
def admin_delete_subject(sid: int):
    try:
        _delete("subjects", {"id": f"eq.{sid}"})
        return {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# ─────────────────────────────────────────────────────────────
# ADMIN — TIMETABLE
# ─────────────────────────────────────────────────────────────

@app.get("/api/admin/timetable")
def admin_get_timetable(teacher_id: Optional[int] = None, class_id: Optional[int] = None):
    params = {
        "select": "id,day,period_name,room_type,is_practical,lab_section,"
                  "teachers(id,full_name),classes(id,name),subjects(id,code)",
        "order":  "day.asc,period_name.asc",
    }
    if teacher_id:
        params["teacher_id"] = f"eq.{teacher_id}"
    if class_id:
        # Also include related class IDs: LAB, PRACT, LIB, combined (e.g. "3D LAB", "3D+4F")
        all_classes = _get("classes", {"select": "id,name", "limit": "500"})
        main_class  = next((c for c in all_classes if c["id"] == class_id), None)
        related_ids = [class_id]
        if main_class:
            prefix = main_class["name"]   # e.g. "3D"
            for c in all_classes:
                n = c["name"]
                # starts with same prefix and has a space after (e.g. "3D LAB", "3D PRACT", "3D LIB")
                # OR is a combined class that includes this class (e.g. "3D+4F", "4F+3D")
                if c["id"] != class_id and (
                    n.startswith(prefix + " ") or
                    n.startswith(prefix + "+") or
                    ("+" in n and n.split("+")[1].strip() == prefix)
                ):
                    related_ids.append(c["id"])
        if len(related_ids) == 1:
            params["class_id"] = f"eq.{class_id}"
        else:
            params["class_id"] = f"in.({','.join(str(i) for i in related_ids)})"
    return _get("timetable", params)

def _free_teacher_slot(teacher_id, day, period_name, room_type, exclude_id=None):
    """Manual entry mode: if the teacher already holds this slot in another
    class, null out that entry so the new assignment can be saved. Returns
    the names of the classes that were cleared."""
    if not teacher_id:
        return []
    params = {"teacher_id": f"eq.{teacher_id}", "day": f"eq.{day}",
              "period_name": f"eq.{period_name}", "room_type": f"eq.{room_type}"}
    if exclude_id is not None:
        params["id"] = f"neq.{exclude_id}"
    cleared = _patch("timetable", params, {"teacher_id": None})
    names = []
    for row in cleared:
        cls = _get("classes", {"id": f"eq.{row['class_id']}", "select": "name"})
        names.append(cls[0]["name"] if cls else str(row["class_id"]))
    return names

@app.post("/api/admin/timetable")
def admin_create_timetable(t: TimetableCreate):
    try:
        cleared = _free_teacher_slot(t.teacher_id, t.day, t.period_name, t.room_type)
        result = _post("timetable", t.dict())
        out = result[0] if result else {"ok": True}
        out["cleared_from"] = cleared
        return out
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.put("/api/admin/timetable/{tid}")
def admin_update_timetable(tid: int, t: TimetableUpdate):
    try:
        data = {k: v for k, v in t.dict().items() if v is not None}
        cleared = []
        if data.get("teacher_id"):
            current = _get("timetable", {"id": f"eq.{tid}", "select": "day,period_name,room_type"})
            if current:
                row = current[0]
                cleared = _free_teacher_slot(
                    data["teacher_id"],
                    data.get("day", row["day"]),
                    data.get("period_name", row["period_name"]),
                    data.get("room_type", row["room_type"]),
                    exclude_id=tid)
        result = _patch("timetable", {"id": f"eq.{tid}"}, data)
        out = result[0] if result else {"ok": True}
        out["cleared_from"] = cleared
        return out
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.delete("/api/admin/timetable/{tid}")
def admin_delete_timetable(tid: int):
    try:
        _delete("timetable", {"id": f"eq.{tid}"})
        return {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# ─────────────────────────────────────────────────────────────
# ADMIN — PERIOD CONFIG
# ─────────────────────────────────────────────────────────────

@app.get("/api/admin/period-config")
def admin_get_period_config():
    return _get("period_config", {"select":"*","order":"grade_band.asc,period_order.asc"})

@app.put("/api/admin/period-config/{pid}")
def admin_update_period_config(pid: int, p: PeriodConfigUpdate):
    try:
        result = _patch("period_config", {"id": f"eq.{pid}"}, {"is_active": p.is_active})
        return result[0] if result else {"ok": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# ─────────────────────────────────────────────────────────────
# HTML UI
# ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Teacher Substitution System — Gyan Niketan School</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{
  --brand:       #1e3a5f;
  --brand-mid:   #2563eb;
  --brand-light: #eff6ff;
  --accent:      #f59e0b;
  --green:       #059669;
  --green-lt:    #d1fae5;
  --red:         #dc2626;
  --red-lt:      #fee2e2;
  --surface:     #ffffff;
  --bg:          #f1f5f9;
  --border:      #e2e8f0;
  --text:        #0f172a;
  --text-2:      #475569;
  --text-3:      #94a3b8;
  --radius:      12px;
  --shadow-sm:   0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.04);
  --shadow-md:   0 4px 16px rgba(0,0,0,.10),0 1px 4px rgba(0,0,0,.06);
  --shadow-lg:   0 20px 60px rgba(0,0,0,.18);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter','Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);
     min-height:100vh;line-height:1.5}

/* ══════════════════════════════════════
   HEADER
══════════════════════════════════════ */
.hdr{
  background:linear-gradient(135deg,#0f2d5e 0%,#1e3a5f 50%,#1a4480 100%);
  color:#fff;
  padding:0 32px;
  display:flex;align-items:center;gap:18px;
  box-shadow:0 2px 16px rgba(0,0,0,.3);
  flex-wrap:wrap;
  min-height:64px;
  position:sticky;top:0;z-index:100;
}
.hdr::after{
  content:'';position:absolute;bottom:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--accent),#f97316,#ef4444);
}
.hdr-logo{
  width:38px;height:38px;background:rgba(255,255,255,.15);border-radius:10px;
  display:flex;align-items:center;justify-content:center;font-size:20px;
  flex-shrink:0;border:1px solid rgba(255,255,255,.2);
}
.hdr-text h1{font-size:16px;font-weight:700;letter-spacing:-.2px}
.hdr-text p{font-size:11px;color:#93c5fd;margin-top:1px;font-weight:500}
.hdr-nav{margin-left:auto;display:flex;gap:4px;padding:12px 0}
.nav-btn{
  background:transparent;color:rgba(255,255,255,.75);
  border:none;
  padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;
  font-family:inherit;transition:all .18s;letter-spacing:.1px;
}
.nav-btn:hover{background:rgba(255,255,255,.12);color:#fff}
.nav-btn.active{background:rgba(255,255,255,.18);color:#fff;
  box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.3)}

/* ══════════════════════════════════════
   LAYOUT
══════════════════════════════════════ */
.wrap{max-width:1120px;margin:28px auto;padding:0 24px}
.card{
  background:var(--surface);border-radius:var(--radius);
  box-shadow:var(--shadow-sm);
  border:1px solid var(--border);
  padding:26px;margin-bottom:20px;
  transition:box-shadow .2s;
}
.card:hover{box-shadow:var(--shadow-md)}
.card-title{
  font-size:14px;font-weight:700;color:var(--brand);
  padding-bottom:14px;
  border-bottom:1.5px solid var(--border);
  margin-bottom:22px;
  display:flex;align-items:center;justify-content:space-between;gap:8px;
}
.card-title-left{display:flex;align-items:center;gap:8px}

/* ══════════════════════════════════════
   FORM
══════════════════════════════════════ */
.form-row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end}
.fg{display:flex;flex-direction:column;gap:5px;flex:1;min-width:180px}
label{font-size:11.5px;font-weight:600;color:var(--text-2);text-transform:uppercase;letter-spacing:.4px}
input[type=date],input[type=text],select,input[type=number]{
  padding:9px 12px;border:1.5px solid var(--border);border-radius:8px;
  font-size:13px;font-family:inherit;outline:none;transition:all .18s;width:100%;
  background:var(--surface);color:var(--text);
}
input[type=date]:hover,input[type=text]:hover,select:hover,input[type=number]:hover{border-color:#94a3b8}
input:focus,select:focus{border-color:var(--brand-mid);box-shadow:0 0 0 3px rgba(37,99,235,.12)}

/* ══════════════════════════════════════
   BUTTONS
══════════════════════════════════════ */
.btn{
  padding:9px 22px;
  background:linear-gradient(135deg,#1e3a5f,#2563eb);
  color:#fff;border:none;border-radius:8px;
  font-size:13px;font-weight:600;font-family:inherit;
  cursor:pointer;transition:all .18s;white-space:nowrap;
  box-shadow:0 2px 8px rgba(37,99,235,.25);
  letter-spacing:.1px;
}
.btn:hover{background:linear-gradient(135deg,#2563eb,#1d4ed8);box-shadow:0 4px 14px rgba(37,99,235,.35);transform:translateY(-1px)}
.btn:active{transform:translateY(0);box-shadow:0 2px 6px rgba(37,99,235,.2)}
.btn:disabled{background:#cbd5e1;box-shadow:none;cursor:not-allowed;transform:none}
.btn-green{background:linear-gradient(135deg,#059669,#10b981);box-shadow:0 2px 8px rgba(5,150,105,.25)}
.btn-green:hover{background:linear-gradient(135deg,#047857,#059669);box-shadow:0 4px 14px rgba(5,150,105,.35)}
.btn-red{background:linear-gradient(135deg,#dc2626,#ef4444);box-shadow:0 2px 8px rgba(220,38,38,.25)}
.btn-red:hover{background:linear-gradient(135deg,#b91c1c,#dc2626);box-shadow:0 4px 14px rgba(220,38,38,.35)}
.btn-gray{background:linear-gradient(135deg,#475569,#64748b);box-shadow:0 2px 8px rgba(71,85,105,.2)}
.btn-gray:hover{background:linear-gradient(135deg,#334155,#475569)}
.btn-sm{padding:6px 13px;font-size:12px;border-radius:6px}
.btn-print{padding:8px 18px;font-size:12px}

/* ══════════════════════════════════════
   SEARCH & TAGS
══════════════════════════════════════ */
.sw{position:relative}
#ts{width:100%;padding:9px 12px;border:1.5px solid var(--border);border-radius:8px;
    font-size:13px;font-family:inherit;outline:none;transition:all .18s}
#ts:focus{border-color:var(--brand-mid);box-shadow:0 0 0 3px rgba(37,99,235,.12)}
#dd{position:absolute;top:calc(100% + 4px);left:0;right:0;background:#fff;
    border:1.5px solid var(--border);border-radius:10px;max-height:220px;overflow-y:auto;
    z-index:200;display:none;box-shadow:var(--shadow-md)}
.ddi{padding:9px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid #f8fafc;transition:.12s}
.ddi:first-child{border-radius:8px 8px 0 0}
.ddi:last-child{border-bottom:none;border-radius:0 0 8px 8px}
.ddi:hover{background:var(--brand-light);color:var(--brand-mid)}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;min-height:32px}
.tag{
  background:linear-gradient(135deg,#dbeafe,#eff6ff);
  color:#1e40af;padding:5px 12px;border-radius:20px;
  font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px;
  border:1px solid #bfdbfe;
}
.tag .x{cursor:pointer;font-size:14px;color:#93c5fd;font-weight:700;line-height:1}
.tag .x:hover{color:#1e40af}

/* ══════════════════════════════════════
   SPINNER / MESSAGES
══════════════════════════════════════ */
.spin{display:none;text-align:center;padding:48px;color:var(--text-3);font-size:13px}
.spin:before{content:"";display:block;width:36px;height:36px;
             border:3px solid var(--border);border-top-color:var(--brand-mid);
             border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 14px}
@keyframes spin{to{transform:rotate(360deg)}}
.err{background:#fff5f5;border:1.5px solid #fca5a5;border-radius:10px;
     padding:12px 16px;color:var(--red);font-size:13px;display:none;margin-bottom:14px;
     display:none}
.success-msg{background:#f0fdf4;border:1.5px solid #86efac;border-radius:10px;
             padding:10px 16px;color:#166534;font-size:13px;display:none;margin-bottom:12px}

/* ══════════════════════════════════════
   TABLE
══════════════════════════════════════ */
.tbl-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{
  background:var(--brand);color:#fff;padding:10px 14px;text-align:left;
  font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  white-space:nowrap;
}
th:first-child{border-radius:10px 0 0 0}
th:last-child{border-radius:0 10px 0 0}
td{padding:10px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle;color:var(--text)}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8fafc}
tr:nth-child(even) td{background:#fafbfc}
tr:nth-child(even):hover td{background:#f1f5f9}
.tbl-wrap table{border-radius:10px;overflow:hidden}

/* ══════════════════════════════════════
   REPORT
══════════════════════════════════════ */
.grp td{
  background:linear-gradient(90deg,#fffbeb,#fef3c7)!important;
  color:#78350f;font-weight:700;font-size:12px;
  padding:8px 14px;border-bottom:1px solid #fde68a;
  letter-spacing:.3px;
}
.pbdg{
  background:var(--brand);color:#fff;padding:3px 9px;border-radius:5px;
  font-size:11px;font-weight:700;display:inline-block;
}
.cbdg{background:#e0f2fe;color:#0369a1;padding:3px 9px;border-radius:5px;font-size:11px;font-weight:700}
.gb{font-size:10px;color:var(--text-3);margin-top:1px}
.sub-ok{font-weight:700;color:var(--green)}
.sub-no{font-weight:700;color:var(--red)}
.rsn{color:var(--text-2);font-size:11px}
.alt{color:var(--text-3);font-size:11px;margin-top:2px}
.absent-lbl{color:var(--red);font-size:12px}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.bdg{padding:5px 13px;border-radius:20px;font-size:12px;font-weight:600;border:1px solid transparent}
.bdg-b{background:#dbeafe;color:#1e40af;border-color:#bfdbfe}
.bdg-g{background:#dcfce7;color:#166534;border-color:#bbf7d0}
.bdg-y{background:#fef3c7;color:#92400e;border-color:#fde68a}
.fnote{margin-top:18px;font-size:11px;color:var(--text-3);border-top:1px solid var(--border);padding-top:12px}
.badge-excl{background:#fee2e2;color:#991b1b;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:700}
.badge-ok{background:#dcfce7;color:#166534;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:700}

/* ══════════════════════════════════════
   TIMETABLE GRID
══════════════════════════════════════ */
.tt-grid{overflow-x:auto;margin-top:18px;border-radius:10px;border:1px solid var(--border)}
.tt-grid table{border-collapse:collapse;min-width:700px;width:100%}
.tt-grid th{
  background:var(--brand);color:#fff;padding:9px 11px;font-size:10.5px;
  font-weight:700;text-align:center;text-transform:uppercase;white-space:nowrap;
  border:1px solid #1a4a7a;letter-spacing:.4px;
}
.tt-grid th.period-col{background:#1a3a5c;min-width:72px;color:#fff}
.tt-grid td{border:1px solid #e8edf4;padding:0;vertical-align:top;min-width:130px;background:#fff}
.tt-cell{padding:8px 9px;min-height:56px;cursor:pointer;transition:.15s;position:relative}
.tt-cell:hover{background:#eff6ff}
.tt-cell.empty{background:#fafbfc;cursor:pointer}
.tt-cell.empty:hover{background:#f0f9ff}
.tt-entry{cursor:pointer;padding:2px 0}
.tt-entry:hover{background:#dbeafe;border-radius:5px;padding:2px 5px;margin:0 -5px}
.tt-cell .tc-name{font-size:11.5px;font-weight:700;color:var(--brand);line-height:1.3}
.tt-cell .tc-subj{font-size:11px;color:var(--text-2);margin-top:2px}
.tt-cell .tc-room{font-size:10px;color:var(--text-3);margin-top:1px}
.tt-cell .add-hint{font-size:11px;color:#cbd5e1;font-style:italic}
.period-label{
  background:#f1f5f9;color:#000000 !important;padding:9px 10px;font-size:12px;
  font-weight:800;text-align:center;border:1px solid #e2e8f0;white-space:nowrap;
}
.class-selector-bar{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:0}

/* ══════════════════════════════════════
   SAVE FLASH
══════════════════════════════════════ */
.save-flash{
  position:fixed;bottom:28px;right:28px;
  background:linear-gradient(135deg,#059669,#10b981);color:#fff;
  padding:11px 22px;border-radius:10px;font-size:13px;font-weight:700;
  box-shadow:0 6px 20px rgba(5,150,105,.35);z-index:2000;
  opacity:0;transition:all .3s;pointer-events:none;transform:translateY(8px);
}
.save-flash.show{opacity:1;transform:translateY(0)}
.err-flash{background:linear-gradient(135deg,#dc2626,#ef4444);box-shadow:0 6px 20px rgba(220,38,38,.35)}

/* ══════════════════════════════════════
   MODAL
══════════════════════════════════════ */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(15,23,42,.5);
               backdrop-filter:blur(4px);z-index:1000;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{
  background:#fff;border-radius:16px;padding:30px;width:530px;max-width:96vw;
  max-height:90vh;overflow-y:auto;box-shadow:var(--shadow-lg);
  border:1px solid var(--border);animation:modalIn .2s ease-out;
}
@keyframes modalIn{from{opacity:0;transform:scale(.96) translateY(8px)}to{opacity:1;transform:none}}
.modal h2{font-size:16px;font-weight:700;color:var(--brand);margin-bottom:22px;
  padding-bottom:14px;border-bottom:1.5px solid var(--border)}
.modal-fields{display:flex;flex-direction:column;gap:15px}
.modal-row{display:flex;gap:12px}
.modal-row .fg{flex:1}
.modal-footer{display:flex;justify-content:flex-end;gap:10px;margin-top:24px;
              padding-top:18px;border-top:1px solid var(--border)}

/* ══════════════════════════════════════
   FILTER BAR
══════════════════════════════════════ */
.filter-bar{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap;align-items:center}
.filter-bar input,.filter-bar select{
  padding:8px 12px;border:1.5px solid var(--border);border-radius:8px;
  font-size:13px;font-family:inherit;outline:none;min-width:220px;transition:all .18s}
.filter-bar input:focus,.filter-bar select:focus{
  border-color:var(--brand-mid);box-shadow:0 0 0 3px rgba(37,99,235,.12)}

/* ══════════════════════════════════════
   ADMIN SUB-TABS
══════════════════════════════════════ */
.admin-tabs{display:flex;gap:0;margin-bottom:22px;
  background:var(--surface);border-radius:10px;padding:5px;
  box-shadow:var(--shadow-sm);border:1px solid var(--border);
  width:fit-content;}
.admin-tab-btn{
  padding:8px 20px;border:none;border-radius:7px;
  background:transparent;color:var(--text-2);
  font-size:13px;font-weight:600;font-family:inherit;cursor:pointer;
  transition:all .18s;white-space:nowrap;
}
.admin-tab-btn:hover{background:var(--brand-light);color:var(--brand-mid)}
.admin-tab-btn.active{
  background:linear-gradient(135deg,var(--brand),#2563eb);
  color:#fff;box-shadow:0 2px 8px rgba(37,99,235,.3);
}

/* ══════════════════════════════════════
   MISC
══════════════════════════════════════ */
.pc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.pc-card{border:1.5px solid var(--border);border-radius:10px;padding:14px;background:#fafafa}
.pc-card h3{font-size:12px;font-weight:700;color:var(--brand);margin-bottom:10px;text-transform:uppercase}
.pc-row{display:flex;align-items:center;justify-content:space-between;padding:5px 0;
        border-bottom:1px solid #f1f5f9;font-size:13px}
.pc-row:last-child{border-bottom:none}
.pc-label{color:#334155;font-weight:500}
.switch{position:relative;display:inline-block;width:40px;height:22px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;inset:0;background:#cbd5e1;border-radius:22px;transition:.3s}
.slider:before{position:absolute;content:"";height:16px;width:16px;left:3px;bottom:3px;
               background:#fff;border-radius:50%;transition:.3s;box-shadow:0 1px 3px rgba(0,0,0,.2)}
input:checked+.slider{background:var(--green)}
input:checked+.slider:before{transform:translateX(18px)}

/* ══════════════════════════════════════
   SMART CLASS
══════════════════════════════════════ */
.smart-badge{
  display:inline-flex;align-items:center;gap:3px;
  background:linear-gradient(135deg,#ccfbf1,#99f6e4);
  color:#0f766e;border:1px solid #5eead4;
  padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700;
  margin-bottom:2px;letter-spacing:.2px;
}
.tt-entry.smart-entry{
  background:#f0fdfa;border-radius:5px;padding:3px 5px;margin:1px -5px;
  border-left:2px solid #14b8a6;
}
.tt-entry.smart-entry:hover{background:#ccfbf1}
.tt-entry.smart-entry .tc-name{color:#0d9488}

/* ══════════════════════════════════════
   PRINT
══════════════════════════════════════ */
@media print{
  body{background:#fff}
  .hdr{-webkit-print-color-adjust:exact;print-color-adjust:exact;position:static}
  .no-print{display:none!important}
  .card{box-shadow:none;border:1px solid var(--border);break-inside:avoid}
  th{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .grp td{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .pbdg{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  #rpt{display:block!important}
  #inputCard{display:none}
}
</style>
</head>
<body>

<!-- ── HEADER ── -->
<div class="hdr">
  <div class="hdr-logo">🏫</div>
  <div class="hdr-text">
    <h1>Teacher Substitution System</h1>
    <p>Gyan Niketan School &nbsp;·&nbsp; Session 2026–27</p>
  </div>
  <nav class="hdr-nav no-print">
    <button class="nav-btn active" id="nav-report"   onclick="showPage('report')">📋 Report</button>
    <button class="nav-btn"        id="nav-teachers" onclick="showPage('teachers')">👥 Teachers</button>
    <button class="nav-btn"        id="nav-admin"    onclick="showPage('admin')">⚙️ Admin</button>
  </nav>
</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!--  PAGE: REPORT                                              -->
<!-- ═══════════════════════════════════════════════════════════ -->
<div class="wrap" id="page-report">

  <div class="card" id="inputCard">
    <div class="card-title"><span class="card-title-left">📋 Mark Absent Teachers &amp; Generate Report</span></div>
    <div class="form-row">
      <div class="fg" style="max-width:210px">
        <label for="di">Date</label>
        <input type="date" id="di" min="" max="">
      </div>
      <div class="fg">
        <label>Absent Teachers</label>
        <div class="sw">
          <input type="text" id="ts" placeholder="Type teacher name to search…">
          <div id="dd"></div>
        </div>
        <div class="tags" id="tags"></div>
      </div>
      <div class="fg" style="max-width:190px">
        <label>&nbsp;</label>
        <button class="btn" id="genBtn" onclick="generate()">⚡ Generate Report</button>
      </div>
    </div>
  </div>

  <div class="err" id="err"></div>
  <div class="spin" id="spin">Running OR-Tools optimizer…</div>

  <div class="card" id="rpt" style="display:none">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <strong id="rTitle" style="color:var(--brand);font-size:17px;display:block;margin-bottom:3px;font-weight:800"></strong>
        <span id="rMeta" style="font-size:13px;color:var(--text-2)"></span>
      </div>
      <div style="display:flex;gap:8px" class="no-print">
        <button class="btn btn-green btn-print" onclick="window.print()">🖨️ Print</button>
        <button class="btn btn-gray btn-sm" style="padding:8px 16px" onclick="resetReport()">← New Report</button>
      </div>
    </div>
    <div class="badges" id="badges"></div>
    <div id="noSchedWarn"></div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>Period</th><th>Class</th><th>Subject</th>
          <th>Absent Teacher</th><th>Substitute Teacher</th><th>Reason</th>
        </tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
    <div class="fnote">
      Generated by Teacher Substitution System &nbsp;·&nbsp;
      OR-Tools CP-SAT Optimizer &nbsp;·&nbsp; <span id="gt"></span>
    </div>
  </div>

</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!--  PAGE: TEACHERS                                            -->
<!-- ═══════════════════════════════════════════════════════════ -->
<div class="wrap" id="page-teachers" style="display:none">
  <div class="card">
    <div class="card-title">
      <span class="card-title-left">👥 Teacher Management</span>
      <button class="btn btn-green btn-sm" onclick="openTeacherModal()">+ Add Teacher</button>
    </div>

    <div class="filter-bar">
      <input type="text" id="teacherSearch" placeholder="Search by name, teacher no or subject…" oninput="filterTeachers()">
    </div>

    <div class="success-msg" id="teacherMsg"></div>
    <div id="teacherCount" style="font-size:12px;color:#64748b;margin-bottom:10px"></div>

    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>Teacher No</th><th>Full Name</th><th>Subject</th>
          <th>Designation</th><th class="no-print">Actions</th>
        </tr></thead>
        <tbody id="teacherTbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!--  PAGE: ADMIN                                               -->
<!-- ═══════════════════════════════════════════════════════════ -->
<div class="wrap" id="page-admin" style="display:none">

  <!-- Sub-tab bar -->
  <div class="admin-tabs no-print">
    <button id="admintab-tt" class="admin-tab-btn active" onclick="switchAdminTab('tt')">
      ⚙️&nbsp; Timetable Editor
    </button>
    <button id="admintab-ct" class="admin-tab-btn" onclick="switchAdminTab('ct')">
      🏫&nbsp; Class Teachers
    </button>
  </div>

  <!-- Sub-tab: Timetable Editor -->
  <div id="adminpanel-tt">
    <div class="card">
      <div class="card-title">
        <span class="card-title-left">⚙️ Timetable Editor
          <span style="font-size:11px;font-weight:400;color:#64748b;margin-left:8px">
            Click any cell to edit · Changes save to Supabase instantly
          </span>
        </span>
      </div>

      <div class="class-selector-bar">
        <div class="fg" style="max-width:160px">
          <label>Class</label>
          <select id="adminGradeSelect" onchange="populateSections()">
            <option value="">— Grade —</option>
          </select>
        </div>
        <div class="fg" style="max-width:160px">
          <label>Section</label>
          <select id="adminSectionSelect" onchange="loadAdminTimetable()">
            <option value="">— Section —</option>
          </select>
        </div>
        <div style="align-self:flex-end;padding-bottom:2px;color:var(--text-2);font-size:13px;font-weight:600" id="adminClassLabel"></div>
        <div style="align-self:flex-end;padding-bottom:2px">
          <button class="btn no-print" id="addSmartClassBtn" onclick="openSmartClassModal()"
            style="display:none;background:linear-gradient(135deg,#0d9488,#14b8a6);
                   box-shadow:0 2px 8px rgba(13,148,136,.3);font-size:12px;padding:8px 16px">
            ✨ Add Smart Class
          </button>
        </div>
      </div>

      <div id="adminTtHint" style="text-align:center;padding:40px;color:#94a3b8;font-size:14px">
        👆 Select a class above to view and edit its timetable
      </div>
      <div class="tt-grid" id="adminTtGrid" style="display:none"></div>
    </div>
  </div>

  <!-- Sub-tab: Class Teachers -->
  <div id="adminpanel-ct" style="display:none">
    <div class="card">
      <div class="card-title">
        <span class="card-title-left">🏫 Class Teacher List
          <span style="font-size:11px;font-weight:400;color:#64748b;margin-left:8px">
            Edit class teachers · Changes save to Supabase instantly
          </span>
        </span>
        <input type="text" id="ctSearch" placeholder="Search class or teacher…"
          oninput="filterCT()"
          style="padding:6px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px;width:220px">
      </div>
      <div class="success-msg" id="ctMsg" style="display:none;padding:8px 12px;margin-bottom:8px;background:#d4edda;border:1px solid #c3e6cb;border-radius:4px;color:#155724;font-size:13px"></div>
      <div class="tbl-wrap">
        <table id="ctTable">
          <thead><tr>
            <th style="width:120px">Class</th>
            <th>Class Teacher</th>
            <th class="no-print" style="width:100px">Save</th>
          </tr></thead>
          <tbody id="ctTbody">
            <tr><td colspan="3" style="text-align:center;padding:30px;color:#94a3b8">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>

<!-- Save flash notification -->
<div class="save-flash" id="saveFlash"></div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!--  MODALS                                                    -->
<!-- ═══════════════════════════════════════════════════════════ -->

<!-- Teacher Add/Edit Modal -->
<div class="modal-overlay" id="teacherModal">
  <div class="modal">
    <h2 id="teacherModalTitle">Add Teacher</h2>
    <div class="modal-fields">
      <div class="modal-row">
        <div class="fg">
          <label>Teacher No *</label>
          <input type="text" id="m_teacher_no" placeholder="e.g. T135">
        </div>
        <div class="fg">
          <label>Abbreviation</label>
          <input type="text" id="m_abbreviation" placeholder="e.g. ABC">
        </div>
      </div>
      <div class="fg">
        <label>Full Name *</label>
        <input type="text" id="m_full_name" placeholder="e.g. MR. JOHN SMITH">
      </div>
      <div class="modal-row">
        <div class="fg">
          <label>Subject</label>
          <input type="text" id="m_subject" placeholder="e.g. MATHEMATICS">
        </div>
        <div class="fg">
          <label>Designation</label>
          <select id="m_designation">
            <option>TEACHER</option><option>SENIOR TEACHER</option>
            <option>HEAD OF DEPARTMENT</option><option>PRINCIPAL</option>
            <option>VICE PRINCIPAL</option><option>PGT</option>
            <option>TGT</option><option>PRT</option>
          </select>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <label class="switch">
          <input type="checkbox" id="m_is_excluded">
          <span class="slider"></span>
        </label>
        <span style="font-size:13px;color:#475569">Exclude from substitution (Principal / VP)</span>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-gray btn-sm" onclick="closeModal('teacherModal')">Cancel</button>
      <button class="btn btn-green btn-sm" onclick="saveTeacher()">Save Teacher</button>
    </div>
  </div>
</div>

<!-- Timetable Cell Edit Modal -->
<div class="modal-overlay" id="cellModal">
  <div class="modal" style="max-width:420px">
    <h2 id="cellModalTitle">Edit Period</h2>
    <p id="cellModalSub" style="font-size:12px;color:#64748b;margin-bottom:18px"></p>
    <div class="modal-fields">
      <div class="fg">
        <label>Teacher</label>
        <select id="cell_teacher">
          <option value="">— Free Period / No Teacher —</option>
        </select>
      </div>
      <div class="fg">
        <label>Subject</label>
        <select id="cell_subject">
          <option value="">— None —</option>
        </select>
      </div>
      <div class="fg">
        <label>Room Type</label>
        <select id="cell_room_type">
          <option value="CLASSROOM">Classroom</option>
          <option value="SMART_CLASS">Smart Class</option>
          <option value="ROBOTICS">Robotics Lab</option>
          <option value="LAB">Science / Computer Lab</option>
        </select>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-red btn-sm" id="cellDeleteBtn" onclick="deleteCellEntry()" style="margin-right:auto">🗑️ Clear</button>
      <button class="btn btn-gray btn-sm" onclick="closeModal('cellModal')">Cancel</button>
      <button class="btn btn-green btn-sm" onclick="saveCellEntry()">Save</button>
    </div>
  </div>
</div>

<!-- Smart Class Modal -->
<div class="modal-overlay" id="smartClassModal">
  <div class="modal" style="max-width:440px">
    <h2 style="color:#0d9488">✨ Add Smart Class</h2>
    <p style="font-size:12px;color:var(--text-2);margin-bottom:18px">
      Adds an <strong>optional extra session</strong> for
      <strong id="scClassName"></strong> — does not remove any existing class.
    </p>
    <div class="modal-fields">
      <div class="modal-row">
        <div class="fg">
          <label>Day</label>
          <select id="sc_day">
            <option value="">— Select Day —</option>
            <option>Monday</option><option>Tuesday</option><option>Wednesday</option>
            <option>Thursday</option><option>Friday</option><option>Saturday</option>
          </select>
        </div>
        <div class="fg">
          <label>Period</label>
          <select id="sc_period">
            <option value="">— Select Period —</option>
            <option value="alpha1">α1 (Assembly 1)</option>
            <option value="alpha2">α2 (Assembly 2)</option>
            <option value="P1">1st Period</option>
            <option value="P2">2nd Period</option>
            <option value="P3">3rd Period</option>
            <option value="P4">4th Period</option>
            <option value="P5">5th Period</option>
            <option value="P6">6th Period</option>
            <option value="P7">7th Period</option>
            <option value="P8">8th Period</option>
          </select>
        </div>
      </div>
      <div class="fg">
        <label>Teacher</label>
        <select id="sc_teacher">
          <option value="">— No specific teacher —</option>
        </select>
      </div>
      <div class="fg">
        <label>Subject</label>
        <select id="sc_subject">
          <option value="">— None —</option>
        </select>
      </div>
      <div style="background:#f0fdfa;border:1px solid #99f6e4;border-radius:8px;
                  padding:10px 14px;font-size:12px;color:#0f766e;line-height:1.6">
        💡 Smart classes appear with a <strong>teal badge</strong> in the timetable grid.
        They are counted as optional and will not affect the regular substitution schedule.
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-gray btn-sm" onclick="closeModal('smartClassModal')">Cancel</button>
      <button class="btn btn-sm" onclick="saveSmartClass()"
        style="background:linear-gradient(135deg,#0d9488,#14b8a6);box-shadow:0 2px 8px rgba(13,148,136,.3)">
        ✨ Add Smart Class
      </button>
    </div>
  </div>
</div>

<!-- Confirm Delete Modal -->
<div class="modal-overlay" id="confirmModal">
  <div class="modal" style="max-width:380px">
    <h2>Confirm Delete</h2>
    <p id="confirmMsg" style="font-size:14px;color:#475569;margin:16px 0"></p>
    <div class="modal-footer">
      <button class="btn btn-gray btn-sm" onclick="closeModal('confirmModal')">Cancel</button>
      <button class="btn btn-red btn-sm" onclick="confirmDeleteFn()">Delete</button>
    </div>
  </div>
</div>

<script>
// ════════════════════════════════════════════════════════════
//  STATE
// ════════════════════════════════════════════════════════════
let allTeachers=[], selected=[];
let adminTeachers=[], adminClasses=[], adminSubjects=[];
let adminTimetableData=[];   // raw rows for current class
let currentCellMeta=null;    // {classId, day, period, existingId}
let editingTeacherId=null;
let confirmDeleteFn=()=>{};
const PERIOD_LABELS={alpha1:'α1',alpha2:'α2',P1:'1st',P2:'2nd',P3:'3rd',P4:'4th',
                     P5:'5th',P6:'6th',P7:'7th',P8:'8th'};
const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const ALL_PERIODS=['alpha1','alpha2','P1','P2','P3','P4','P5','P6','P7','P8'];

// ════════════════════════════════════════════════════════════
//  NAVIGATION
// ════════════════════════════════════════════════════════════
function showPage(p){
  ['report','teachers','admin'].forEach(n=>{
    document.getElementById('page-'+n).style.display = n===p?'block':'none';
    document.getElementById('nav-'+n).classList.toggle('active', n===p);
  });
  if(p==='teachers') loadAdminTeachers();
  if(p==='admin')    initAdminPage();
}

// ════════════════════════════════════════════════════════════
//  INIT
// ════════════════════════════════════════════════════════════
function fmtDate(d){
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+
         '-'+String(d.getDate()).padStart(2,'0');
}

async function init(){
  try{
    const r = await fetch('/api/teachers');
    allTeachers = await r.json();
  }catch(e){ showErr('Cannot connect to server.'); }

  const now=new Date(), hour=now.getHours();
  const today=new Date(now); today.setHours(0,0,0,0);
  const tomorrow=new Date(today); tomorrow.setDate(today.getDate()+1);
  const maxDate=new Date(today); maxDate.setDate(today.getDate()+90);
  const di=document.getElementById('di');
  const after5pm=hour>=17;
  di.min   = fmtDate(after5pm ? tomorrow : today);
  di.max   = fmtDate(maxDate);
  di.value = fmtDate(after5pm ? tomorrow : today);
}

// ════════════════════════════════════════════════════════════
//  REPORT PAGE
// ════════════════════════════════════════════════════════════
const ts=document.getElementById('ts');
const dd=document.getElementById('dd');

ts.addEventListener('input',function(){
  const q=this.value.toLowerCase().trim();
  dd.innerHTML='';
  if(!q){dd.style.display='none';return;}
  const m=allTeachers.filter(t=>t.full_name.toLowerCase().includes(q)&&!selected.find(s=>s.id===t.id)).slice(0,12);
  if(!m.length){dd.style.display='none';return;}
  m.forEach(t=>{
    const d=document.createElement('div');
    d.className='ddi';d.textContent=t.full_name;d.onclick=()=>pick(t);
    dd.appendChild(d);
  });
  dd.style.display='block';
});

document.addEventListener('click',e=>{if(!e.target.closest('.sw'))dd.style.display='none';});

function pick(t){if(selected.find(s=>s.id===t.id))return;selected.push(t);renderTags();ts.value='';dd.style.display='none';}
function removeTag(id){selected=selected.filter(t=>t.id!==id);renderTags();}
function renderTags(){
  const c=document.getElementById('tags');c.innerHTML='';
  selected.forEach(t=>{
    const el=document.createElement('div');el.className='tag';
    el.innerHTML=`${t.full_name} <span class="x" onclick="removeTag(${t.id})">×</span>`;
    c.appendChild(el);
  });
}

async function generate(){
  const dv=document.getElementById('di').value;
  if(!dv){showErr('Please select a date.');return;}
  if(!selected.length){showErr('Please select at least one absent teacher.');return;}
  hideErr();
  document.getElementById('spin').style.display='block';
  document.getElementById('rpt').style.display='none';
  document.getElementById('genBtn').disabled=true;
  try{
    const r=await fetch('/api/generate-report',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({absent_teacher_ids:selected.map(t=>t.id),absence_date:dv})});
    const data=await r.json();
    if(data.error){showErr(data.error);return;}
    renderReport(data);
  }catch(e){showErr('Server error: '+e.message);}
  finally{document.getElementById('spin').style.display='none';document.getElementById('genBtn').disabled=false;}
}

function renderReport(data){
  const rep=data.report;
  document.getElementById('rTitle').textContent='Substitution Report — '+data.date+' ('+data.weekday+')';
  document.getElementById('rMeta').textContent='Absent: '+selected.map(t=>t.full_name).join(', ');
  const covered=rep.filter(r=>r.substitute!=='No substitute available').length;
  const uncovered=rep.length-covered;
  document.getElementById('badges').innerHTML=
    `<span class="bdg bdg-b">📚 ${rep.length} Period${rep.length!==1?'s':''} to Cover</span>`+
    `<span class="bdg bdg-g">✅ ${covered} Covered</span>`+
    (uncovered?`<span class="bdg bdg-y">⚠️ ${uncovered} Uncovered</span>`:'')+
    `<span class="bdg bdg-b">👥 ${selected.length} Absent</span>`;

  const ns=data.no_schedule||[];
  const nw=document.getElementById('noSchedWarn');
  nw.innerHTML=ns.length?`<div style="background:#fefce8;border:1px solid #fde047;border-radius:8px;
    padding:9px 13px;margin-bottom:12px;font-size:13px;color:#92400e">
    ℹ️ <b>No timetable found on ${data.weekday} for:</b> ${ns.join(', ')}</div>`:'';

  const groups={},order=[];
  rep.forEach(r=>{if(!groups[r.period]){groups[r.period]=[];order.push(r.period);}groups[r.period].push(r);});

  const tbody=document.getElementById('tbody');tbody.innerHTML='';
  order.forEach(period=>{
    const rows=groups[period]||[];
    const label=rows[0]?rows[0].period_label:period;
    const gh=document.createElement('tr');gh.className='grp';
    gh.innerHTML=`<td colspan="6">🕐 &nbsp;Period ${label}</td>`;
    tbody.appendChild(gh);
    rows.forEach(r=>{
      const no=r.substitute==='No substitute available';
      const alt=r.alternatives.length?'Also: '+r.alternatives.join(' / '):'';
      const tr=document.createElement('tr');
      tr.innerHTML=`<td><span class="pbdg">${r.period_label}</span></td>`+
        `<td><span class="cbdg">${r.class_name}</span><div class="gb">${r.grade_band}</div></td>`+
        `<td><b>${r.subject}</b></td>`+
        `<td><span class="absent-lbl">${r.absent_teacher}</span></td>`+
        `<td><span class="${no?'sub-no':'sub-ok'}">${r.substitute}</span>${alt?`<div class="alt">${alt}</div>`:''}</td>`+
        `<td><span class="rsn">${r.reason}</span></td>`;
      tbody.appendChild(tr);
    });
  });

  document.getElementById('gt').textContent='Generated at '+new Date().toLocaleTimeString();
  document.getElementById('rpt').style.display='block';
  document.getElementById('rpt').scrollIntoView({behavior:'smooth'});
}

function showErr(m){const b=document.getElementById('err');b.textContent='⚠️  '+m;b.style.display='block';document.getElementById('spin').style.display='none';}
function hideErr(){document.getElementById('err').style.display='none';}
function resetReport(){document.getElementById('rpt').style.display='none';document.getElementById('inputCard').scrollIntoView({behavior:'smooth'});}

// ════════════════════════════════════════════════════════════
//  TEACHERS PAGE
// ════════════════════════════════════════════════════════════
async function loadAdminTeachers(){
  const r=await fetch('/api/admin/teachers');
  adminTeachers=await r.json();
  renderTeachers(adminTeachers);
}

function filterTeachers(){
  const q=document.getElementById('teacherSearch').value.toLowerCase();
  let list=adminTeachers;
  if(q) list=list.filter(t=>
    (t.full_name||'').toLowerCase().includes(q)||
    (t.teacher_no||'').toLowerCase().includes(q)||
    (t.subject||'').toLowerCase().includes(q)
  );
  renderTeachers(list);
}

function renderTeachers(list){
  document.getElementById('teacherCount').textContent=`Showing ${list.length} of ${adminTeachers.length} teachers`;
  const tbody=document.getElementById('teacherTbody');
  tbody.innerHTML=list.map(t=>`
    <tr>
      <td><b>${t.teacher_no}</b></td>
      <td>${t.full_name}</td>
      <td style="color:#64748b">${t.subject||'—'}</td>
      <td style="color:#64748b;font-size:12px">${t.designation||'TEACHER'}</td>
      <td class="no-print">
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm" style="background:#f1f5f9;color:#334155;border:1px solid #e2e8f0"
            onclick="openTeacherModal(${t.id})">✏️ Edit</button>
          <button class="btn btn-sm btn-red" onclick="deleteTeacher(${t.id},'${t.full_name.replace(/'/g,"\\'")}')">🗑️</button>
        </div>
      </td>
    </tr>`).join('');
}

function openTeacherModal(id=null){
  editingTeacherId=id;
  document.getElementById('teacherModalTitle').textContent=id?'Edit Teacher':'Add Teacher';
  if(id){
    const t=adminTeachers.find(x=>x.id===id);
    document.getElementById('m_teacher_no').value=t.teacher_no||'';
    document.getElementById('m_full_name').value=t.full_name||'';
    document.getElementById('m_subject').value=t.subject||'';
    document.getElementById('m_designation').value=t.designation||'TEACHER';
    document.getElementById('m_abbreviation').value=t.abbreviation||'';
    document.getElementById('m_is_excluded').checked=t.is_excluded||false;
    document.getElementById('m_teacher_no').disabled=true;
  } else {
    ['m_teacher_no','m_full_name','m_subject','m_abbreviation'].forEach(id=>document.getElementById(id).value='');
    document.getElementById('m_designation').value='TEACHER';
    document.getElementById('m_is_excluded').checked=false;
    document.getElementById('m_teacher_no').disabled=false;
  }
  document.getElementById('teacherModal').classList.add('open');
}

async function saveTeacher(){
  const data={
    teacher_no: document.getElementById('m_teacher_no').value.trim().toUpperCase(),
    full_name:  document.getElementById('m_full_name').value.trim().toUpperCase(),
    subject:    document.getElementById('m_subject').value.trim().toUpperCase()||null,
    designation:document.getElementById('m_designation').value,
    abbreviation:document.getElementById('m_abbreviation').value.trim().toUpperCase()||null,
    is_excluded:document.getElementById('m_is_excluded').checked,
  };
  if(!data.full_name){alert('Full name is required');return;}
  if(!editingTeacherId && !data.teacher_no){alert('Teacher No is required');return;}

  try{
    let res, json;
    if(editingTeacherId){
      delete data.teacher_no;
      res=await fetch(`/api/admin/teachers/${editingTeacherId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    } else {
      res=await fetch('/api/admin/teachers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    }
    json=await res.json().catch(()=>({}));
    if(!res.ok){alert('Error saving teacher: '+(json.error||json.message||res.status));return;}
    closeModal('teacherModal');
    showTeacherMsg(editingTeacherId?'Teacher updated successfully!':'Teacher added successfully!');
    await loadAdminTeachers();
    filterTeachers();
  }catch(e){alert('Error: '+e.message);}
}

function deleteTeacher(id,name){
  document.getElementById('confirmMsg').textContent=`Delete "${name}"? This cannot be undone.`;
  confirmDeleteFn=async()=>{
    await fetch(`/api/admin/teachers/${id}`,{method:'DELETE'});
    closeModal('confirmModal');
    showTeacherMsg('Teacher deleted.');
    await loadAdminTeachers();
    filterTeachers();
  };
  document.getElementById('confirmModal').classList.add('open');
}

function showTeacherMsg(m){
  const el=document.getElementById('teacherMsg');
  el.textContent='✅ '+m;el.style.display='block';
  setTimeout(()=>el.style.display='none',3000);
}

// ════════════════════════════════════════════════════════════
//  ADMIN — TIMETABLE GRID
// ════════════════════════════════════════════════════════════
async function initAdminPage(){
  // Load supporting data once
  const [tr, sr, cr] = await Promise.all([
    fetch('/api/admin/teachers').then(r=>r.json()),
    fetch('/api/admin/subjects').then(r=>r.json()),
    fetch('/api/admin/classes').then(r=>r.json()),
  ]);
  adminTeachers = tr;
  adminSubjects = sr;
  adminClasses  = cr;

  // Populate modal dropdowns
  document.getElementById('cell_teacher').innerHTML =
    '<option value="">— Free Period / No Teacher —</option>' +
    adminTeachers.map(t=>`<option value="${t.id}">${t.teacher_no} — ${t.full_name}</option>`).join('');
  document.getElementById('cell_subject').innerHTML =
    '<option value="">— None —</option>' +
    adminSubjects.map(s=>`<option value="${s.id}">${s.code}</option>`).join('');

  loadAdminClassList();
}

function loadAdminClassList(){
  const grades = [...new Set(adminClasses.map(c=>c.grade).filter(Boolean))].sort((a,b)=>a-b);
  const preNames = ['NURSERY','LKG','UKG'];
  const preOpts  = preNames
    .filter(n=>adminClasses.some(c=>c.name===n||c.name.startsWith(n+' ')))
    .map(n=>`<option value="__${n}">${n}</option>`).join('');
  document.getElementById('adminGradeSelect').innerHTML =
    '<option value="">— Grade —</option>' +
    grades.map(g=>`<option value="${g}">${g}</option>`).join('') +
    (preOpts?`<optgroup label="Pre-Primary">${preOpts}</optgroup>`:'');
  document.getElementById('adminSectionSelect').innerHTML = '<option value="">— Section —</option>';
  document.getElementById('adminTtHint').style.display='block';
  document.getElementById('adminTtGrid').style.display='none';
  document.getElementById('addSmartClassBtn').style.display='none';
}

function populateSections(){
  const raw   = document.getElementById('adminGradeSelect').value;
  const grade = raw.startsWith('__') ? raw : parseInt(raw);
  document.getElementById('adminTtGrid').style.display='none';
  document.getElementById('adminTtHint').style.display='block';
  document.getElementById('adminClassLabel').textContent='';
  if(!grade){ document.getElementById('adminSectionSelect').innerHTML='<option value="">— Section —</option>'; return; }
  let sections;
  if(typeof grade==='string' && grade.startsWith('__')){
    const pname = grade.slice(2);
    sections = adminClasses
      .filter(c=>c.name===pname || c.name.startsWith(pname+' '))
      .filter(c=>!c.name.includes('LAB')&&!c.name.includes('PRACT')&&!c.name.includes('+'))
      .map(c=>c.name===pname?'—':c.name.replace(pname+' ',''))
      .sort();
  } else {
    sections = adminClasses.filter(c=>c.grade===grade && c.section).map(c=>c.section).sort();
  }
  document.getElementById('adminSectionSelect').innerHTML =
    '<option value="">— Section —</option>' +
    sections.map(s=>`<option value="${s}">${s}</option>`).join('');
}

async function loadAdminTimetable(){
  const raw     = document.getElementById('adminGradeSelect').value;
  const grade   = raw.startsWith('__') ? raw : parseInt(raw);
  const section = document.getElementById('adminSectionSelect').value;
  if(!grade || !section){
    document.getElementById('adminTtHint').style.display='block';
    document.getElementById('adminTtGrid').style.display='none';
    document.getElementById('addSmartClassBtn').style.display='none';
    return;
  }
  let cls;
  if(typeof grade==='string' && grade.startsWith('__')){
    const pname = grade.slice(2);
    cls = adminClasses.find(c=>section==='—'?c.name===pname:c.name===pname+' '+section);
  } else {
    cls = adminClasses.find(c=>c.grade===grade && c.section===section);
  }
  if(!cls){
    document.getElementById('adminTtHint').textContent='No class found for that combination.';
    document.getElementById('adminTtHint').style.display='block';
    document.getElementById('adminTtGrid').style.display='none';
    return;
  }
  document.getElementById('adminClassLabel').textContent='📚 '+cls.name;
  const r = await fetch(`/api/admin/timetable?class_id=${cls.id}`);
  adminTimetableData = await r.json();
  // store class id for cell modal
  window._adminCurrentClassId = cls.id;
  window._adminCurrentClassName = cls.name;
  document.getElementById('adminTtHint').style.display='none';
  document.getElementById('adminTtGrid').style.display='block';
  document.getElementById('addSmartClassBtn').style.display='inline-block';
  renderAdminTimetable();
}

function renderAdminTimetable(){
  const days = DAYS;

  // Build lookup: day+period → array of rows (handles multiple entries per slot)
  const lookup = {};
  adminTimetableData.forEach(r=>{
    const key = r.day+'__'+r.period_name;
    if(!lookup[key]) lookup[key]=[];
    lookup[key].push(r);
  });

  // Show all periods that appear in data
  const usedPeriods = new Set(adminTimetableData.map(r=>r.period_name));
  const showPeriods = ALL_PERIODS.filter(p=>usedPeriods.has(p));
  const periodsToShow = showPeriods.length ? showPeriods : ALL_PERIODS;

  let html = '<table><thead><tr>';
  html += '<th class="period-col">Period</th>';
  days.forEach(d=>{ html+=`<th>${d}</th>`; });
  html += '</tr></thead><tbody>';

  periodsToShow.forEach(period=>{
    html += '<tr>';
    html += `<td class="period-label">${PERIOD_LABELS[period]||period}</td>`;
    days.forEach(day=>{
      const key = day+'__'+period;
      const rows = lookup[key];
      if(rows && rows.length){
        // Use first row's id for click (primary entry)
        const firstId = rows[0].id;
        const cellContent = rows.map(row=>{
          const tname   = (row.teachers||{}).full_name || '—';
          const tno     = (row.teachers||{}).teacher_no || '';
          const subj    = (row.subjects||{}).code || '';
          const isSmart = row.room_type === 'SMART_CLASS';
          const isOther = row.room_type && row.room_type!=='CLASSROOM' && !isSmart;
          const smartBadge = isSmart
            ? `<div class="smart-badge">✨ Smart Class</div>` : '';
          const roomBadge  = isOther
            ? `<div class="tc-room">📍 ${row.room_type.replace(/_/g,' ')}</div>` : '';
          return `<div class="tt-entry${isSmart?' smart-entry':''}" onclick="openCellModal(${row.id},'${day}','${period}',true)">
            ${smartBadge}
            <div class="tc-name">${tname}${tno?` <span style="color:#94a3b8;font-weight:400;font-size:10px">(${tno})</span>`:''}</div>
            ${subj?`<div class="tc-subj">${subj}</div>`:''}
            ${roomBadge}
          </div>`;
        }).join('<div style="border-top:1px dashed #e2e8f0;margin:3px 0"></div>');
        html+=`<td><div class="tt-cell">${cellContent}</div></td>`;
      } else {
        html+=`<td><div class="tt-cell empty" onclick="openCellModal(null,'${day}','${period}',false)">
          <span class="add-hint">+ assign</span>
        </div></td>`;
      }
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  document.getElementById('adminTtGrid').innerHTML = html;
}

function openCellModal(existingId, day, period, hasEntry){
  currentCellMeta = {classId: window._adminCurrentClassId, day, period, existingId};

  document.getElementById('cellModalTitle').textContent =
    `${PERIOD_LABELS[period]||period} — ${day}`;
  document.getElementById('cellModalSub').textContent =
    `Class: ${window._adminCurrentClassName||''}`;
  document.getElementById('cellDeleteBtn').style.display = hasEntry ? 'inline-block' : 'none';

  if(hasEntry && existingId){
    const row = adminTimetableData.find(r=>r.id===existingId);
    document.getElementById('cell_teacher').value  = (row?.teachers?.id)  || '';
    document.getElementById('cell_subject').value  = (row?.subjects?.id)  || '';
    document.getElementById('cell_room_type').value= row?.room_type || 'CLASSROOM';
  } else {
    document.getElementById('cell_teacher').value  = '';
    document.getElementById('cell_subject').value  = '';
    document.getElementById('cell_room_type').value= 'CLASSROOM';
  }
  document.getElementById('cellModal').classList.add('open');
}

async function saveCellEntry(){
  const {classId, day, period, existingId} = currentCellMeta;
  const teacherId = parseInt(document.getElementById('cell_teacher').value)||null;
  const subjectId = parseInt(document.getElementById('cell_subject').value)||null;
  const roomType  = document.getElementById('cell_room_type').value;

  if(!teacherId){
    // No teacher selected — treat as clear
    if(existingId) await fetch(`/api/admin/timetable/${existingId}`,{method:'DELETE'});
    closeModal('cellModal');
    flashSave('Period cleared');
    await loadAdminTimetable();
    return;
  }

  const payload={class_id:classId,teacher_id:teacherId,subject_id:subjectId,
                 day,period_name:period,room_type:roomType,is_practical:false};
  try{
    const url=existingId?`/api/admin/timetable/${existingId}`:'/api/admin/timetable';
    const res=await fetch(url,{
      method:existingId?'PUT':'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const body=await res.json().catch(()=>({}));
    if(!res.ok){
      flashSave('⚠️ '+(body.error||'Could not save'),'err');
      closeModal('cellModal');
      return;
    }
    closeModal('cellModal');
    const cleared=body.cleared_from||[];
    if(cleared.length){
      flashSave('✅ Saved — teacher removed from '+cleared.join(', ')+' for this period (now blank there)');
    } else {
      flashSave('✅ Saved to Supabase');
    }
    await loadAdminTimetable();
  }catch(e){
    flashSave('Error saving: '+e.message,'err');
    closeModal('cellModal');
  }
}

async function deleteCellEntry(){
  const {existingId}=currentCellMeta;
  if(existingId){
    await fetch(`/api/admin/timetable/${existingId}`,{method:'DELETE'});
  }
  closeModal('cellModal');
  flashSave('Period cleared');
  await loadAdminTimetable();
}

function flashSave(msg, type=''){
  const el=document.getElementById('saveFlash');
  el.textContent=msg;
  el.className='save-flash show'+(type==='err'?' err-flash':'');
  setTimeout(()=>el.className='save-flash',2500);
}

// ════════════════════════════════════════════════════════════
//  ADMIN — SMART CLASS
// ════════════════════════════════════════════════════════════
function openSmartClassModal(){
  const className = window._adminCurrentClassName || '';
  document.getElementById('scClassName').textContent = className;

  // Populate teacher + subject dropdowns from already-loaded data
  document.getElementById('sc_teacher').innerHTML =
    '<option value="">— No specific teacher —</option>' +
    (adminTeachers||[]).map(t=>
      `<option value="${t.id}">${t.teacher_no ? t.teacher_no+' — ':'' }${t.full_name}</option>`
    ).join('');
  document.getElementById('sc_subject').innerHTML =
    '<option value="">— None —</option>' +
    (adminSubjects||[]).map(s=>`<option value="${s.id}">${s.code}</option>`).join('');

  // Reset selections
  document.getElementById('sc_day').value    = '';
  document.getElementById('sc_period').value = '';
  document.getElementById('sc_teacher').value= '';
  document.getElementById('sc_subject').value= '';

  document.getElementById('smartClassModal').classList.add('open');
}

async function saveSmartClass(){
  const classId   = window._adminCurrentClassId;
  const day       = document.getElementById('sc_day').value;
  const period    = document.getElementById('sc_period').value;
  const teacherId = parseInt(document.getElementById('sc_teacher').value)||null;
  const subjectId = parseInt(document.getElementById('sc_subject').value)||null;

  if(!day)    { alert('Please select a day.');    return; }
  if(!period) { alert('Please select a period.'); return; }

  const payload = {
    class_id:    classId,
    teacher_id:  teacherId,
    subject_id:  subjectId,
    day,
    period_name: period,
    room_type:   'SMART_CLASS',
    is_practical: false,
  };

  try{
    const res = await fetch('/api/admin/timetable', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });

    if(res.status === 409){
      // Smart class already exists for this slot — still fine, just warn
      flashSave('⚠️ A Smart Class already exists for this day/period','err');
      closeModal('smartClassModal');
      return;
    }
    if(!res.ok){
      const e = await res.json().catch(()=>({}));
      flashSave('⚠️ '+(e.error||'Could not add smart class'),'err');
      closeModal('smartClassModal');
      return;
    }

    closeModal('smartClassModal');
    flashSave('✨ Smart Class added!');
    await loadAdminTimetable();    // refresh grid
  }catch(e){
    flashSave('Error: '+e.message,'err');
    closeModal('smartClassModal');
  }
}

// ════════════════════════════════════════════════════════════
//  ADMIN — SUB-TAB SWITCHER
// ════════════════════════════════════════════════════════════
function switchAdminTab(tab){
  ['tt','ct'].forEach(t=>{
    document.getElementById('adminpanel-'+t).style.display = t===tab?'block':'none';
    document.getElementById('admintab-'+t).classList.toggle('active', t===tab);
  });
  if(tab==='ct') loadClassTeachers();
}

// ════════════════════════════════════════════════════════════
//  ADMIN — CLASS TEACHER LIST
// ════════════════════════════════════════════════════════════
let ctData = [];          // [{class_id, teacher_id, class_name, teacher_name}, …]
let ctTeachers = [];      // flat teacher list for dropdowns

async function loadClassTeachers(){
  const tbody = document.getElementById('ctTbody');
  tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#94a3b8">Loading…</td></tr>';
  try{
    // Use already-loaded adminTeachers; fetch CT rows
    ctTeachers = adminTeachers || [];
    if(!ctTeachers.length){
      const r = await fetch('/api/admin/teachers');
      ctTeachers = await r.json();
    }

    // Fetch class_teachers with nested class + teacher info
    const r = await fetch('/api/admin/class-teachers');
    ctData = await r.json();

    // Build a lookup: class_id → row
    const byClass = {};
    ctData.forEach(row=>{
      byClass[row.class_id] = row;
    });

    // Only main classes: NURSERY, UKG A/B/C and Grade 1–12 sections (no LAB/LIB/PRACT/A/V/OPT/+ etc.)
    const SKIP_RE = /\b(LAB|LIB|PRACT|A\/V|OPT|GK|RL)\b|[\r\n+]/i;
    const UKG_RE  = /^UKG\s+[A-Z]$/i;
    const MAIN_RE = /^\d+[A-Z]$/;   // e.g. 7D, 12A
    const SKIP_NAMES = new Set(['LKG']);

    const allClasses = adminClasses || [];
    const rows = allClasses
      .filter(cls=>{
        const n = (cls.name||'').trim();
        if(SKIP_NAMES.has(n.toUpperCase())) return false;
        if(SKIP_RE.test(n)) return false;
        if(n.toUpperCase()==='NURSERY') return true;
        if(UKG_RE.test(n)) return true;
        if(MAIN_RE.test(n)) return true;
        return false;
      })
      .map(cls=>{
        const existing = byClass[cls.id];
        return {
          class_id:   cls.id,
          class_name: cls.name.trim(),
          grade:      cls.grade,
          section:    cls.section,
          teacher_id: existing ? existing.teacher_id : null,
        };
      });

    // Sort: Grade 1–12 first, then UKG A/B/C, then NURSERY at bottom
    const prePriOrder = n => /^UKG/i.test(n) ? 1 : /^NURSERY$/i.test(n) ? 2 : 0;
    rows.sort((a,b)=>{
      const pa=prePriOrder(a.class_name), pb=prePriOrder(b.class_name);
      if(pa||pb){                        // at least one is pre-primary
        if(pa&&pb) return pa!==pb ? pa-pb : a.class_name.localeCompare(b.class_name);
        return pa ? 1 : -1;             // pre-primary always after numbered
      }
      const ag=Number(a.grade)||999, bg=Number(b.grade)||999;
      if(ag!==bg) return ag-bg;
      return a.class_name.localeCompare(b.class_name);
    });

    renderCT(rows);
  }catch(e){
    tbody.innerHTML = `<tr><td colspan="3" style="color:#d9534f;padding:20px;text-align:center">Error: ${e.message}</td></tr>`;
  }
}

function renderCT(rows){
  const filter = (document.getElementById('ctSearch').value||'').toLowerCase();
  const tbody = document.getElementById('ctTbody');

  const teacherOptions = ctTeachers.map(t=>
    `<option value="${t.id}">${t.teacher_no ? t.teacher_no+' — ' : ''}${t.full_name}</option>`
  ).join('');

  // group key: for UKG use 'UKG', for numeric grade use the grade number
  const groupKey = row => /^UKG/i.test(row.class_name) ? 'UKG' : /^NURSERY$/i.test(row.class_name) ? 'Nursery' : `Class ${row.grade}`;
  let lastGroup = null;
  let html = '';
  rows.forEach(row=>{
    const searchStr = (row.class_name+' '+(row.teacher_name||'')).toLowerCase();
    if(filter && !searchStr.includes(filter)) return;

    const grp = groupKey(row);
    if(grp !== lastGroup){
      html += `<tr style="background:#f0f4f8"><td colspan="3" style="font-weight:700;font-size:12px;color:#475569;padding:6px 10px;letter-spacing:.5px">${grp}</td></tr>`;
      lastGroup = grp;
    }

    const selVal = row.teacher_id || '';
    html += `<tr data-class-id="${row.class_id}">
      <td style="font-weight:600">${row.class_name}</td>
      <td>
        <select class="ct-sel" data-class-id="${row.class_id}" style="width:100%;padding:5px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px">
          <option value="">— No Class Teacher —</option>
          ${teacherOptions}
        </select>
      </td>
      <td class="no-print" style="text-align:center">
        <button onclick="saveCT(${row.class_id})"
          style="padding:5px 14px;background:#337ab7;color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer">
          Save
        </button>
        ${selVal ? `<button onclick="deleteCT(${row.class_id})"
          style="padding:5px 10px;background:#fff;color:#d9534f;border:1px solid #d9534f;border-radius:4px;font-size:12px;cursor:pointer;margin-left:4px">
          ✕
        </button>` : ''}
      </td>
    </tr>`;
  });
  if(!html) html = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#94a3b8">No results</td></tr>';
  tbody.innerHTML = html;

  // Set dropdown values after render
  rows.forEach(row=>{
    if(!row.teacher_id) return;
    const sel = tbody.querySelector(`.ct-sel[data-class-id="${row.class_id}"]`);
    if(sel) sel.value = row.teacher_id;
  });
}

function filterCT(){
  const SKIP_RE  = /\b(LAB|LIB|PRACT|A\/V|OPT|GK|RL)\b|[\r\n+]/i;
  const UKG_RE   = /^UKG\s+[A-Z]$/i;
  const MAIN_RE  = /^\d+[A-Z]$/;
  const SKIP_NMS = new Set(['LKG']);
  const byClass  = {};
  ctData.forEach(row=>{ byClass[row.class_id]=row; });
  const rows = (adminClasses||[])
    .filter(cls=>{
      const n=(cls.name||'').trim();
      if(SKIP_NMS.has(n.toUpperCase())) return false;
      if(SKIP_RE.test(n)) return false;
      if(n.toUpperCase()==='NURSERY') return true;
      return UKG_RE.test(n) || MAIN_RE.test(n);
    })
    .map(cls=>{
      const ex=byClass[cls.id];
      return { class_id:cls.id, class_name:cls.name.trim(), grade:cls.grade,
               section:cls.section, teacher_id:ex?ex.teacher_id:null,
               teacher_name:ex&&ex.teachers?ex.teachers.full_name:'' };
    });
  const ppo=n=>/^UKG/i.test(n)?1:/^NURSERY$/i.test(n)?2:0;
  rows.sort((a,b)=>{
    const pa=ppo(a.class_name),pb=ppo(b.class_name);
    if(pa||pb){ if(pa&&pb) return pa!==pb?pa-pb:a.class_name.localeCompare(b.class_name); return pa?1:-1; }
    const ag=Number(a.grade)||999,bg=Number(b.grade)||999;
    return ag!==bg?ag-bg:a.class_name.localeCompare(b.class_name);
  });
  renderCT(rows);
}

async function saveCT(classId){
  const sel = document.querySelector(`.ct-sel[data-class-id="${classId}"]`);
  if(!sel) return;
  const teacherId = sel.value;
  if(!teacherId){ await deleteCT(classId); return; }

  try{
    const r = await fetch(`/api/admin/class-teachers/${classId}`, {
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({teacher_id: parseInt(teacherId)})
    });
    const json = await r.json().catch(()=>({}));
    if(!r.ok){ alert('Save failed: '+(json.error||r.status)); return; }

    // Update ctData cache
    const existing = ctData.find(x=>x.class_id===classId);
    if(existing) existing.teacher_id = parseInt(teacherId);
    else ctData.push({class_id:classId, teacher_id:parseInt(teacherId)});

    showCTMsg('✅ Saved!');
  }catch(e){ alert('Error: '+e.message); }
}

async function deleteCT(classId){
  try{
    const r = await fetch(`/api/admin/class-teachers/${classId}`, {method:'DELETE'});
    if(!r.ok){ const j=await r.json().catch(()=>({})); alert('Delete failed: '+(j.error||r.status)); return; }
    // Remove from cache
    ctData = ctData.filter(x=>x.class_id!==classId);
    // Re-render
    filterCT();
    showCTMsg('✅ Removed.');
  }catch(e){ alert('Error: '+e.message); }
}

function showCTMsg(msg){
  const el = document.getElementById('ctMsg');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(()=>el.style.display='none', 2500);
}

// ════════════════════════════════════════════════════════════
//  MODAL HELPERS
// ════════════════════════════════════════════════════════════
function closeModal(id){document.getElementById(id).classList.remove('open');}

document.querySelectorAll('.modal-overlay').forEach(m=>{
  m.addEventListener('click',e=>{if(e.target===m) m.classList.remove('open');});
});

// ════════════════════════════════════════════════════════════
//  START
// ════════════════════════════════════════════════════════════
init();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

# ─────────────────────────────────────────────────────────────
# START
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"
    print("="*52)
    print("  Teacher Substitution System")
    print("  Gyan Niketan School — 2026-27")
    print("="*52)
    print(f"  This PC    :  http://localhost:8000")
    print(f"  School LAN :  http://{local_ip}:8000")
    print("  Press Ctrl+C to stop.")
    print("="*52)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
