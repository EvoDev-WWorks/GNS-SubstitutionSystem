"""
Sync class teacher assignments → Supabase class_teachers table.
Run with --apply to actually write changes.
"""
import httpx, sys, warnings
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')

APPLY = '--apply' in sys.argv
URL   = 'https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'

# Load key from .env
import os
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
KEY = os.environ['SUPABASE_SERVICE_KEY']
H   = {'apikey': KEY, 'Authorization': f'Bearer {KEY}'}
HJ  = {**H, 'Content-Type': 'application/json', 'Prefer': 'return=representation'}

# ── Raw input data ───────────────────────────────────────────
RAW = """
MRS BARKHA KRI	11C
MRS. SHOBHA RANI	11D
DR SUJEET KR MISHRA	12D
MR RABINDRA KR	9C
MRS. SANGITA SHARAN	7H
MR. SANTOSH KUMAR	8G
MRS PAMMI	6G
MRS MOHITA SINGH	4C
MS. ANANTA SINHA	4E
MRS TANYA RAKSHIT	7E
MR. SHAMBHU	10D
MRS. ANJALI SINHA	9G
MRS. SHOBHA CHOUDHARY	7A
MRS. RUNI KUMARI	4D
MRS. NILANJANA	11A
MRS. RASHMI LATA	10A
MR. JITENDRA KUMAR	10I
MR. RAVI KR MISHRA	9F
MR. AJIT KUMAR SINGH	12B
MR. NAGENDRA SHARMA	10J
MRS. MEENU MINAKSHI	6C
MR. SUDHIR CHAUBEY	11B
MRS. SUPRIYA BALA	10H
MRS. ANAMIKA KUMARI	7C
MRS. RENU KUMARI	8A
MRS RUPAM CHOUDHARY	7J
MS MONIKA KRI	4A
MRS PRATIBHA SINGH	5F
MRS. SHEETAL KHURANA	3B
MRS. APARNA	2C
MRS. RICHA MISHRA	2D
MRS. BABY NEHA	1A
MR. SUNNY	9D
MRS RUBY TIWARY	12A
MRS. ANINDITA BANERJEE	12C
MRS. RENU SHARMA	10B
MR. M. K. VERMA	9B
MRS. AMITA GARDNER	10E
MRS. NEETA KISHORE	8E
MR. AJAY PRATAP SINGH	8F
MR. PRADEEP DUTTA	8H
MR. S. N. MISHRA	7G
MR. SUDHANSHU RANJAN	8C
MR ANJANI KUMAR	7D
MD. TANVEER ALAM	9H
MRS. PALLAVI	6B
MRS. RANI RANJAN	3D
MRS. KIRAN THAKUR	5C
MRS. NIKITA SINGH	3F
MRS. RUBY SINGH	1C
MS. VARSHA MISHRA	2E
MRS. TRIPTI MISHRA	3E
MRS. BHAWNA DUBEY	4F
MRS. SANSKRITI PRAKASH	1B
MR. SAYED H. AKHTAR	10F
MR. RAJAN KUMAR	10G
MR. SHASHANK PODDAR	9A
MR. PANKAJ KUMAR	8D
MR. ALOK KUMAR	9E
MR. NAVIN KUMAR SINGH	7F
MR MRITUNJAY KUMAR	8J
MR. DIWAKAR KUMAR	6F
MR NITISH KR	5D
MR. RANJAN KR	5A
MRS. MRIDULA PRASAD	2B
MRS. JYOTSNA	3C
MRS. ANURADHA SHARMA	3A
MRS. MEETU	1D
MRS. KAVITA PATHAK	9J
MRS. BASBI KUMARI	8I
MR. B K VIBHAKER	7B
MRS. JYOTI SINHA	6A
DR. MAMTA SINHA	4B
MRS. KUMARI MADHU	5E
MRS. NOMITA KUMARI	6E
MRS. RAJNI	2A
MRS. DIKSHA SANDALIYA	1E
MRS JYOTI GUPTA	2F
MRS ARCHITA RAJ SINGH	5G
MRS. SIMA KUMARI	6D
DR. S. K. PRADHAN	10C
MRS. ANUJA SARRAF	6H
MD. WARIS JAMAL	9I
MR SRI KRISHNA	7I
MR. AMIT KUMAR SINGH	5B
MR. ANINDYA BANERJEE	8B
MRS. SHABNAM MIRAJ	UKG A
MRS. ANKITA SNEHI	UKG B
MRS. SONALI	UKG C
MRS. NIDHI AGRAWAL	NUR
MRS. RUPA SINGH	LKG
""".strip()

