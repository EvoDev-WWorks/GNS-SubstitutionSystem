"""
ETL — Push clean CSV data into Supabase (PostgreSQL)
Run once:  python etl_supabase.py

Source files (all keyed by Teacher_no):
  CSV\teacher_master.csv      -> teachers table
  CSV\master_timetable.csv    -> timetable table
  CSV\gk_msc_master.csv       -> gk_msc table
  CSV\CT 2026-27.csv          -> class_teachers table
"""

import os, csv, re, difflib
import psycopg2
from psycopg2.extras import execute_values

# ── CONNECTION ────────────────────────────────────────────────────────────────
SUPABASE_URL = "postgresql://postgres:Evodoc%402026@db.dbwqompqjduzstwxzijm.supabase.co:5432/postgres"

CSV_DIR = os.path.join(os.path.dirname(__file__), "CSV")

F_TEACHERS  = os.path.join(CSV_DIR, "teacher_master.csv")
F_TIMETABLE = os.path.join(CSV_DIR, "master_timetable.csv")
F_GK_MSC    = os.path.join(CSV_DIR, "gk_msc_master.csv")
F_CT        = os.path.join(CSV_DIR, "CT 2026-27.csv")

# ── SCHEMA ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS subjects (
    id   SERIAL PRIMARY KEY,
    code TEXT   UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id           SERIAL PRIMARY KEY,
    teacher_no   TEXT   UNIQUE NOT NULL,
    full_name    TEXT   NOT NULL,
    subject      TEXT,
    designation  TEXT   DEFAULT 'TEACHER',
    abbreviation TEXT,
    is_excluded  BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS teacher_subjects (
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (teacher_id, subject_id)
);

CREATE TABLE IF NOT EXISTS classes (
    id         SERIAL PRIMARY KEY,
    name       TEXT   UNIQUE NOT NULL,
    grade      INTEGER,
    section    TEXT,
    grade_band TEXT
);

