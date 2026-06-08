"""
generate_import_csvs.py
Generates flat CSVs that can be imported directly into Supabase
via the Table Editor > Import CSV feature.

Output folder: CSV\supabase_import\
  1. teachers.csv
  2. subjects.csv
  3. classes.csv
  4. timetable_import.csv   (uses teacher_no + class_name — needs ETL for FK)

NOTE: Because Supabase CSV import does not resolve foreign keys automatically,
we generate a self-contained script approach:
  - teachers.csv       → import to teachers table
  - subjects.csv       → import to subjects table
  - classes.csv        → import to classes table
  - timetable_flat.csv → Teacher_no, Class, Day, Period, Subject, Room_type, Lab_section
                         (human-readable, for reference)
  - seed_data.sql      → Full INSERT SQL with all data — paste into SQL Editor
"""

import csv, os, re

BASE    = os.path.join(os.path.dirname(__file__), "CSV")
OUT_DIR = os.path.join(BASE, "supabase_import")
os.makedirs(OUT_DIR, exist_ok=True)

F_TEACHERS  = os.path.join(BASE, "teacher_master.csv")
F_TIMETABLE = os.path.join(BASE, "master_timetable.csv")
F_GK_MSC    = os.path.join(BASE, "gk_msc_master.csv")
F_CT        = os.path.join(BASE, "CT 2026-27.csv")

ALL_PERIODS = ["alpha1","alpha2","P1","P2","P3","P4","P5","P6","P7","P8"]

def grade_band(cls):
    cls = cls.strip().upper()
    m = re.match(r"^(\d+)", cls)
    if m:
        g = int(m.group(1))
        if g <= 5:  return "LOWER"
        if g <= 10: return "MIDDLE"
        return "HIGHER"
    if any(k in cls for k in ("NURSERY","LKG","UKG")): return "NURSERY"
    return "UNKNOWN"

def esc(v):
    if v is None: return "NULL"
    v = str(v).replace("'", "''")
    return f"'{v}'"

def b(v):
    return "TRUE" if v else "FALSE"