# Name overrides: only entries where input ≠ DB name
NAME_OVERRIDE = {
    # abbreviations / alternate spellings → exact DB name
    'DR SUJEET KR MISHRA':   'DR. SUJEET KUMAR MISHRA',
    'MR RABINDRA KR':        'MR. RABINDRA KUMAR',
    'MRS. SHOBHA CHOUDHARY': 'MRS. SHOBHA N. CHOUDHARY',
    'MR. B K VIBHAKER':      'MR. BIBHAS KUMAR VIBHAKER',
    'MS MONIKA KRI':         'MS. MONIKA KUMARI',
    'MRS MOHITA SINGH':      'MRS MOHITA SINGH',   # exact in DB (no dot)
    'MRS PAMMI':             'MRS PAMMI KUMARI',
    'MRS RUPAM CHOUDHARY':   'MRS RUPAM CHOUDHARY',
    'MRS RUBY TIWARY':       'MRS RUBY TIWARY',    # exact in DB
    'MRS TANYA RAKSHIT':     'MRS TANYA RAKSHIT',  # exact in DB
    'MR. RAVI KR MISHRA':    'MR. RAVI KUMAR MISHRA',
    'MR. M. K. VERMA':       'MR. MANOJ KUMAR VERMA',
    'MRS. MEETU':            'MRS. MEETU KUMARI',
    'MRS. DIKSHA SANDALIYA': 'MRS. DIKSHA SANDILAYA',
    'MR NITISH KR':          'MR. NITISH KUMAR',
    'MR. RANJAN KR':         'MR. RANJAN KUMAR',
    'DR. S. K. PRADHAN':     'DR. SUNIL KUMAR PRADHAN',
    'MR SRI KRISHNA':        'MR. SRI KRISHNA',
    'MR MRITUNJAY KUMAR':    'MR. MRITUNJAY KUMAR',
    'MR ANJANI KUMAR':       'MR. ANJANI KUMAR',
    'MRS. SANSKRITI PRAKASH':'MRS. SANSKRITI PRAKASH',
}

# Class name overrides (input → DB name)
CLASS_OVERRIDE = {
    'NUR':   'NURSERY',
    'NURSERY': 'NURSERY',
}

def _get(table, params):
    rows, offset = [], 0
    while True:
        p = {**params, 'limit': '1000', 'offset': str(offset)}
        r = httpx.get(f'{URL}/{table}', headers=H, params=p, verify=False)
        chunk = r.json()
        if not chunk: break
        rows.extend(chunk)
        if len(chunk) < 1000: break
        offset += 1000
    return rows

print("Loading Supabase data…")
teachers_db = _get('teachers', {'select': 'id,full_name'})
classes_db  = _get('classes',  {'select': 'id,name'})
ct_db       = _get('class_teachers', {'select': 'class_id,teacher_id'})

t_by_name = {t['full_name'].upper().strip(): t['id'] for t in teachers_db}
t_by_id   = {t['id']: t['full_name'] for t in teachers_db}
c_by_name = {c['name'].upper().strip(): c['id'] for c in classes_db}
c_by_id   = {c['id']: c['name'] for c in classes_db}
ct_by_class = {r['class_id']: r['teacher_id'] for r in ct_db}

import re
def match_teacher(name):
    name = name.strip()
    upper = name.upper()
    # Apply override map
    for k, v in NAME_OVERRIDE.items():
        if upper == k.upper():
            name = v
            break
    upper = name.upper()
    if upper in t_by_name:
        return t_by_name[upper]
    # Strip title and try again
    clean = re.sub(r'^(MR\.|MRS\.|MS\.|DR\.|MD\.|MR |MRS |MS |DR |MD )', '', upper).strip()
    for k, v in t_by_name.items():
        kc = re.sub(r'^(MR\.|MRS\.|MS\.|DR\.|MD\.|MR |MRS |MS |DR |MD )', '', k).strip()
        if clean == kc:
            return v
    # Partial: first + last word match
    parts = clean.split()
    if len(parts) >= 2:
        for k, v in t_by_name.items():
            kc = re.sub(r'^(MR\.|MRS\.|MS\.|DR\.|MD\.|MR |MRS |MS |DR |MD )', '', k).strip()
            if parts[0] in kc and parts[-1] in kc:
                return v
    return None