CREATE TABLE IF NOT EXISTS class_teachers (
    class_id   INTEGER REFERENCES classes(id)  ON DELETE CASCADE,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    PRIMARY KEY (class_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS period_config (
    id           SERIAL PRIMARY KEY,
    grade_band   TEXT NOT NULL,
    period_name  TEXT NOT NULL,
    period_order INTEGER NOT NULL,
    is_alpha     BOOLEAN DEFAULT FALSE,
    is_active    BOOLEAN DEFAULT TRUE,
    UNIQUE (grade_band, period_name)
);

CREATE TABLE IF NOT EXISTS labs (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    lab_type TEXT NOT NULL,
    block    TEXT,
    sub_type TEXT
);

CREATE TABLE IF NOT EXISTS timetable (
    id           SERIAL PRIMARY KEY,
    class_id     INTEGER REFERENCES classes(id)  ON DELETE CASCADE,
    teacher_id   INTEGER REFERENCES teachers(id),
    subject_id   INTEGER REFERENCES subjects(id),
    day          TEXT NOT NULL,
    period_name  TEXT NOT NULL,
    room_type    TEXT DEFAULT 'CLASSROOM',
    is_practical BOOLEAN DEFAULT FALSE,
    lab_section  TEXT,
    UNIQUE (teacher_id, day, period_name, room_type)
);

CREATE TABLE IF NOT EXISTS gk_msc (
    id             SERIAL PRIMARY KEY,
    class_id       INTEGER REFERENCES classes(id) ON DELETE CASCADE,
    gk_teacher_id  INTEGER REFERENCES teachers(id),
    msc_teacher_id INTEGER REFERENCES teachers(id),
    UNIQUE (class_id)
);

CREATE TABLE IF NOT EXISTS absences (
    id           SERIAL PRIMARY KEY,
    teacher_id   INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    absence_date DATE    NOT NULL,
    day_of_week  TEXT    NOT NULL,
    reason       TEXT,
    marked_by    TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (teacher_id, absence_date)
);

CREATE TABLE IF NOT EXISTS substitutions (
    id                    SERIAL PRIMARY KEY,
    absence_id            INTEGER REFERENCES absences(id) ON DELETE CASCADE,
    class_id              INTEGER REFERENCES classes(id),
    period_name           TEXT NOT NULL,
    absent_teacher_id     INTEGER REFERENCES teachers(id),
    substitute_teacher_id INTEGER REFERENCES teachers(id),
    subject_id            INTEGER REFERENCES subjects(id),
    room_type             TEXT DEFAULT 'CLASSROOM',
    score                 INTEGER DEFAULT 0,
    reason                TEXT,
    status                TEXT DEFAULT 'SUGGESTED',
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_load (
    id                   SERIAL PRIMARY KEY,
    teacher_id           INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    load_date            DATE NOT NULL,
    regular_classes      INTEGER DEFAULT 0,
    substitution_classes INTEGER DEFAULT 0,
    UNIQUE (teacher_id, load_date)
);
"""

DROP_SQL = """
DROP TABLE IF EXISTS daily_load       CASCADE;
DROP TABLE IF EXISTS substitutions    CASCADE;
DROP TABLE IF EXISTS absences         CASCADE;
DROP TABLE IF EXISTS gk_msc          CASCADE;
DROP TABLE IF EXISTS timetable        CASCADE;
DROP TABLE IF EXISTS labs             CASCADE;
DROP TABLE IF EXISTS period_config    CASCADE;
DROP TABLE IF EXISTS class_teachers   CASCADE;
DROP TABLE IF EXISTS classes          CASCADE;
DROP TABLE IF EXISTS teacher_subjects CASCADE;
DROP TABLE IF EXISTS teachers         CASCADE;
DROP TABLE IF EXISTS subjects         CASCADE;
"""

ALL_PERIODS = ["alpha1","alpha2","P1","P2","P3","P4","P5","P6","P7","P8"]

def grade_band(cls):
    cls = cls.strip().upper()
    m = re.match(r"^(\d+)", cls)
    if m:
        g = int(m.group(1))
        if g <= 5:  return "LOWER"
        if g <= 10: return "MIDDLE"
        return "HIGHER"
    if any(k in cls for k in ("NURSERY","LKG","UKG")):
        return "NURSERY"
    return "UNKNOWN"

def period_config_rows():
    rows = []
    for band in ("NURSERY","LOWER","MIDDLE","HIGHER"):
        for order, pname in enumerate(ALL_PERIODS, 1):
            is_alpha = pname in ("alpha1","alpha2")
            if pname in ("alpha1","alpha2"):
                active = band == "HIGHER"
            elif pname in ("P5","P6","P7","P8"):
                active = band != "HIGHER"
            else:
                active = True
            rows.append((band, pname, order, is_alpha, active))
    return rows

# ── LOADERS ───────────────────────────────────────────────────────────────────

def load_teachers():
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
    return teachers

def load_master_timetable():
    rows = []
    with open(F_TIMETABLE, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "teacher_no":   r["Teacher_no"].strip(),
                "subject":      r["Subject"].strip().upper(),
                "day":          r["Day"].strip(),
                "period":       r["Period"].strip(),
                "class_name":   r["Class"].strip().upper(),
                "is_practical": r["Is_practical"].strip().lower() == "yes",
                "room_type":    r["Room_type"].strip(),
                "lab_section":  r.get("Lab_section","").strip(),
            })
    return rows

def load_gk_msc():
    rows = []
    with open(F_GK_MSC, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({
                "class_name":    r["Class"].strip().upper(),
                "gk_teacher_no": r["GK_Teacher_no"].strip(),
                "msc_teacher_no":r["MSC_Teacher_no"].strip(),
            })
    return rows

def load_ct(tch_by_name):
    ct_rows = []
    all_names = list(tch_by_name.keys())
    with open(F_CT, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cls  = r.get("CLASS_SECTION","").strip().upper()
            name = r.get("CLASS_TEACHER_NAME","").strip()
            if not cls or not name: continue
            tid = tch_by_name.get(name.upper())
            if not tid:
                matches = difflib.get_close_matches(name.upper(), all_names, n=1, cutoff=0.75)
                if matches:
                    tid = tch_by_name[matches[0]]
            ct_rows.append({"class_name": cls, "teacher_id": tid})
    return ct_rows

# ── SEED ─────────────────────────────────────────────────────────────────────

def seed(cur, teachers, timetable_rows, gk_msc_rows, ct_raw):

    # ── Subjects ──────────────────────────────────────────────────────────────
    print("Seeding subjects...")
    subject_codes = set(t["subject"].upper() for t in teachers if t["subject"])
    subject_codes.update(r["subject"] for r in timetable_rows if r["subject"])
    subject_codes.discard("")
    execute_values(cur,
        "INSERT INTO subjects (code) VALUES %s ON CONFLICT (code) DO NOTHING",
        [(s,) for s in sorted(subject_codes)])
    cur.execute("SELECT id, code FROM subjects")
    subj_map = {r[1]: r[0] for r in cur.fetchall()}
    print(f"  {len(subj_map)} subjects")

    # ── Teachers ──────────────────────────────────────────────────────────────
    print("Seeding teachers...")
    execute_values(cur,
        """INSERT INTO teachers (teacher_no, full_name, subject, designation, abbreviation, is_excluded)
           VALUES %s ON CONFLICT (teacher_no) DO NOTHING""",
        [(t["teacher_no"], t["full_name"], t["subject"],
          t["designation"], t["abbreviation"], t["is_excluded"]) for t in teachers])
    cur.execute("SELECT id, teacher_no, full_name FROM teachers")
    rows = cur.fetchall()
    tno_map      = {r[1]: r[0] for r in rows}   # T001 -> db id
    tch_by_name  = {r[2].upper(): r[0] for r in rows}
    print(f"  {len(tno_map)} teachers")

    # ── Teacher → Subject links ───────────────────────────────────────────────
    print("Seeding teacher_subjects...")
    ts_rows = []
    for t in teachers:
        tid = tno_map.get(t["teacher_no"])
        sid = subj_map.get(t["subject"].upper()) if t["subject"] else None
        if tid and sid:
            ts_rows.append((tid, sid, True))
    if ts_rows:
        execute_values(cur,
            "INSERT INTO teacher_subjects (teacher_id, subject_id, is_primary) VALUES %s "
            "ON CONFLICT DO NOTHING", ts_rows)
    print(f"  {len(ts_rows)} links")

    # ── Classes ───────────────────────────────────────────────────────────────
    print("Seeding classes...")
    all_class_names = set(r["class_name"] for r in timetable_rows)
    all_class_names.update(r["class_name"] for r in gk_msc_rows)
    all_class_names.update(r["class_name"] for r in ct_raw)
    cls_rows = []
    for cname in sorted(all_class_names):
        if not cname: continue
        m = re.match(r"^(\d+)([A-Z]*)$", cname.upper())
        grade   = int(m.group(1)) if m else None
        section = m.group(2)      if m else None
        cls_rows.append((cname.upper(), grade, section, grade_band(cname)))
    execute_values(cur,
        "INSERT INTO classes (name, grade, section, grade_band) VALUES %s "
        "ON CONFLICT (name) DO NOTHING", cls_rows)
    cur.execute("SELECT id, name FROM classes")
    cls_map = {r[1]: r[0] for r in cur.fetchall()}
    print(f"  {len(cls_map)} classes")

    # ── Class teachers ────────────────────────────────────────────────────────
    print("Seeding class_teachers...")
    ct_rows, ct_skip = [], 0
    for r in ct_raw:
        cid = cls_map.get(r["class_name"])
        tid = r["teacher_id"]
        if cid and tid:
            ct_rows.append((cid, tid))
        else:
            ct_skip += 1
    if ct_rows:
        execute_values(cur,
            "INSERT INTO class_teachers (class_id, teacher_id) VALUES %s "
            "ON CONFLICT DO NOTHING", ct_rows)
    print(f"  {len(ct_rows)} links  ({ct_skip} skipped)")

    # ── Period config ─────────────────────────────────────────────────────────
    print("Seeding period_config...")
    execute_values(cur,
        "INSERT INTO period_config (grade_band,period_name,period_order,is_alpha,is_active) "
        "VALUES %s ON CONFLICT (grade_band, period_name) DO NOTHING",
        period_config_rows())

    # ── Labs ──────────────────────────────────────────────────────────────────
    print("Seeding labs...")
    execute_values(cur,
        "INSERT INTO labs (name, lab_type, block, sub_type) VALUES %s ON CONFLICT DO NOTHING",
        [("Smart Class Block A", "SMART_CLASS","A","JUNIOR"),
         ("Smart Class Block B", "SMART_CLASS","B","PRIMARY"),
         ("Smart Class Block C", "SMART_CLASS","C","SENIOR"),
         ("Robotics Lab Junior", "ROBOTICS",   None,"JUNIOR"),
         ("Robotics Lab Senior", "ROBOTICS",   None,"SENIOR")])

    # ── Timetable ─────────────────────────────────────────────────────────────
    print("Seeding timetable...")
    tt_rows, tt_skip, tt_no_teacher = [], 0, 0
    for r in timetable_rows:
        cid = cls_map.get(r["class_name"])
        if not cid: tt_skip += 1; continue
        tid = tno_map.get(r["teacher_no"])
        if not tid: tt_no_teacher += 1
        sid = subj_map.get(r["subject"]) if r["subject"] else None
        tt_rows.append((
            cid, tid, sid,
            r["day"], r["period"], r["room_type"],
            r["is_practical"], r["lab_section"] or None
        ))
    if tt_rows:
        execute_values(cur,
            """INSERT INTO timetable
               (class_id,teacher_id,subject_id,day,period_name,room_type,is_practical,lab_section)
               VALUES %s ON CONFLICT (class_id, day, period_name, room_type) DO NOTHING""",
            tt_rows)
    print(f"  {len(tt_rows)} rows  ({tt_skip} class not found, {tt_no_teacher} teacher not found)")

    # ── GK / MSC ──────────────────────────────────────────────────────────────
    print("Seeding gk_msc...")
    gk_rows, gk_skip = [], 0
    for r in gk_msc_rows:
        cid     = cls_map.get(r["class_name"])
        gk_tid  = tno_map.get(r["gk_teacher_no"])
        msc_tid = tno_map.get(r["msc_teacher_no"])
        if cid:
            gk_rows.append((cid, gk_tid, msc_tid))
        else:
            gk_skip += 1
    if gk_rows:
        execute_values(cur,
            "INSERT INTO gk_msc (class_id, gk_teacher_id, msc_teacher_id) VALUES %s "
            "ON CONFLICT (class_id) DO NOTHING", gk_rows)
    print(f"  {len(gk_rows)} rows  ({gk_skip} skipped)")

    print("\nAll tables seeded successfully.")

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Loading CSV files ===")
    teachers       = load_teachers()
    print(f"  teacher_master  : {len(teachers)} teachers")
    timetable_rows = load_master_timetable()
    print(f"  master_timetable: {len(timetable_rows)} rows")
    gk_msc_rows    = load_gk_msc()
    print(f"  gk_msc_master   : {len(gk_msc_rows)} rows")
    tch_by_name    = {t["full_name"].upper(): 0 for t in teachers}
    ct_raw         = load_ct(tch_by_name)
    print(f"  CT 2026-27      : {len(ct_raw)} rows")

    print(f"\n=== Connecting to Supabase ===")
    conn = psycopg2.connect(SUPABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    print("  Connected")

    print("\n=== Dropping existing tables (clean rebuild) ===")
    cur.execute(DROP_SQL)
    conn.commit()
    print("  Tables dropped")

    print("\n=== Creating schema ===")
    cur.execute(SCHEMA_SQL)
    conn.commit()
    print("  Schema created")

    # Reload ct_raw with real teacher ids after schema exists
    # (teacher ids come from DB after insert, so re-run load_ct with real map)
    print("\n=== Seeding tables ===")
    seed(cur, teachers, timetable_rows, gk_msc_rows, ct_raw)
    conn.commit()

    cur.close()
    conn.close()
    print("\n=== ETL complete — Supabase is ready ===")

if __name__ == "__main__":
    main()
