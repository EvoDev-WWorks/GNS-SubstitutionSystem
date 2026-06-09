"""
Sync timetable from ROUTINE 2026-27 Excel → Supabase.
Run with --apply to actually write changes.
"""
import pandas as pd, httpx, warnings, re, sys
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

APPLY = '--apply' in sys.argv
XLSX  = r'C:\Users\hp\Downloads\ROUTINE 2026-27 (1).xlsx'
URL   = 'https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'

import os as _os
_env = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
if _os.path.exists(_env):
    with open(_env) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _os.environ.setdefault(_k.strip(), _v.strip())
KEY   = _os.environ['SUPABASE_SERVICE_KEY']
H     = {'apikey': KEY, 'Authorization': f'Bearer {KEY}'}
HJ    = {**H, 'Content-Type': 'application/json', 'Prefer': 'return=representation'}

COL_PERIOD = {2:'alpha1', 3:'alpha2', 5:'P1', 6:'P2', 7:'P3', 8:'P4',
              10:'P5', 11:'P6', 12:'P7', 13:'P8'}
DAY_MAP = {'MONDAY':'Monday','TUESDAY':'Tuesday','WEDNESDAY':'Wednesday',
           'THURSDAY':'Thursday','FRIDAY':'Friday','SATURDAY':'Saturday'}

# Manual name overrides (Excel name → DB name)
NAME_OVERRIDE = {
    'MR. K.K. THAKUR':       'MR. KAUSHAL KISHORE THAKUR',
    'MRS. DIKSHA SANDALIYA':  'MRS. DIKSHA SANDILAYA',
    'MR. SHANKAR SARAN':      'MR. SHANKER SARAN',
    'MRS PAMMI':              'MRS PAMMI KUMARI',
    'MRS BARKHA KUMARI':      'MRS BARKHA KRI',
    'MRS KRI SALONI':         'MRS KUMARI SALONI',
    'MRS KRI SHEELA PANDEY':  'MRS. SHEELA PANDEY',
    'MRS. MEETU':             'MRS. MEETU KUMARI',
    'MRS. SANSKRITI':         'MRS. SANSKRITI PRAKASH',
    'MR. L. K. PATHAK':       'MR. LALIT KUMAR PATHAK',
    'MR. M. K. RAHUL':        'MR. MUKESH KUMAR RAHUL',
    'MR. M. K. VERMA':        'MR. MANOJ KUMAR VERMA',
    'MR. N. K. CHAUDHARY':    'MR. NAND KISHORE CHAUDHARY',
    'DR. S. K. PRADHAN':      'DR. SUNIL KUMAR PRADHAN',
    'MR. KARN':               'MR. KARN KUMAR',
    'MRS RUPAM CHAUDHARY':    'MRS RUPAM CHOUDHARY',
}

def _get(table, params):
    rows, offset = [], 0
    while True:
        p = {**params, 'limit':'1000', 'offset':str(offset)}
        r = httpx.get(f'{URL}/{table}', headers=H, params=p, verify=False)
        chunk = r.json()
        if not chunk: break
        rows.extend(chunk)
        if len(chunk) < 1000: break
        offset += 1000
    return rows

print("Loading Supabase data...")
teachers_db = _get('teachers', {'select':'id,full_name'})
classes_db  = _get('classes',  {'select':'id,name'})
tt_db       = _get('timetable',{'select':'id,teacher_id,class_id,subject_id,day,period_name'})

t_by_id   = {t['id']: t['full_name'] for t in teachers_db}
t_by_name = {t['full_name'].upper().strip(): t['id'] for t in teachers_db}
c_by_id   = {c['id']: c['name'] for c in classes_db}
c_by_name = {c['name'].upper().strip(): c['id'] for c in classes_db}
tt_lookup = {(r['teacher_id'], r['day'], r['period_name']): r for r in tt_db}

