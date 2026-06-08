"""
Teacher Substitution System — Gyan Niketan Public School
=========================================================
Single file: UI + Backend + OR-Tools + Report

HOW TO RUN:
  Double-click  START.bat
  Then open:    http://localhost:8000
"""

import os, httpx
from datetime import date
from collections import defaultdict
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from ortools.sat.python import cp_model
import uvicorn, socket

# ─────────────────────────────────────────────────────────────
# SUPABASE — connects via HTTPS (REST API), no DNS issues
# ─────────────────────────────────────────────────────────────

SUPABASE_PROJECT_URL = "https://lvsdwybkfvzioykhnfai.supabase.co"
SUPABASE_SERVICE_KEY = "sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V"

_HEADERS = {
    "apikey":        SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type":  "application/json",
}

def _get(table: str, params: dict | None = None) -> list:
    """GET from PostgREST — returns list of row dicts."""
    p = {"limit": "20000", **(params or {})}
    r = httpx.get(
        f"{SUPABASE_PROJECT_URL}/rest/v1/{table}",
        headers=_HEADERS, params=p, verify=False, timeout=30,
    )
    r.raise_for_status()
    return r.json()

def _post(table: str, data: dict | list, upsert_on: str | None = None) -> None:
    """POST / upsert a row (or list of rows)."""
    headers = {**_HEADERS}
    if upsert_on:
        headers["Prefer"] = f"resolution=ignore-duplicates,return=minimal"
    else:
        headers["Prefer"] = "return=minimal"
    r = httpx.post(
        f"{SUPABASE_PROJECT_URL}/rest/v1/{table}",
        headers=headers, json=data, verify=False, timeout=30,
    )
    # 409 conflict is fine (ON CONFLICT DO NOTHING equivalent)
    if r.status_code not in (200, 201, 204, 409):
        r.raise_for_status()

def _rpc(func: str, params: dict | None = None) -> list:
    """Call a Supabase RPC (stored function)."""
    r = httpx.post(
        f"{SUPABASE_PROJECT_URL}/rest/v1/rpc/{func}",
        headers=_HEADERS, json=params or {}, verify=False, timeout=30,
    )
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
    "alpha1": "α1", "alpha2": "α2",
    "P1": "1st", "P2": "2nd", "P3": "3rd", "P4": "4th",
    "P5": "5th", "P6": "6th", "P7": "7th", "P8": "8th",
}
MAX_DAILY_LOAD = 6

# ─────────────────────────────────────────────────────────────
# OR-TOOLS ENGINE
# ─────────────────────────────────────────────────────────────

BAND_ORDER = {"NURSERY": 0, "LOWER": 1, "MIDDLE": 2, "HIGHER": 3}

