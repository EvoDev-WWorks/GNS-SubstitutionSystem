"""
build_final_csv.py
Merges timetable_final, smart_class_final, robotics_final into one
unified master_timetable.csv with consistent columns.

gk_msc_final stays separate (weekly fixed schedule, not day/period keyed).

Output columns:
  Teacher_no, Teacher_name, Subject, Day, Period, Class,
  Period_type, Is_practical, Room_type, Lab_section
"""

import csv, os, re

BASE = os.path.join(os.path.dirname(__file__), "CSV")

def normalize_section(raw):
    """'SMART CLASS : BLOCK A\\nDT. : 01 - 07'  ->  'BLOCK A'
       'BLOCK A JUNIOR'                          ->  'BLOCK A'
       'JUNIOR'                                  ->  'JUNIOR'   (robotics)
       'SENIOR'                                  ->  'SENIOR'   (robotics)
    """
    raw = raw.replace("\n", " ").strip()
    m = re.search(r"BLOCK\s+([A-Z])", raw, re.I)
    if m:
        return f"BLOCK {m.group(1).upper()}"
    return raw.upper()

# ── 1. timetable_final ────────────────────────────────────────────────────────
rows = []

with open(os.path.join(BASE, "timetable_final.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append({
            "Teacher_no":   r["Teacher_no"],
            "Teacher_name": r["Full_name"],
            "Subject":      r["Subject"],
            "Day":          r["Day"],
            "Period":        r["Period"],
            "Class":        r["Class"],
            "Period_type":  r["Period_type"],
            "Is_practical": r["Is_practical"],
            "Room_type":    r["Room_type"],
            "Lab_section":  "",
        })

print(f"timetable_final  : {len(rows):,} rows")

# ── 2. smart_class_final ──────────────────────────────────────────────────────
sc_count = 0
with open(os.path.join(BASE, "smart_class_final.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append({
            "Teacher_no":   r["Teacher_no"],
            "Teacher_name": r["Teacher_name"],
            "Subject":      "SMART CLASS",
            "Day":          r["Day"],
            "Period":        r["Period"],
            "Class":        r["Class"],
            "Period_type":  "REGULAR",
            "Is_practical": "No",
            "Room_type":    "SMART_CLASS",
            "Lab_section":  normalize_section(r["Section"]),
        })
        sc_count += 1

print(f"smart_class_final: {sc_count:,} rows")

# ── 3. robotics_final ─────────────────────────────────────────────────────────
rb_count = 0
with open(os.path.join(BASE, "robotics_final.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append({
            "Teacher_no":   r["Teacher_no"],
            "Teacher_name": r["Teacher_name"],
            "Subject":      "ROBOTICS",
            "Day":          r["Day"],
            "Period":        r["Period"],
            "Class":        r["Class"],
            "Period_type":  "REGULAR",
            "Is_practical": "Yes",
            "Room_type":    "ROBOTICS_LAB",
            "Lab_section":  normalize_section(r["Lab"]),
        })
        rb_count += 1

print(f"robotics_final   : {rb_count:,} rows")

# ── 4. Deduplicate — only remove TRUE duplicates (same teacher, same class, same period) ──
# A teacher CAN appear multiple times for the same period (PRACT/OPT/LIB = multiple teachers per class)
# But a teacher CANNOT appear for the SAME class twice at the same period
teacher_subject = {}
with open(os.path.join(BASE, "teacher_master.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        teacher_subject[r["Teacher_no"].strip()] = r["Subject"].strip().upper()

seen_exact   = set()   # (Teacher_no, Class, Day, Period, Room_type) — exact row dupes
seen_teacher = {}      # (Teacher_no, Day, Period, Room_type) -> row index — teacher double-booking
deduped      = []
removed_exact   = 0
removed_teacher = 0

for row in rows:
    exact_key   = (row["Teacher_no"], row["Class"], row["Day"], row["Period"], row["Room_type"])
    teacher_key = (row["Teacher_no"], row["Day"], row["Period"], row["Room_type"])

    if exact_key in seen_exact:
        removed_exact += 1
        continue

    seen_exact.add(exact_key)

    if teacher_key not in seen_teacher:
        seen_teacher[teacher_key] = len(deduped)
        deduped.append(row)
    else:
        # Teacher double-booked — keep entry matching their primary subject
        existing_idx = seen_teacher[teacher_key]
        existing_row = deduped[existing_idx]
        primary_subj = teacher_subject.get(row["Teacher_no"], "")
        if row["Subject"].upper() == primary_subj and existing_row["Subject"].upper() != primary_subj:
            deduped[existing_idx] = row   # replace with correct subject row
        # else: keep existing, drop new
        removed_teacher += 1

print(f"\n   Exact duplicates removed  : {removed_exact}")
print(f"   Teacher conflicts resolved: {removed_teacher}")
rows = deduped
rows = deduped

# ── 5. Write master_timetable.csv ─────────────────────────────────────────────
FIELDS = ["Teacher_no","Teacher_name","Subject","Day","Period","Class",
          "Period_type","Is_practical","Room_type","Lab_section"]

out_path = os.path.join(BASE, "master_timetable.csv")
with open(out_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)

total = len(rows)
print(f"\nDONE  master_timetable.csv : {total:,} total rows -> {out_path}")

# ── 6. Also copy gk_msc_final as-is (already clean) ──────────────────────────
import shutil
gk_src = os.path.join(BASE, "gk_msc_final.csv")
gk_dst = os.path.join(BASE, "gk_msc_master.csv")
shutil.copy(gk_src, gk_dst)
print(f"DONE  gk_msc_master.csv    : copied (fixed weekly schedule)")

# ── 7. Quick sanity check ─────────────────────────────────────────────────────
bad = [r for r in rows if not r["Teacher_no"] or r["Teacher_no"] == "???"]
print(f"\n   Unmatched Teacher_no  : {len(bad)}")

from collections import Counter
by_type = Counter(r["Room_type"] for r in rows)
for k,v in sorted(by_type.items()):
    print(f"   {k:<20}: {v:,}")