def match_teacher(name):
    if not name or str(name).strip() in ('','nan'): return None
    name = str(name).strip()
    # Apply manual override
    upper = name.upper()
    for k,v in NAME_OVERRIDE.items():
        if upper == k.upper():
            name = v; break
    upper = name.upper()
    if upper in t_by_name: return t_by_name[upper]
    clean = re.sub(r'^(MR\.|MRS\.|MS\.|DR\.|MR |MRS |MS |DR )', '', upper).strip()
    for k,v in t_by_name.items():
        kc = re.sub(r'^(MR\.|MRS\.|MS\.|DR\.|MR |MRS |MS |DR )', '', k).strip()
        if clean == kc: return v
    parts = clean.split()
    if len(parts) >= 2:
        for k,v in t_by_name.items():
            kc = re.sub(r'^(MR\.|MRS\.|MS\.|DR\.|MR |MRS |MS |DR )', '', k).strip()
            if parts[0] in kc and parts[-1] in kc: return v
    return None

SKIP_SFXS = [' GK',' RL1',' RL2',' LIB',' LAB',' PRACT',' OPT',' SUB',' MSC',' RL']
def match_class(raw):
    if not raw or str(raw).strip() in ('','nan'): return None
    raw = str(raw).upper().strip()
    if raw in c_by_name: return c_by_name[raw]
    for sfx in SKIP_SFXS:
        if raw.endswith(sfx):
            base = raw[:-len(sfx)].strip()
            if base in c_by_name: return c_by_name[base]
    return None

print("Parsing Excel...")
excel_entries = []
unmatched_teachers, unmatched_classes = set(), set()

for sheet_day, db_day in DAY_MAP.items():
    df = pd.read_excel(XLSX, sheet_name=sheet_day, header=None)
    for _, row in df.iterrows():
        sn   = row[0]
        name = str(row[1]).strip() if pd.notna(row[1]) else ''
        if pd.isna(sn) or str(sn).strip() in ('','S.N.','NaN'): continue
        try: float(sn)
        except: continue
        tid = match_teacher(name)
        if not tid:
            if name and name not in ('NaN','nan',''): unmatched_teachers.add(name)
            continue
        for col, period in COL_PERIOD.items():
            val = row[col] if col < len(row) else None
            if pd.isna(val) or str(val).strip() in ('','nan','NaN'): continue
            cid = match_class(val)
            if not cid:
                unmatched_classes.add(str(val).strip())
                continue
            excel_entries.append({'teacher_id':tid,'day':db_day,'period_name':period,'class_id':cid})

print(f"Parsed {len(excel_entries)} entries")
print(f"Unmatched teachers ({len(unmatched_teachers)}): {sorted(unmatched_teachers)}")
print(f"Unmatched classes  ({len(unmatched_classes)}):  {sorted(list(unmatched_classes))[:20]}")

# Only track class_id changes (not subject)
to_insert, to_update = [], []
for e in excel_entries:
    key = (e['teacher_id'], e['day'], e['period_name'])
    existing = tt_lookup.get(key)
    if not existing:
        to_insert.append(e)
    elif existing['class_id'] != e['class_id']:
        to_update.append({'id':existing['id'],'new_class':e['class_id'],
                          'old_class':existing['class_id'],'entry':e})

print(f"\n--- DIFF ---")
print(f"INSERT: {len(to_insert)}  |  UPDATE (class change): {len(to_update)}")
print(f"\nSample UPDATEs:")
for u in to_update[:20]:
    e = u['entry']
    print(f"  {t_by_id.get(e['teacher_id'],'?'):35s} {e['day']:10s} {e['period_name']:6s}  {c_by_id.get(u['old_class'],'?'):8s} -> {c_by_id.get(u['new_class'],'?')}")

if not APPLY:
    print("\nDry run complete. Run with --apply to apply changes.")
    exit()

print(f"\nApplying changes...")
ins_ok=ins_err=upd_ok=upd_err=0
for e in to_insert:
    r=httpx.post(f'{URL}/timetable',headers=HJ,
        json={**e,'room_type':'CLASSROOM','is_practical':False},verify=False)
    if r.status_code in (200,201): ins_ok+=1
    elif r.status_code==409: pass  # conflict, skip
    else: ins_err+=1; print(f"  INS ERR {r.status_code}: {r.text[:80]}")

for u in to_update:
    r=httpx.patch(f'{URL}/timetable',headers=HJ,
        params={'id':f"eq.{u['id']}"},json={'class_id':u['new_class']},verify=False)
    if r.status_code==200: upd_ok+=1
    else: upd_err+=1; print(f"  UPD ERR {r.status_code}: {r.text[:80]}")

print(f"\nDone! Inserted:{ins_ok} | Updated:{upd_ok} | Errors:{ins_err+upd_err}")