def run_substitution(absent_teacher_ids: list, absence_date: date):
    day = absence_date.strftime("%A")

    # ── Load period config from Supabase (source of truth) ───────
    rows = _get("period_config", {"select": "grade_band,period_name,is_active"})
    # active_periods[grade_band] = set of valid period names
    active_periods = defaultdict(set)
    for r in rows:
        if r["is_active"]:
            active_periods[r["grade_band"]].add(r["period_name"])

    # ── Load all teacher metadata ─────────────────────────────
    rows = _get("teachers", {"select": "id,full_name,designation,is_excluded"})
    all_teachers = {r["id"]: r for r in rows}

    rows = _get("subjects", {"select": "id,code"})
    subj_code_map = {r["id"]: r["code"] for r in rows}

    rows = _get("teacher_subjects", {"select": "teacher_id,subject_id"})
    teacher_subjects = defaultdict(set)
    for r in rows:
        teacher_subjects[r["teacher_id"]].add(r["subject_id"])

    # Grade of each class a teacher normally teaches (RPC — needs JOIN + DISTINCT)
    rows = _rpc("get_teacher_grades")
    teacher_grades = defaultdict(set)
    teacher_bands  = defaultdict(set)
    for r in rows:
        teacher_bands[r["teacher_id"]].add(r["grade_band"])
        if r["grade"]:
            teacher_grades[r["teacher_id"]].add(r["grade"])

    rows = _rpc("get_weekly_load")
    weekly_load = {r["teacher_id"]: r["cnt"] for r in rows}

    # ── Who is already busy this day ──────────────────────────
    rows = _get("timetable", {
        "select":     "teacher_id,period_name",
        "day":        f"eq.{day}",
        "teacher_id": "not.is.null",
    })
    busy = defaultdict(set)
    for r in rows:
        busy[r["teacher_id"]].add(r["period_name"])

    daily_count = {tid: len(periods) for tid, periods in busy.items()}

    # ── Find vacant periods for ALL absent teachers ───────────
    vacancies   = []
    no_schedule = []

    for tid in absent_teacher_ids:
        tname = all_teachers.get(tid, {}).get("full_name", "")
        # Embedded join: classes and subjects resolved by PostgREST FK
        rows = _get("timetable", {
            "select":     "class_id,period_name,subject_id,room_type,"
                          "classes(name,grade_band,grade),subjects(code)",
            "teacher_id": f"eq.{tid}",
            "day":        f"eq.{day}",
        })

        if not rows:
            no_schedule.append(tname)
        for r in rows:
            cls = r.get("classes") or {}
            sbj = r.get("subjects") or {}
            gband  = cls.get("grade_band", "")
            period = r["period_name"]
            # Filter using period_config from Supabase — single source of truth
            if active_periods and period not in active_periods.get(gband, {period}):
                continue
            vacancies.append({
                "class_id":            r["class_id"],
                "period_name":         r["period_name"],
                "subject_id":          r["subject_id"],
                "room_type":           r["room_type"],
                "class_name":          cls.get("name", ""),
                "grade_band":          cls.get("grade_band", ""),
                "grade":               cls.get("grade"),
                "subject_code":        sbj.get("code"),
                "absent_teacher_id":   tid,
                "absent_teacher_name": tname,
            })

    if not vacancies:
        return {
            "day": day, "date": absence_date.strftime("%d %B %Y"),
            "report": [],
            "no_schedule": no_schedule,
        }

    # ── Scoring — all 10 rules from the school's PDF ──────────
    def score(cand_id, v):
        s = 0
        vband  = v.get("grade_band", "")
        vgrade = v.get("grade") or 0

        # Rule 7 — same subject (+35)
        if v["subject_id"] and v["subject_id"] in teacher_subjects.get(cand_id, set()):
            s += 35

        # Rule 2 — same stream for class 11/12 (+40)
        if vband == "HIGHER":
            if "HIGHER" in teacher_bands.get(cand_id, set()):
                s += 40

        # Rule 6 — same grade band (+25)
        if vband and vband in teacher_bands.get(cand_id, set()):
            s += 25

        # Rule 3 — grade proximity
        if vgrade and teacher_grades.get(cand_id):
            min_diff = min(abs(vgrade - g) for g in teacher_grades[cand_id])
            if min_diff <= 2:
                s += 20
            elif min_diff <= 4:
                s += 5
            else:
                s -= 15

        # Rule 4 — senior going to junior: slight penalty but allowed
        cand_bands = teacher_bands.get(cand_id, set())
        if cand_bands:
            cand_max   = max(BAND_ORDER.get(b, 0) for b in cand_bands)
            vband_ord  = BAND_ORDER.get(vband, 0)
            if cand_max > vband_ord:
                s -= 5

        # Rule 5 — PT teacher is last resort for grades 10, 11, 12
        cand_subjs   = teacher_subjects.get(cand_id, set())
        is_pt_teacher = any(
            "PT" in (subj_code_map.get(sid, "") or "").upper()
            for sid in cand_subjs
        )
        if is_pt_teacher and vgrade in (10, 11, 12):
            s -= 30

        # Rule 8 — existing daily load penalty
        existing = daily_count.get(cand_id, 0)
        s -= existing * 8

        # Weekly overload penalty
        if weekly_load.get(cand_id, 0) > 35:
            s -= 10

        return s

    # ── Build candidate list per vacancy ─────────────────────
    cands_per = []
    for v in vacancies:
        period   = v["period_name"]
        eligible = []

        for cid, meta in all_teachers.items():
            if meta["is_excluded"]:               continue
            if cid in absent_teacher_ids:         continue
            if period in busy.get(cid, set()):    continue
            if daily_count.get(cid, 0) >= 7:     continue

            eligible.append({
                "id":    cid,
                "name":  meta["full_name"],
                "score": score(cid, v),
            })

        eligible.sort(key=lambda x: x["score"], reverse=True)
        cands_per.append(eligible)

    # ── OR-Tools CP-SAT ──────────────────────────────────────
    model   = cp_model.CpModel()
    n       = len(vacancies)
    all_ids = sorted({c["id"] for cands in cands_per for c in cands})

    if not all_ids:
        return {
            "day": day, "date": absence_date.strftime("%d %B %Y"),
            "report": [{
                "period":        v["period_name"],
                "period_label":  PERIOD_LABEL.get(v["period_name"], v["period_name"]),
                "class_name":    v["class_name"],
                "grade_band":    v.get("grade_band", ""),
                "subject":       v.get("subject_code") or "—",
                "absent_teacher": v["absent_teacher_name"],
                "substitute":    "No substitute available",
                "reason":        "No eligible teacher found",
                "alternatives":  [],
                "score":         0,
            } for v in vacancies],
            "no_schedule": no_schedule,
        }

    # Decision variables
    x = {}
    for i in range(n):
        eid_set = {c["id"] for c in cands_per[i]}
        for j in all_ids:
            x[(i, j)] = model.NewBoolVar(f"x_{i}_{j}")
            if j not in eid_set:
                model.Add(x[(i, j)] == 0)

    # C1: exactly one substitute per vacancy
    for i in range(n):
        if cands_per[i]:
            model.Add(sum(x[(i, j)] for j in all_ids) == 1)
        else:
            model.Add(sum(x[(i, j)] for j in all_ids) == 0)

    # C2: Rule 8 — total daily cap per teacher
    for j in all_ids:
        existing = daily_count.get(j, 0)
        max_subs = max(0, 7 - existing)
        model.Add(sum(x[(i, j)] for i in range(n)) <= max_subs)

    # C3: Load spreading — max 2 substitution periods per teacher today
    for j in all_ids:
        model.Add(sum(x[(i, j)] for i in range(n)) <= 2)

    # Objective: maximise total score − spreading penalty
    score_map = {}
    for i, cands in enumerate(cands_per):
        for c in cands:
            score_map[(i, c["id"])] = max(1, c["score"] + 100)

    used = {}
    for j in all_ids:
        used[j] = model.NewIntVar(0, n, f"used_{j}")
        model.Add(used[j] == sum(x[(i, j)] for i in range(n)))

    model.Maximize(
        sum(score_map.get((i, j), 0) * x[(i, j)]
            for i in range(n) for j in all_ids)
        - sum(25 * used[j] for j in all_ids)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    status = solver.Solve(model)

    # ── Build report ──────────────────────────────────────────
    sub_count = defaultdict(int)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i in range(n):
            for j in all_ids:
                if solver.Value(x[(i, j)]) == 1:
                    sub_count[j] += 1

    report = []
    for i, v in enumerate(vacancies):
        assigned_id    = None
        assigned_name  = "No substitute available"
        assigned_score = 0

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for j in all_ids:
                if solver.Value(x[(i, j)]) == 1:
                    assigned_id    = j
                    assigned_name  = all_teachers[j]["full_name"]
                    assigned_score = next(
                        (c["score"] for c in cands_per[i] if c["id"] == j), 0)
                    break

        # Reason string
        reasons = []
        if assigned_id:
            vband = v.get("grade_band", "")
            vgrade = v.get("grade") or 0

            if v["subject_id"] and v["subject_id"] in teacher_subjects.get(assigned_id, set()):
                reasons.append("Same subject")
            if vband == "HIGHER" and "HIGHER" in teacher_bands.get(assigned_id, set()):
                reasons.append("Same stream (11/12)")
            elif vband and vband in teacher_bands.get(assigned_id, set()):
                reasons.append("Same level")
            else:
                cand_bands = teacher_bands.get(assigned_id, set())
                if cand_bands:
                    cand_max = max(BAND_ORDER.get(b,0) for b in cand_bands)
                    if cand_max > BAND_ORDER.get(vband, 0):
                        reasons.append("Senior teacher to junior class")
            if v.get("room_type") == "SMART_CLASS":
                reasons.append("Smart lab treated as classroom")
            a_subjs = teacher_subjects.get(assigned_id, set())
            is_pt = any("PT" in (subj_code_map.get(sid,"") or "").upper() for sid in a_subjs)
            if is_pt and vgrade in (10, 11, 12):
                reasons.append("PT teacher (last resort)")
        reason = " · ".join(reasons) if reasons else "Best available"

        alternatives = [
            c["name"] for c in cands_per[i] if c["id"] != assigned_id
        ][:3]

        report.append({
            "period"         : v["period_name"],
            "period_label"   : PERIOD_LABEL.get(v["period_name"], v["period_name"]),
            "class_name"     : v["class_name"],
            "grade_band"     : v.get("grade_band", ""),
            "subject"        : v.get("subject_code") or "—",
            "absent_teacher" : v["absent_teacher_name"],
            "substitute"     : assigned_name,
            "reason"         : reason,
            "alternatives"   : alternatives,
            "score"          : assigned_score,
        })

    # Sort by absent teacher then period order
    report.sort(key=lambda r: (
        absent_teacher_ids.index(
            next(tid for tid in absent_teacher_ids
                 if all_teachers.get(tid,{}).get("full_name","") == r["absent_teacher"])
        ) if any(all_teachers.get(tid,{}).get("full_name","") == r["absent_teacher"]
                 for tid in absent_teacher_ids) else 99,
        PERIOD_ORDER.index(r["period"]) if r["period"] in PERIOD_ORDER else 99
    ))

    # Save absences (ignore duplicates)
    for tid in absent_teacher_ids:
        try:
            _post("absences", {
                "teacher_id":   tid,
                "absence_date": absence_date.isoformat(),
                "day_of_week":  day,
            }, upsert_on="teacher_id,absence_date")
        except Exception:
            pass

    return {
        "day"         : day,
        "date"        : absence_date.strftime("%d %B %Y"),
        "weekday"     : day,
        "report"      : report,
        "no_schedule" : no_schedule,
    }

# ─────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────

@app.get("/api/teachers")
def get_teachers():
    rows = _get("teachers", {
        "select":       "id,full_name,designation",
        "is_excluded":  "eq.false",
        "order":        "full_name.asc",
    })
    return rows

class ReportRequest(BaseModel):
    absent_teacher_ids: List[int]
    absence_date: str   # YYYY-MM-DD

@app.post("/api/generate-report")
def generate_report(req: ReportRequest):
    try:
        d      = date.fromisoformat(req.absence_date)
        result = run_substitution(req.absent_teacher_ids, d)
        return JSONResponse(content=result)
    except Exception as e:
        import traceback
        return JSONResponse(content={"error": str(e), "detail": traceback.format_exc()}, status_code=500)

@app.get("/api/health")
def health():
    try:
        rows = _get("teachers", {"select": "id", "limit": "1"})
        return {"status": "ok", "db": "connected", "teachers_sample": len(rows)}
    except Exception as e:
        return {"status": "error", "db": str(e)}

# ─────────────────────────────────────────────────────────────
# HTML UI
# ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Teacher Substitution System — Gyan Niketan</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f4f8;color:#1a202c;min-height:100vh}

/* Header */
.hdr{background:#0d2b55;color:#fff;padding:16px 32px;display:flex;align-items:center;gap:14px;
     box-shadow:0 2px 8px rgba(0,0,0,.25)}
.hdr-icon{font-size:30px}
.hdr h1{font-size:20px;font-weight:700}
.hdr p{font-size:12px;color:#94a3b8;margin-top:2px}

/* Layout */
.wrap{max-width:1050px;margin:28px auto;padding:0 20px}

/* Card */
.card{background:#fff;border-radius:12px;box-shadow:0 1px 5px rgba(0,0,0,.08);
      padding:26px;margin-bottom:22px}
.card-title{font-size:15px;font-weight:700;color:#0d2b55;padding-bottom:12px;
            border-bottom:2px solid #e2e8f0;margin-bottom:20px;
            display:flex;align-items:center;gap:8px}

/* Form */
.form-row{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-end}
.fg{display:flex;flex-direction:column;gap:6px;flex:1;min-width:200px}
label{font-size:13px;font-weight:600;color:#475569}
input[type=date]{padding:9px 12px;border:1.5px solid #cbd5e1;border-radius:8px;
                 font-size:14px;outline:none;transition:.2s}
input[type=date]:focus{border-color:#1a56a4}

/* Search */
.sw{position:relative}
#ts{width:100%;padding:9px 12px;border:1.5px solid #cbd5e1;border-radius:8px;
    font-size:14px;outline:none;transition:.2s}
#ts:focus{border-color:#1a56a4}
#dd{position:absolute;top:100%;left:0;right:0;background:#fff;border:1.5px solid #cbd5e1;
    border-top:none;border-radius:0 0 8px 8px;max-height:220px;overflow-y:auto;
    z-index:99;display:none;box-shadow:0 4px 12px rgba(0,0,0,.1)}
.ddi{padding:9px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid #f8fafc}
.ddi:hover{background:#eff6ff}

/* Tags */
.tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px;min-height:34px}
.tag{background:#dbeafe;color:#1e40af;padding:5px 12px;border-radius:20px;
     font-size:13px;font-weight:600;display:flex;align-items:center;gap:6px}
.tag .x{cursor:pointer;font-size:15px;color:#93c5fd;font-weight:700;line-height:1}
.tag .x:hover{color:#1e40af}

/* Button */
.btn{padding:10px 28px;background:#0d2b55;color:#fff;border:none;border-radius:8px;
     font-size:14px;font-weight:700;cursor:pointer;transition:.2s;white-space:nowrap}
.btn:hover{background:#1a56a4}
.btn:disabled{background:#94a3b8;cursor:not-allowed}
.btn-print{background:#1a6b3c;padding:8px 20px;font-size:13px}
.btn-print:hover{background:#15803d}
.btn-back{background:#475569;padding:8px 18px;font-size:13px}
.btn-back:hover{background:#334155}

/* Spinner */
.spin{display:none;text-align:center;padding:48px;color:#64748b;font-size:14px}
.spin:before{content:"";display:block;width:38px;height:38px;border:4px solid #e2e8f0;
             border-top-color:#0d2b55;border-radius:50%;animation:spin .8s linear infinite;
             margin:0 auto 14px}
@keyframes spin{to{transform:rotate(360deg)}}

/* Error */
.err{background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;padding:14px 16px;
     color:#dc2626;font-size:13px;display:none;margin-bottom:16px}

/* Report */
#rpt{display:none}
.rpt-hdr{display:flex;justify-content:space-between;align-items:flex-start;
         margin-bottom:16px;flex-wrap:wrap;gap:12px}
.rpt-meta strong{color:#0d2b55;font-size:16px;display:block;margin-bottom:3px}
.rpt-meta span{font-size:13px;color:#64748b}
.btn-row{display:flex;gap:10px}

/* Badges */
.badges{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.bdg{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:700}
.bdg-b{background:#dbeafe;color:#1e40af}
.bdg-g{background:#dcfce7;color:#166534}
.bdg-y{background:#fef3c7;color:#92400e}
.bdg-r{background:#fee2e2;color:#991b1b}

/* Table */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#0d2b55;color:#fff;padding:10px 13px;text-align:left;
   font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
td{padding:10px 13px;border-bottom:1px solid #f1f5f9;vertical-align:top}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8fafc}
tr:nth-child(even) td{background:#fafafa}
tr:nth-child(even):hover td{background:#f1f5f9}

/* Group header */
.grp td{background:#fef6e7!important;color:#92400e;font-weight:700;
        font-size:12px;padding:7px 13px;border-bottom:1px solid #fde68a}

/* Cell styles */
.pbdg{background:#0d2b55;color:#fff;padding:3px 9px;border-radius:5px;
      font-size:11px;font-weight:700;display:inline-block}
.cbdg{background:#e0f2fe;color:#0369a1;padding:3px 9px;border-radius:5px;
      font-size:11px;font-weight:700}
.gb{font-size:11px;color:#94a3b8;margin-top:2px}
.sub-ok{font-weight:700;color:#1a6b3c}
.sub-no{font-weight:700;color:#dc2626}
.rsn{color:#64748b;font-size:12px}
.alt{color:#94a3b8;font-size:11px;margin-top:3px}
.absent{color:#dc2626;font-size:12px}

/* Footer note */
.fnote{margin-top:18px;font-size:11px;color:#94a3b8;
       border-top:1px solid #f1f5f9;padding-top:12px}

/* Print */
@media print{
  body{background:#fff}
  .hdr{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .no-print{display:none!important}
  .card{box-shadow:none;border:1px solid #e2e8f0;break-inside:avoid}
  th{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .grp td{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .pbdg{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  #rpt{display:block!important}
  #inputCard{display:none}
  .err{display:none}
}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-icon">🏫</div>
  <div>
    <h1>Teacher Substitution System</h1>
    <p>Gyan Niketan Public School &nbsp;·&nbsp; Session 2026–27</p>
  </div>
</div>

<div class="wrap">

  <!-- Input card -->
  <div class="card" id="inputCard">
    <div class="card-title">📋 Mark Absent Teachers &amp; Generate Report</div>

    <div class="form-row">
      <div class="fg" style="max-width:200px">
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

  <!-- Error -->
  <div class="err" id="err"></div>

  <!-- Spinner -->
  <div class="spin" id="spin">Running OR-Tools optimizer…</div>

  <!-- Report -->
  <div class="card" id="rpt">
    <div class="rpt-hdr">
      <div class="rpt-meta">
        <strong id="rTitle"></strong>
        <span id="rMeta"></span>
      </div>
      <div class="btn-row no-print">
        <button class="btn btn-print" onclick="window.print()">🖨️ Print</button>
        <button class="btn btn-back"  onclick="reset()">← New</button>
      </div>
    </div>

    <div class="badges" id="badges"></div>
    <div id="noSchedWarn"></div>

    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Period</th>
            <th>Class</th>
            <th>Subject</th>
            <th>Absent Teacher</th>
            <th>Substitute Teacher</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>

    <div class="fnote">
      Generated by Teacher Substitution System &nbsp;·&nbsp;
      OR-Tools CP-SAT Optimizer (10 Rules) &nbsp;·&nbsp; <span id="gt"></span>
    </div>
  </div>

</div>

<script>
let allTeachers = [], selected = [];

function fmtDate(d){
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}

async function init(){
  try{
    const r = await fetch('/api/teachers');
    allTeachers = await r.json();
  } catch(e){ showErr('Cannot connect to server. Is app.py running?'); }

  const now      = new Date();
  const hour     = now.getHours();             // 0-23
  const after5pm = hour >= 17;                 // 5:00 PM = 17:00

  const today    = new Date(now); today.setHours(0,0,0,0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate()+1);

  const di = document.getElementById('di');

  if(after5pm){
    // After 5 PM — only tomorrow is selectable
    di.min   = fmtDate(tomorrow);
    di.max   = fmtDate(tomorrow);
    di.value = fmtDate(tomorrow);
  } else {
    // Before 5 PM — today and tomorrow are selectable, default to today
    di.min   = fmtDate(today);
    di.max   = fmtDate(tomorrow);
    di.value = fmtDate(today);
  }
}

// ── Search dropdown ───────────────────────────────────────
const ts = document.getElementById('ts');
const dd = document.getElementById('dd');

ts.addEventListener('input', function(){
  const q = this.value.toLowerCase().trim();
  dd.innerHTML = '';
  if(!q){ dd.style.display='none'; return; }
  const m = allTeachers.filter(t =>
    t.full_name.toLowerCase().includes(q) && !selected.find(s=>s.id===t.id)
  ).slice(0,12);
  if(!m.length){ dd.style.display='none'; return; }
  m.forEach(t=>{
    const d=document.createElement('div');
    d.className='ddi'; d.textContent=t.full_name;
    d.onclick=()=>pick(t);
    dd.appendChild(d);
  });
  dd.style.display='block';
});

document.addEventListener('click', e=>{
  if(!e.target.closest('.sw')) dd.style.display='none';
});

function pick(t){
  if(selected.find(s=>s.id===t.id)) return;
  selected.push(t); renderTags();
  ts.value=''; dd.style.display='none';
}

function remove(id){
  selected = selected.filter(t=>t.id!==id); renderTags();
}

function renderTags(){
  const c = document.getElementById('tags');
  c.innerHTML='';
  selected.forEach(t=>{
    const el = document.createElement('div');
    el.className='tag';
    el.innerHTML=`${t.full_name} <span class="x" onclick="remove(${t.id})">×</span>`;
    c.appendChild(el);
  });
}

// ── Generate ──────────────────────────────────────────────
async function generate(){
  const dv = document.getElementById('di').value;
  if(!dv){ showErr('Please select a date.'); return; }
  if(!selected.length){ showErr('Please select at least one absent teacher.'); return; }
  hideErr();
  document.getElementById('spin').style.display='block';
  document.getElementById('rpt').style.display='none';
  document.getElementById('genBtn').disabled=true;
  try{
    const r = await fetch('/api/generate-report',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({absent_teacher_ids:selected.map(t=>t.id), absence_date:dv})
    });
    const data = await r.json();
    if(data.error){ showErr(data.error); return; }
    render(data);
  } catch(e){ showErr('Server error: '+e.message); }
  finally{
    document.getElementById('spin').style.display='none';
    document.getElementById('genBtn').disabled=false;
  }
}

// ── Render report ─────────────────────────────────────────
function render(data){
  const rep = data.report;
  document.getElementById('rTitle').textContent =
    'Substitution Report — '+data.date+' ('+data.weekday+')';
  document.getElementById('rMeta').textContent =
    'Absent: '+selected.map(t=>t.full_name).join(', ');

  const covered   = rep.filter(r=>r.substitute!=='No substitute available').length;
  const uncovered = rep.length - covered;

  document.getElementById('badges').innerHTML =
    `<span class="bdg bdg-b">📚 ${rep.length} Period${rep.length!==1?'s':''} to Cover</span>`+
    `<span class="bdg bdg-g">✅ ${covered} Covered</span>`+
    (uncovered?`<span class="bdg bdg-y">⚠️ ${uncovered} Uncovered</span>`:'')+
    `<span class="bdg bdg-b">👥 ${selected.length} Absent</span>`;

  const ns = data.no_schedule || [];
  const nw = document.getElementById('noSchedWarn');
  if(ns.length){
    nw.innerHTML = `<div style="background:#fefce8;border:1px solid #fde047;border-radius:8px;
      padding:10px 14px;margin-bottom:14px;font-size:13px;color:#92400e">
      ℹ️ <b>No timetable found on ${data.weekday} for:</b> ${ns.join(', ')}
      — They may have no classes scheduled on this day, or their timetable was not loaded.
    </div>`;
  } else { nw.innerHTML=''; }

  const groups = {};
  const order  = [];
  rep.forEach(r=>{
    if(!groups[r.absent_teacher]){ groups[r.absent_teacher]=[]; order.push(r.absent_teacher); }
    groups[r.absent_teacher].push(r);
  });
  ns.forEach(n=>{ if(!groups[n]){ groups[n]=[]; order.push(n); } });

  const tbody = document.getElementById('tbody');
  tbody.innerHTML='';
  order.forEach(teacher=>{
    const rows = groups[teacher]||[];
    const gh=document.createElement('tr');
    gh.className='grp';
    gh.innerHTML=`<td colspan="6">🔴 &nbsp;Absent: ${teacher}` +
      (rows.length===0?' &nbsp;<span style="font-weight:normal;color:#b45309">(No classes on this day)</span>':'')+
      `</td>`;
    tbody.appendChild(gh);

    rows.forEach(r=>{
      const no = r.substitute==='No substitute available';
      const alt= r.alternatives.length ? 'Also: '+r.alternatives.join(' / ') : '';
      const tr=document.createElement('tr');
      tr.innerHTML=
        `<td><span class="pbdg">${r.period_label}</span></td>`+
        `<td><span class="cbdg">${r.class_name}</span><div class="gb">${r.grade_band}</div></td>`+
        `<td><b>${r.subject}</b></td>`+
        `<td><span class="absent">${r.absent_teacher}</span></td>`+
        `<td><span class="${no?'sub-no':'sub-ok'}">${r.substitute}</span>`+
             `${alt?`<div class="alt">${alt}</div>`:''}</td>`+
        `<td><span class="rsn">${r.reason}</span></td>`;
      tbody.appendChild(tr);
    });
  });

  document.getElementById('gt').textContent='Generated at '+new Date().toLocaleTimeString();
  document.getElementById('rpt').style.display='block';
  document.getElementById('rpt').scrollIntoView({behavior:'smooth'});
}

function showErr(m){
  const b=document.getElementById('err');
  b.textContent='⚠️  '+m; b.style.display='block';
  document.getElementById('spin').style.display='none';
}
function hideErr(){ document.getElementById('err').style.display='none'; }
function reset(){
  document.getElementById('rpt').style.display='none';
  document.getElementById('inputCard').scrollIntoView({behavior:'smooth'});
}

init();
</script>
</body>
</html>
"""

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

    print("=" * 52)
    print("  Teacher Substitution System")
    print("  Gyan Niketan Public School — 2026-27")
    print("=" * 52)
    print(f"  This PC    :  http://localhost:8000")
    print(f"  School LAN :  http://{local_ip}:8000")
    print("  Press Ctrl+C to stop.")
    print("=" * 52)

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