def match_class(name):
    name = name.strip().upper()
    if name in CLASS_OVERRIDE:
        name = CLASS_OVERRIDE[name].upper()
    if name in c_by_name:
        return c_by_name[name]
    return None

# ── Parse RAW data ───────────────────────────────────────────
entries = []
unmatched_teachers = []
unmatched_classes  = []

seen = set()
for line in RAW.splitlines():
    line = line.strip()
    if not line or '\t' not in line:
        continue
    parts = line.split('\t', 1)
    if len(parts) != 2:
        continue
    teacher_name = parts[0].strip()
    class_name   = parts[1].strip()

    if not teacher_name or not class_name:
        continue

    key = class_name.upper()
    if key in seen:
        continue  # skip duplicate class entries
    seen.add(key)

    tid = match_teacher(teacher_name)
    cid = match_class(class_name)

    if not tid:
        unmatched_teachers.append(teacher_name)
    if not cid:
        unmatched_classes.append(class_name)
    if tid and cid:
        entries.append({'teacher_id': tid, 'class_id': cid,
                        'teacher_name': teacher_name, 'class_name': class_name})

print(f"\nParsed {len(entries)} matched entries")

if unmatched_teachers:
    print(f"\n⚠  Unmatched teachers ({len(unmatched_teachers)}):")
    for n in unmatched_teachers:
        print(f"   {n}")

if unmatched_classes:
    print(f"\n⚠  Unmatched classes ({len(unmatched_classes)}):")
    for n in unmatched_classes:
        print(f"   {n}")

# ── Diff ─────────────────────────────────────────────────────
to_insert, to_update, unchanged = [], [], []

for e in entries:
    existing_tid = ct_by_class.get(e['class_id'])
    if existing_tid is None:
        to_insert.append(e)
    elif existing_tid != e['teacher_id']:
        to_update.append({**e, 'old_teacher': t_by_id.get(existing_tid, str(existing_tid))})
    else:
        unchanged.append(e)

print(f"\n── DIFF ──────────────────────────────────────────────")
print(f"  Insert (new):   {len(to_insert)}")
print(f"  Update (change):{len(to_update)}")
print(f"  Unchanged:      {len(unchanged)}")

if to_update:
    print(f"\n  Updates:")
    for u in to_update:
        print(f"    {u['class_name']:8s}  {u['old_teacher']:35s} → {u['teacher_name']}")

if to_insert:
    print(f"\n  Inserts:")
    for e in to_insert:
        print(f"    {e['class_name']:8s}  {e['teacher_name']}")

if not APPLY:
    print("\nDry run complete. Run with --apply to apply changes.")
    sys.exit()

print(f"\nApplying…")
ins_ok = ins_err = upd_ok = upd_err = 0

for e in to_insert:
    r = httpx.post(f'{URL}/class_teachers', headers=HJ,
                   json={'class_id': e['class_id'], 'teacher_id': e['teacher_id']}, verify=False)
    if r.status_code in (200, 201):
        ins_ok += 1
    else:
        ins_err += 1
        print(f"  INS ERR {r.status_code} {e['class_name']}: {r.text[:80]}")

for e in to_update:
    r = httpx.patch(f'{URL}/class_teachers', headers=HJ,
                    params={'class_id': f"eq.{e['class_id']}"},
                    json={'teacher_id': e['teacher_id']}, verify=False)
    if r.status_code == 200:
        upd_ok += 1
    else:
        upd_err += 1
        print(f"  UPD ERR {r.status_code} {e['class_name']}: {r.text[:80]}")

print(f"\nDone!  Inserted:{ins_ok}  Updated:{upd_ok}  Errors:{ins_err+upd_err}")