# ── Load source data ──────────────────────────────────────────────────────────
teachers = []
with open(F_TEACHERS, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        excl = r.get("Is_excluded","NO").strip().upper() in ("YES","1","TRUE")
        teachers.append({
            "teacher_no":   r["Teacher_no"].strip(),
            "full_name":    r["Full_name"].strip(),
            "subject":      r.get("Subject","").strip(),
            "designation":  r.get("Designation","TEACHER").strip(),
            "abbreviation": r.get("Abbreviation","").strip(),
            "is_excluded":  excl,
        })

timetable_rows = []
with open(F_TIMETABLE, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        timetable_rows.append({
            "teacher_no":   r["Teacher_no"].strip(),
            "subject":      r["Subject"].strip().upper(),
            "day":          r["Day"].strip(),
            "period":       r["Period"].strip(),
            "class_name":   r["Class"].strip().upper(),
            "is_practical": r["Is_practical"].strip().lower() == "yes",
            "room_type":    r["Room_type"].strip(),
            "lab_section":  r.get("Lab_section","").strip() or None,
        })

gk_msc_rows = []
with open(F_GK_MSC, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        gk_msc_rows.append({
            "class_name":    r["Class"].strip().upper(),
            "gk_teacher_no": r["GK_Teacher_no"].strip(),
            "msc_teacher_no":r["MSC_Teacher_no"].strip(),
        })

# Build lookup maps
tno_to_id   = {t["teacher_no"]: i+1 for i, t in enumerate(teachers)}
subject_set = sorted(set(
    [t["subject"].upper() for t in teachers if t["subject"]] +
    [r["subject"] for r in timetable_rows if r["subject"]]
) - {""})
subj_to_id  = {s: i+1 for i, s in enumerate(subject_set)}

all_class_names = sorted(set(
    [r["class_name"] for r in timetable_rows] +
    [r["class_name"] for r in gk_msc_rows]
))
cls_list = []
for cname in all_class_names:
    if not cname: continue
    m = re.match(r"^(\d+)([A-Z]*)$", cname)
    grade   = int(m.group(1)) if m else None
    section = m.group(2)      if m else None
    cls_list.append({"name": cname, "grade": grade, "section": section, "band": grade_band(cname)})
cls_to_id = {c["name"]: i+1 for i, c in enumerate(cls_list)}

print(f"Teachers : {len(teachers)}")
print(f"Subjects : {len(subject_set)}")
print(f"Classes  : {len(cls_list)}")
print(f"Timetable: {len(timetable_rows)}")
print(f"GK/MSC   : {len(gk_msc_rows)}")

# ── Build seed_data.sql ───────────────────────────────────────────────────────
lines = []
lines.append("-- ============================================================")
lines.append("-- Gyan Niketan Public School — Seed Data")
lines.append("-- Paste into Supabase SQL Editor and Run")
lines.append("-- IMPORTANT: Run schema.sql first, then this file")
lines.append("-- ============================================================\n")

# subjects
lines.append("-- 1. SUBJECTS")
lines.append("INSERT INTO subjects (id, code) VALUES")
vals = [f"  ({i+1}, {esc(s)})" for i, s in enumerate(subject_set)]
lines.append(",\n".join(vals) + ";")
lines.append("SELECT setval('subjects_id_seq', (SELECT MAX(id) FROM subjects));\n")

# teachers
lines.append("-- 2. TEACHERS")
lines.append("INSERT INTO teachers (id, teacher_no, full_name, subject, designation, abbreviation, is_excluded) VALUES")
vals = []
for i, t in enumerate(teachers):
    vals.append(f"  ({i+1}, {esc(t['teacher_no'])}, {esc(t['full_name'])}, {esc(t['subject'])}, {esc(t['designation'])}, {esc(t['abbreviation'])}, {b(t['is_excluded'])})")
lines.append(",\n".join(vals) + ";")
lines.append("SELECT setval('teachers_id_seq', (SELECT MAX(id) FROM teachers));\n")

# teacher_subjects
lines.append("-- 3. TEACHER_SUBJECTS")
lines.append("INSERT INTO teacher_subjects (teacher_id, subject_id, is_primary) VALUES")
vals = []
for i, t in enumerate(teachers):
    sid = subj_to_id.get(t["subject"].upper())
    if sid:
        vals.append(f"  ({i+1}, {sid}, TRUE)")
lines.append(",\n".join(vals) + ";\n")

# classes
lines.append("-- 4. CLASSES")
lines.append("INSERT INTO classes (id, name, grade, section, grade_band) VALUES")
vals = []
for i, c in enumerate(cls_list):
    grade   = str(c["grade"]) if c["grade"] is not None else "NULL"
    section = esc(c["section"]) if c["section"] else "NULL"
    vals.append(f"  ({i+1}, {esc(c['name'])}, {grade}, {section}, {esc(c['band'])})")
lines.append(",\n".join(vals) + ";")
lines.append("SELECT setval('classes_id_seq', (SELECT MAX(id) FROM classes));\n")

# period_config
lines.append("-- 5. PERIOD_CONFIG")
lines.append("INSERT INTO period_config (grade_band, period_name, period_order, is_alpha, is_active) VALUES")
vals = []
for band in ("NURSERY","LOWER","MIDDLE","HIGHER"):
    for order, pname in enumerate(ALL_PERIODS, 1):
        is_alpha = pname in ("alpha1","alpha2")
        if pname in ("alpha1","alpha2"):   active = band == "HIGHER"
        elif pname in ("P5","P6","P7","P8"): active = band != "HIGHER"
        else: active = True
        vals.append(f"  ({esc(band)}, {esc(pname)}, {order}, {b(is_alpha)}, {b(active)})")
lines.append(",\n".join(vals) + ";\n")

# labs
lines.append("-- 6. LABS")
lines.append("INSERT INTO labs (name, lab_type, block, sub_type) VALUES")
lines.append("  ('Smart Class Block A', 'SMART_CLASS', 'A', 'JUNIOR'),")
lines.append("  ('Smart Class Block B', 'SMART_CLASS', 'B', 'PRIMARY'),")
lines.append("  ('Smart Class Block C', 'SMART_CLASS', 'C', 'SENIOR'),")
lines.append("  ('Robotics Lab Junior', 'ROBOTICS', NULL, 'JUNIOR'),")
lines.append("  ('Robotics Lab Senior', 'ROBOTICS', NULL, 'SENIOR');\n")

# timetable — split into chunks of 500 to avoid SQL size limits
lines.append("-- 7. TIMETABLE (4771 rows — inserted in chunks)")
tt_vals = []
for r in timetable_rows:
    cid = cls_to_id.get(r["class_name"])
    tid = tno_to_id.get(r["teacher_no"])
    sid = subj_to_id.get(r["subject"]) if r["subject"] else None
    if not cid: continue
    lab = esc(r["lab_section"]) if r["lab_section"] else "NULL"
    sid_s = str(sid) if sid else "NULL"
    tid_s = str(tid) if tid else "NULL"
    tt_vals.append(f"  ({cid}, {tid_s}, {sid_s}, {esc(r['day'])}, {esc(r['period'])}, {esc(r['room_type'])}, {b(r['is_practical'])}, {lab})")

CHUNK = 500
for i in range(0, len(tt_vals), CHUNK):
    chunk = tt_vals[i:i+CHUNK]
    lines.append("INSERT INTO timetable (class_id, teacher_id, subject_id, day, period_name, room_type, is_practical, lab_section) VALUES")
    lines.append(",\n".join(chunk) + ";")
lines.append("")

# gk_msc
lines.append("-- 8. GK_MSC")
lines.append("INSERT INTO gk_msc (class_id, gk_teacher_id, msc_teacher_id) VALUES")
vals = []
for r in gk_msc_rows:
    cid     = cls_to_id.get(r["class_name"])
    gk_tid  = tno_to_id.get(r["gk_teacher_no"])
    msc_tid = tno_to_id.get(r["msc_teacher_no"])
    if cid:
        vals.append(f"  ({cid}, {gk_tid or 'NULL'}, {msc_tid or 'NULL'})")
lines.append(",\n".join(vals) + ";\n")

lines.append("-- ============================================================")
lines.append("-- Done! All tables seeded.")
lines.append("-- ============================================================")

sql_out = os.path.join(OUT_DIR, "seed_data.sql")
with open(sql_out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

size_kb = os.path.getsize(sql_out) // 1024
print(f"\nGenerated: {sql_out}")
print(f"File size: {size_kb} KB")
print(f"Timetable rows in SQL: {len(tt_vals)}")
print("\nNext steps:")
print("  1. Open Supabase SQL Editor")
print("  2. Run schema.sql")
print("  3. Run seed_data.sql")
print("  Done!")
