"""
Generates a formatted timetable summary for every class.
Output: timetable_summary.txt
"""
import httpx, warnings, re
warnings.filterwarnings('ignore')

URL = 'https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'
KEY = 'sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V'
H   = {'apikey': KEY, 'Authorization': f'Bearer {KEY}'}

def get(table, params=None):
    rows, offset, limit = [], 0, 1000
    while True:
        p = {**(params or {}), 'limit': str(limit), 'offset': str(offset)}
        r = httpx.get(f'{URL}/{table}', headers=H, params=p, verify=False)
        chunk = r.json()
        if not chunk: break
        rows.extend(chunk)
        if len(chunk) < limit: break
        offset += limit
    return rows

# ── reference data ────────────────────────────────────────────
teachers = {t['id']: t['full_name'] for t in get('teachers', {'select':'id,full_name'})}
subjects  = {s['id']: s['code']      for s in get('subjects',  {'select':'id,code'})}
classes_all = get('classes', {'select':'id,name'})

def sort_key(c):
    n = c['name'].strip()
    if n == 'NURSERY': return (-3, '')
    if n == 'LKG':     return (-2, '')
    if n.startswith('UKG'): return (-1, n)
    m = re.match(r'^(\d+)([A-Z]*)$', n)
    if m: return (int(m.group(1)), m.group(2))
    return (999, n)

SKIP_KEYWORDS = ['LIB','LAB','PRACT','OPT','SUB','EXTRA']
main_classes = sorted(
    [c for c in classes_all
     if not any(k in c['name'].upper() for k in SKIP_KEYWORDS)
     and '+' not in c['name']
     and '\n' not in c['name']
     and c['name'].strip() not in ('', '1``')
     and 'A/V' not in c['name']],
    key=sort_key
)

DAYS    = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
PERIODS = ['P1','P2','P3','P4','P5','P6','P7','P8']

lines = []

for cls in main_classes:
    cid  = cls['id']
    name = cls['name']

    rows = get('timetable', {
        'select': 'day,period_name,subject_id,teacher_id',
        'class_id': f'eq.{cid}'
    })

    if not rows:
        continue

    # build lookup: (day, period) -> list of (subj_code, teacher_short)
    lookup = {}
    for r in rows:
        key = (r['day'], r['period_name'])
        subj = subjects.get(r['subject_id'], '?')
        tname = teachers.get(r['teacher_id'], '?')
        # shorten teacher name for display
        parts = tname.replace('MRS.','').replace('MRS','').replace('MR.','').replace('MR','') \
                     .replace('MS.','').replace('MS','').replace('DR.','').replace('DR','').strip().split()
        short = parts[-1] if parts else tname  # use last name
        lookup.setdefault(key, []).append(f"{subj}/{short}")

    lines.append(f"\n{'='*90}")
    lines.append(f"  CLASS: {name}")
    lines.append(f"{'='*90}")

    # header
    header = f"{'DAY':<12}" + "".join(f"{'P'+str(i+1):>14}" for i in range(8))
    lines.append(header)
    lines.append('-'*90)

    for day in DAYS:
        # check if any data for this day
        day_entries = [lookup.get((day, p), []) for p in PERIODS]
        if not any(day_entries):
            continue

        # subject row
        subj_row  = f"{day:<12}"
        teach_row = f"{'':12}"
        for p in PERIODS:
            entries = lookup.get((day, p), [])
            if entries:
                # show first entry (most cells have 1 entry)
                parts = entries[0].split('/')
                s = parts[0][:6] if parts else ''
                t = parts[1][:6] if len(parts)>1 else ''
                if len(entries) > 1:
                    s = s + '*'   # mark multi-entry cells
            else:
                s = t = ''
            subj_row  += f"{s:>14}"
            teach_row += f"{t:>14}"
        lines.append(subj_row)
        lines.append(teach_row)
        lines.append('')

output = '\n'.join(lines)

with open('timetable_summary.txt', 'w', encoding='utf-8') as f:
    f.write(output)

print(f"Written timetable_summary.txt — {len(main_classes)} classes, {len(lines)} lines")

# Also print a compact stats table
print(f"\n{'CLASS':<10} {'MON':>5} {'TUE':>5} {'WED':>5} {'THU':>5} {'FRI':>5} {'SAT':>5} {'TOTAL':>7}")
print('-'*55)
for cls in main_classes:
    cid = cls['id']
    rows = get('timetable', {'select':'day,period_name','class_id':f'eq.{cid}'})
    day_counts = {d: sum(1 for r in rows if r['day']==d) for d in DAYS}
    total = len(rows)
    if total == 0: continue
    print(f"{cls['name']:<10} {day_counts['Monday']:>5} {day_counts['Tuesday']:>5} "
          f"{day_counts['Wednesday']:>5} {day_counts['Thursday']:>5} "
          f"{day_counts['Friday']:>5} {day_counts['Saturday']:>5} {total:>7}")
