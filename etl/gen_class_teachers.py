import csv, difflib, os, re

BASE = os.path.join(os.path.dirname(__file__), "CSV")

ROMAN = {
    "I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,
    "VII":7,"VIII":8,"IX":9,"X":10,
    "XI":11,"XII":12
}

def roman_to_num(cls):
    """'VII B' -> '7B',  'XII A (SCI.)' -> '12A',  'NURSERY' -> 'NURSERY'"""
    cls = cls.strip().upper()
    # Strip stream suffix like (SCI.) (COM.) (HUM.)
    cls = re.sub(r'\s*\(.*?\)', '', cls).strip()
    # Split into parts
    parts = cls.split()
    if parts and parts[0] in ROMAN:
        num = str(ROMAN[parts[0]])
        section = parts[1] if len(parts) > 1 else ""
        return num + section
    return cls

teachers = list(csv.DictReader(open(f"{BASE}/teacher_master.csv", encoding="utf-8-sig")))
tch_by_name = {t["Full_name"].upper(): t["Teacher_no"] for t in teachers}
all_names   = list(tch_by_name.keys())

# Build class list from timetable to get class names
timetable = list(csv.DictReader(open(f"{BASE}/master_timetable.csv", encoding="utf-8")))
class_names = sorted(set(r["Class"] for r in timetable))

# Assign sequential IDs matching what was inserted into Supabase
# Classes were inserted sorted — same order as generate_import_csvs.py
gk_msc = list(csv.DictReader(open(f"{BASE}/gk_msc_master.csv", encoding="utf-8-sig")))
all_class_names = sorted(set(
    [r["Class"] for r in timetable] +
    [r["Class"] for r in gk_msc]
))
cls_to_id = {c: i+1 for i, c in enumerate(all_class_names)}

# Teacher_no to sequential id
tno_to_id = {t["Teacher_no"]: i+1 for i, t in enumerate(teachers)}

rows = []
skipped = []
with open(f"{BASE}/CT 2026-27.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        cls  = roman_to_num(r.get("CLASS_SECTION","").strip())
        name = r.get("CLASS_TEACHER_NAME","").strip()
        if not cls or not name:
            continue
        # Manual overrides for name variants
        MANUAL = {
            "MR B K VIBHAKAR": "T066",
        }
        # Direct match
        tno = MANUAL.get(name.upper())
        if not tno:
            tno = None
        tid_name = tch_by_name.get(name.upper())
        if not tno and tid_name:
            tno = tid_name
        elif not tno:
            matches = difflib.get_close_matches(name.upper(), all_names, n=1, cutoff=0.75)
            if matches:
                tno = tch_by_name[matches[0]]

        cid = cls_to_id.get(cls)
        tid = tno_to_id.get(tno) if tno else None

        if cid and tid:
            rows.append((cid, tid))
        else:
            skipped.append(f"  SKIP: class={cls} teacher={name} cid={cid} tno={tno}")

print(f"Matched : {len(rows)}")
print(f"Skipped : {len(skipped)}")
for s in skipped:
    print(s)

# Write SQL — use subqueries to look up IDs by name (avoids hardcoded ID mismatch)
lines = ["-- Paste into Supabase SQL Editor\n"]
for cid, tid in rows:
    # Find class name and teacher_no for this pair
    cls_name = [c for c, i in cls_to_id.items() if i == cid]
    tno      = [t["Teacher_no"] for t in teachers if tno_to_id[t["Teacher_no"]] == tid]
    if cls_name and tno:
        lines.append(
            f"INSERT INTO class_teachers (class_id, teacher_id) "
            f"SELECT c.id, t.id FROM classes c, teachers t "
            f"WHERE c.name = '{cls_name[0]}' AND t.teacher_no = '{tno[0]}';"
        )

out = os.path.join(BASE, "supabase_import", "class_teachers.sql")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nGenerated: {out}")
