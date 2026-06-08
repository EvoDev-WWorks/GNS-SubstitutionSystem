"""
Bulk timetable import — inserts missing entries for ALL classes (grades 1-6, Nursery, LKG, UKG).
Skips any (class_id, day, period_name) slot that already has data for that teacher.
Run: python import_timetable.py
"""
import httpx, warnings
warnings.filterwarnings('ignore')

URL = 'https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'
KEY = 'sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V'
H   = {'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'}

# ─── helpers ────────────────────────────────────────────────────────────────
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

def post_one(table, data):
    r = httpx.post(f'{URL}/{table}', headers={**H, 'Prefer': 'return=minimal'},
                   json=data, verify=False)
    return r.status_code

# ─── fetch reference data ────────────────────────────────────────────────────
print("Loading reference data...")
teachers = get('teachers', {'select': 'id,full_name,teacher_no'})
subjects = get('subjects', {'select': 'id,code'})
classes  = get('classes',  {'select': 'id,name'})

subject_by_code = {s['code']: s['id'] for s in subjects}
class_by_name   = {c['name']: c['id'] for c in classes}

# ─── ensure missing subjects exist ──────────────────────────────────────────
NEW_SUBJS = [
    'GK', 'SST', 'AI', 'AI LAB', 'EVS', 'ACT', 'MPT', 'PD',
    'DANCE', 'SINGING', 'GAME', 'STORY TELLING', 'AUDIO/VISUAL',
    'ENG RECT', 'HINDI RECT', 'ENG WR', 'HINDI WR',
    'ENG WR/ORAL', 'HINDI DICT/WR', 'ENG WR/DICT/SPL',
    'HINDI WR/DICT/SPL', 'NUM WORK', 'ART/CRAFT', 'SMART',
]
for code in NEW_SUBJS:
    if code not in subject_by_code:
        r = httpx.post(f'{URL}/subjects', headers={**H,'Prefer':'return=representation'},
                       json={'code': code}, verify=False)
        if r.status_code in (200,201):
            sid = r.json()[0]['id']
            subject_by_code[code] = sid
            print(f"  Added subject: {code} (id={sid})")
        else:
            print(f"  ERR adding subject {code}: {r.text[:80]}")

# ─── subject abbreviation → subject_id ──────────────────────────────────────
S = subject_by_code   # shorthand
def subj(abbr):
    abbr = abbr.strip()
    direct_map = {
        'ENG': S['ENGLISH'], 'ENGLISH': S['ENGLISH'],
        'MATHS': S['MATHS'], 'MATH': S['MATHS'],
        'PHY': S['SCIENCE (PHY)'], 'PHYSICS': S['SCIENCE (PHY)'],
        'CHE': S['SCIENCE (CHEM)'], 'CHEM': S['SCIENCE (CHEM)'],
        'BIO': S['SCIENCE (BIO)'], 'BIOLOGY': S['SCIENCE (BIO)'],
        'SCIENCE': S['SCIENCE'], 'SCI': S['SCIENCE'],
        'HINDI': S['HINDI'], 'HND': S['HINDI'],
        'SANSKRIT': S['SANSKRIT'],
        'ART': S['ART'], 'ART/CRAFT': S.get('ART/CRAFT', S['ART']),
        'MUSIC': S['MUSIC'],
        'ROBOTICS': S['ROBOTICS'],
        'LIB': S['LIB'], 'LIBRARY': S['LIB'],
        'GEO': S['SOCIAL STUDIES (GEO)'],
        'HIS/POL': S['SOCIAL STUDIES (HIST)'],
        'HISTORY': S['SOCIAL STUDIES (HIST)'],
        'POL.SC.': S['POL.SC.'], 'POLSC': S['POL.SC.'],
        'COMMERCE': S['COMMERCE'],
        'COMPUTER': S['COMPUTER'],
        'PT': S['PHE'], 'PHE': S['PHE'],
        'MSC': S['SMART CLASS'], 'SMART CLASS': S['SMART CLASS'],
        'SMART': S.get('SMART', S['SMART CLASS']),
        'AUDIO/VISUAL': S.get('AUDIO/VISUAL', S['SMART CLASS']),
        'GK': S.get('GK'), 'SST': S.get('SST'),
        'AI': S.get('AI'), 'AI LAB': S.get('AI LAB'),
        'EVS': S.get('EVS'), 'ACT': S.get('ACT'),
        'MPT': S.get('MPT'), 'PD': S.get('PD'),
        'P.D.': S.get('PD'),
        'DANCE': S.get('DANCE'), 'SINGING': S.get('SINGING'),
        'GAME': S.get('GAME'), 'STORY TELLING': S.get('STORY TELLING'),
        'ENG RECT': S.get('ENG RECT'), 'ENG RECT.': S.get('ENG RECT'),
        'HINDI RECT': S.get('HINDI RECT'), 'HINDI RECT.': S.get('HINDI RECT'),
        'ENG WR': S.get('ENG WR'), 'ENG WR/ORAL': S.get('ENG WR/ORAL'),
        'HINDI DICT/WR': S.get('HINDI DICT/WR'),
        'HINDI WR': S.get('HINDI WR'),
        'ENG WR/DICT/SPL': S.get('ENG WR/DICT/SPL'),
        'ENG WR/DICT/SPL.': S.get('ENG WR/DICT/SPL'),
        'HINDI WR/DICT/SPL': S.get('HINDI WR/DICT/SPL'),
        'HINDI WR/DICT/SPL.': S.get('HINDI WR/DICT/SPL'),
        'NUM WORK': S.get('NUM WORK'),
        'ACTIVITY': S.get('ACT'),
    }
    sid = direct_map.get(abbr)
    if sid is None:
        # fallback: try direct lookup
        sid = S.get(abbr)
    return sid

# ─── teacher abbreviation → teacher_id ──────────────────────────────────────
T = {
    # Grade 6
    'MEENU': 55, 'KK THAKUR': 25, 'SANTOSH': 12, 'PRADEEP': 121,
    'SHEELA': 65, 'ANAND': 85, 'RUPAM CH.': 102, 'RUPAM CH': 102,
    'ASHOK': 48, 'KRI. KALPANA': 42, 'KRI KALPANA': 42,
    'KALPANA KRI.': 42, 'KALPANA KRI': 42, 'KALPANA': 42,
    'SUDHANSHU': 123, 'BRAJESH': 92, 'ANJANA M': 80, 'ANJANA': 80,
    'SUNITA': 110, 'SUNITA M.': 110, 'SUNITA M': 110,
    'IB JHA': 56, 'SEEMA': 79, 'SIMA': 79,
    'ANJANEE': 124, 'ANJANEE KUMAR': 124,
    'SANGITA SARAN': 11, 'SANGITA SARA': 11,
    'MK RAHUL': 91, 'MUKESH R.': 91, 'MUKESH R': 91,
    'PALLAVI': 126, 'PALLVI': 126,
    'BETTY K': 50, 'BETTY K.': 50, 'BETTY': 50,
    'MONIKA': 103, 'RANJAN': 30, 'SACHIN': 96,
    'DEEPAK': 93, 'SHANKAR': 94, 'SHANKAR S.': 94, 'SHANKAR S': 94,
    'SN MISHRA': 122, 'AJAY PRATAP': 120,
    'DIWAKAR': 27, 'DIWAKAR K': 27, 'DIWAKAR K.': 27,
    'ARCHITA': 68, 'ARCHITA RAJ': 68,
    'PAMMI': 13, 'PAMMI KRI.': 13, 'PAMMI KRI': 13, 'PAMMI K': 13,
    'SIMA K': 79,
    'AMIT KUMAR': 86, 'AMIT KR.': 86, 'AMIT KR': 86, 'AMIT': 86,
    'SAKSHI': 35,
    'RUNI K': 43, 'RUNI K.': 43, 'RUNI KRI.': 43, 'RUNI KRI': 43, 'RUNI': 43,
    'ANUJA': 78, 'ANUJA S': 78, 'ANUJA SARRAF': 78,
    'BHAWNA D.': 133, 'BHAWNA D': 133, 'BHAWNA': 133,
    'MAMTA': 69, 'MAMTA SINHA': 69, 'MAMTA SINHA.': 69,
    'SANJAY SHARMA': 88, 'SANJAY SH.': 88, 'SANJAY SH': 88, 'SANJAY': 88,
    'SHASHANK PD': 20, 'SHASHANK PD.': 20,
    'NOMITA': 71, 'NOMITA K.': 71, 'NOMITA KRI.': 71, 'NOMITA KRI': 71,
    'SANGITA K': 95, 'SANGITA KRI.': 95, 'SANGITA KRI': 95, 'SANGITA': 95,
    # Grade 5
    'KIRAN T': 128, 'KIRAN TH.': 128, 'KIRAN TH': 128, 'KIRAN': 128,
    'RUPAM KRI.': 106, 'RUPAM KRI': 106,
    'RUPAM': 106,
    'NOMITA KRI': 71,
    'SUBOSH S': 32, 'SUBOSH SINGH': 32, 'SUBOSH S.': 32,
    'PRATIBHA S.': 104, 'PRATIBHA S': 104, 'PRATIBHA': 104,
    'SHEETAL KH.': 105, 'SHEETAL KH': 105, 'SHEETAL K.': 105, 'SHEETAL K': 105,
    'NITISH': 29,
    'MADHU': 70, 'KRI. MADHU': 70, 'KRI MADHU': 70,
    'GAUTAM': 28, 'GAUTAM M.': 28, 'GAUTAM M': 28,
    'ANIMESH': 87,
    'PAMMI KRI': 13,
    'SEEMA KRI.': 79, 'SEEMA KRI': 79,
    'TRIPTI M.': 132, 'TRIPTI M': 132, 'TRIPTI': 132,
    # Grade 4
    'RANI RANJAN': 127, 'RANI RANJAN.': 127,
    'NIKITA SINGH': 129, 'NIKITA S.': 129, 'NIKITA S': 129, 'NIKITA': 129,
    'ANANTA SINHA': 15, 'ANANTA SINHA.': 15,
    'MOHITA SINGH': 14, 'MOHITA S.': 14, 'MOHITA S': 14, 'MOHITA': 14,
    'ANURADHA SH.': 34, 'ANURADHA SH': 34, 'ANURADHA': 34,
    'ANURADAHA S': 34, 'ANURADAHA S.': 34, 'ANURADAHA': 34,
    'ANURADHA S.': 34, 'ANURADHA S': 34,
    'RUPAM KUMARI': 106,
    # Grade 3
    'JYOTSANA': 33, 'JYOTSNA': 33,
    'BETTY K.': 50,
    'SANJAY SH': 88,
    'MOHITA S': 14,
    'PAMMI K.': 13,
    # Grade 2
    'APARNA K.': 107, 'APARNA K': 107, 'APARNA': 107,
    'MRIDULA PD.': 31, 'MRIDULA PD': 31, 'MRIDULA': 31,
    'RAJNI K.': 72, 'RAJNI K': 72, 'RAJNI': 72,
    'RICHA MISHRA': 108, 'RICHA': 108,
    'VARSHA': 131,
    'JYOTI G.': 74, 'JYOTI G': 74, 'JYOTI': 74,
    'BRAJESH S.': 92, 'BRAJESH S': 92,
    # Grade 1
    'BABY NEHA': 109,
    'SANSKRITI': 134,
    'RUBY SINGH': 130, 'RUBY S.': 130, 'RUBY S': 130, 'RUBY': 130,
    'MEETU': 36, 'MEETU KUMARI': 36,
    'DIKSHA S.': 73, 'DIKSHA S': 73, 'DIKSHA': 73,
    'NIDHI AG': 101, 'NIDHI': 101,
    'RUPA S.': 100, 'RUPA S': 100, 'RUPA': 100,
    'SHABNAM M.': 97, 'SHABNAM M': 97, 'SHABNAM': 97,
    'ANKITA S.': 98, 'ANKITA S': 98, 'ANKITA': 98,
    'SALONI': 99, 'SONALI K.': 99, 'SONALI K': 99,
    'PALLAVI': 126,
    # others
    'SUDHANSHU R': 123,
    'PRADEEP DUTTA': 121,
}

# ─── timetable data ──────────────────────────────────────────────────────────
# Format: TT[class_name][day] = [(subj, teacher), ...] — 8 items for P1..P8, None = empty
# α (assembly) periods are not encoded here (always empty in images)

DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']

# Helper: shorthand row builder — p1..p8, use None for empty period
def row(p1,p2,p3,p4,p5,p6,p7,p8):
    return [p1,p2,p3,p4,p5,p6,p7,p8]

def E(s,t): return (s,t)   # entry

TT = {}

# ════════════════════════════════════════════════════════════════
# CLASS 6C
# ════════════════════════════════════════════════════════════════
TT['6C'] = {
'Monday':    row(E('PHY','MEENU'),E('MATHS','KK THAKUR'),E('HIS/POL','SANTOSH'),E('ENG','PRADEEP'),E('HINDI','SHEELA'),E('AI','ANAND'),E('BIO','RUPAM CH.'),E('MSC','PRADEEP')),
'Tuesday':   row(E('MATHS','KK THAKUR'),E('MUSIC','DEEPAK'),E('ENG','PRADEEP'),E('SANSKRIT','ANJANA M'),E('ROBOTICS','SUDHANSHU'),E('HIS/POL','SANTOSH'),E('HINDI','SHEELA'),E('CHE','ASHOK')),
'Wednesday': row(E('PHY','MEENU'),E('HINDI','SHEELA'),E('ENG','PRADEEP'),E('ROBOTICS','SUDHANSHU'),E('PT','BRAJESH'),E('AI LAB','ANAND'),E('GEO','KRI. KALPANA'),E('MATHS','KK THAKUR')),
'Thursday':  row(E('MATHS','KK THAKUR'),E('GEO','KRI. KALPANA'),E('HIS/POL','SANTOSH'),E('ENG','PRADEEP'),E('HINDI','SHEELA'),E('SANSKRIT','ANJANA M'),E('CHE','ASHOK'),E('MATHS','KK THAKUR')),
'Friday':    row(E('MATHS','KK THAKUR'),E('ART','SANGITA K'),E('SANSKRIT','ANJANA M'),E('ENG','PRADEEP'),E('HINDI','SHEELA'),E('AI','ANAND'),E('GK','AJAY PRATAP'),E('BIO','RUPAM CH.')),
'Saturday':  row(E('MPT','MEENU'),E('MATHS','KK THAKUR'),E('SANSKRIT','ANJANA M'),E('ENG','PRADEEP'),E('LIB','SUNITA'),E('HIS/POL','SANTOSH'),E('ACT','MEENU'),E('ACT','MEENU')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 6D
# ════════════════════════════════════════════════════════════════
TT['6D'] = {
'Monday':    row(E('HINDI','SEEMA'),E('AI','ANIMESH'),E('MATHS','KK THAKUR'),E('ROBOTICS','ANJANEE'),E('ENG','ANJANEE'),E('BIO','RUPAM CH.'),E('HIS/POL','SANGITA SARAN'),E('SANSKRIT','SEEMA')),
'Tuesday':   row(E('PHY','IB JHA'),E('HINDI','SEEMA'),E('MATHS','KK THAKUR'),E('ENG','ANJANEE'),E('GEO','KALPANA KRI.'),E('HIS/POL','SANGITA SARAN'),E('MATHS','KK THAKUR'),E('MSC','ANJANEE')),
'Wednesday': row(E('HINDI','SEEMA'),E('AI LAB','ANIMESH'),E('MATHS','KK THAKUR'),E('ENG','ANJANEE'),E('SANSKRIT','SEEMA'),E('CHE','ASHOK'),E('ROBOTICS','ANJANEE'),E('BIO','RUPAM CH.')),
'Thursday':  row(E('HINDI','SEEMA'),E('PT','MK RAHUL'),E('MATHS','KK THAKUR'),E('ENG','ANJANEE'),E('SANSKRIT','SEEMA'),E('CHE','ASHOK'),E('LIB','SUNITA'),E('GEO','KALPANA KRI.')),
'Friday':    row(E('PHY','IB JHA'),E('HINDI','SEEMA'),E('MATHS','KK THAKUR'),E('ENG','ANJANEE'),E('ART','SANGITA K'),E('GK','SHASHANK PD'),E('HIS/POL','SANGITA SARAN'),E('SANSKRIT','SEEMA')),
'Saturday':  row(E('MPT','SEEMA'),E('HIS/POL','SANGITA SARAN'),E('MATHS','KK THAKUR'),E('ENG','ANJANEE'),E('MUSIC','DEEPAK'),E('AI','ANIMESH'),E('ACT','SEEMA'),E('ACT','SEEMA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 6E
# ════════════════════════════════════════════════════════════════
TT['6E'] = {
'Monday':    row(E('HINDI','NOMITA'),E('ART','SACHIN'),E('CHE','BETTY K'),E('BIO','MONIKA'),E('MATHS','RANJAN'),E('ENG','ANJANEE'),E('SANSKRIT','ANUJA S'),E('MUSIC','SHANKAR')),
'Tuesday':   row(E('HINDI','NOMITA'),E('MATHS','RANJAN'),E('ROBOTICS','ANJANEE'),E('GK','ASHOK'),E('HIS/POL','SANTOSH'),E('ENG','ANJANEE'),E('PHY','MEENU'),E('MATHS','RANJAN')),
'Wednesday': row(E('HINDI','NOMITA'),E('MATHS','RANJAN'),E('CHE','BETTY K'),E('SANSKRIT','ANUJA S'),E('GEO','KRI. KALPANA'),E('ENG','ANJANEE'),E('AI','ANAND'),E('HIS/POL','SANTOSH')),
'Thursday':  row(E('HINDI','NOMITA'),E('LIB','SUNITA'),E('ROBOTICS','ANJANEE'),E('SANSKRIT','ANUJA S'),E('MATHS','RANJAN'),E('ENG','ANJANEE'),E('AI LAB','ANAND'),E('PHY','MEENU')),
'Friday':    row(E('HINDI','NOMITA'),E('ENG','ANJANEE'),E('GEO','KRI. KALPANA'),E('BIO','MONIKA'),E('MSC','SN MISHRA'),E('MATHS','RANJAN'),E('HIS/POL','SANTOSH'),E('SANSKRIT','ANUJA S')),
'Saturday':  row(E('MPT','NOMITA'),E('AI','ANAND'),E('MATHS','RANJAN'),E('HIS/POL','SANTOSH'),E('PT','BRAJESH'),E('ENG','ANJANEE'),E('ACT','NOMITA'),E('ACT','NOMITA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 6F
# ════════════════════════════════════════════════════════════════
TT['6F'] = {
'Monday':    row(E('MATHS','DIWAKAR'),E('ENG','PALLAVI'),E('AI LAB','ANIMESH'),E('SANSKRIT','ANJANA M'),E('ROBOTICS','PRADEEP'),E('HIS/POL','SANTOSH'),E('HINDI','ARCHITA'),E('PHY','IB JHA')),
'Tuesday':   row(E('MATHS','DIWAKAR'),E('ENG','PALLAVI'),E('CHE','BETTY K'),E('ROBOTICS','PRADEEP'),E('BIO','MONIKA'),E('SANSKRIT','ANJANA M'),E('MSC','PALLAVI'),E('HINDI','ARCHITA')),
'Wednesday': row(E('MATHS','DIWAKAR'),E('ENG','PALLAVI'),E('AI','ANIMESH'),E('BIO','MONIKA'),E('PT','BRAJESH'),E('HIS/POL','SANTOSH'),E('HINDI','ARCHITA'),E('MATHS','DIWAKAR')),
'Thursday':  row(E('MATHS','DIWAKAR'),E('ENG','PALLAVI'),E('AI','ANIMESH'),E('MUSIC','SHANKAR'),E('GEO','KALPANA KRI.'),E('HIS/POL','SANTOSH'),E('HINDI','ARCHITA'),E('SANSKRIT','ANJANA M')),
'Friday':    row(E('MATHS','DIWAKAR'),E('ENG','PALLAVI'),E('CHE','BETTY K'),E('PHY','IB JHA'),E('HINDI','ARCHITA'),E('HIS/POL','SANTOSH'),E('GK','PALLAVI'),E('MATHS','DIWAKAR')),
'Saturday':  row(E('MPT','DIWAKAR'),E('ENG','PALLAVI'),E('LIB','SUNITA'),E('SANSKRIT','ANJANA M'),E('ART','SACHIN'),E('GEO','KALPANA KRI.'),E('ACT','DIWAKAR'),E('ACT','DIWAKAR')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 6G
# ════════════════════════════════════════════════════════════════
TT['6G'] = {
'Monday':    row(E('GK','PAMMI'),E('HINDI','SIMA'),E('SANSKRIT','ANJANA M'),E('ENG','PALLAVI'),E('MATHS','SAKSHI'),E('GEO','RUNI K'),E('ROBOTICS','ASHOK'),E('HIS/POL','PAMMI')),
'Tuesday':   row(E('MATHS','SAKSHI'),E('AI','AMIT KUMAR'),E('ART','SACHIN'),E('MSC','BETTY K'),E('ENG','PALLAVI'),E('HIS/POL','PAMMI'),E('BIO','MONIKA'),E('SANSKRIT','ANJANA M')),
'Wednesday': row(E('MATHS','SAKSHI'),E('HINDI','SIMA'),E('LIB','SUNITA'),E('PHY','MEENU'),E('ENG','PALLAVI'),E('CHE','BETTY K'),E('SANSKRIT','ANJANA M'),E('HIS/POL','PAMMI')),
'Thursday':  row(E('MATHS','SAKSHI'),E('HINDI','SIMA'),E('CHE','BETTY K'),E('BIO','MONIKA'),E('ENG','PALLAVI'),E('HIS/POL','PAMMI'),E('PT','MK RAHUL'),E('GEO','RUNI K')),
'Friday':    row(E('MATHS','SAKSHI'),E('AI LAB','AMIT KUMAR'),E('HINDI','SIMA'),E('ROBOTICS','ASHOK'),E('MATHS','SAKSHI'),E('PHY','MEENU'),E('SANSKRIT','ANJANA M'),E('ENG','PALLAVI')),
'Saturday':  row(E('MPT','PAMMI'),E('MUSIC','SHANKAR'),E('MATHS','SAKSHI'),E('AI','AMIT KUMAR'),E('HINDI','SIMA'),E('ENG','PALLAVI'),E('ACT','PAMMI'),E('ACT','PAMMI')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 6H
# ════════════════════════════════════════════════════════════════
TT['6H'] = {
'Monday':    row(E('SANSKRIT','ANUJA'),E('ENG','BHAWNA D.'),E('ART','SACHIN'),E('HINDI','MAMTA'),E('HIS/POL','SANGITA SARAN'),E('MATHS','RANJAN'),E('GEO','RUNI K'),E('BIO','MONIKA')),
'Tuesday':   row(E('SANSKRIT','ANUJA'),E('ENG','BHAWNA D.'),E('MSC','AJAY PRATAP'),E('AI','SANJAY SHARMA'),E('MATHS','RANJAN'),E('HINDI','MAMTA'),E('PT','BRAJESH'),E('CHE','BETTY K')),
'Wednesday': row(E('SANSKRIT','ANUJA'),E('ENG','BHAWNA D.'),E('MATHS','RANJAN'),E('PHY','IB JHA'),E('HINDI','MAMTA'),E('HIS/POL','SANGITA SARAN'),E('MATHS','RANJAN'),E('ROBOTICS','BHAWNA D.')),
'Thursday':  row(E('AI LAB','SANJAY SHARMA'),E('HIS/POL','SANGITA SARAN'),E('ENG','BHAWNA D.'),E('GEO','RUNI K'),E('BIO','MONIKA'),E('MATHS','RANJAN'),E('GK','AJAY PRATAP'),E('CHE','BETTY K')),
'Friday':    row(E('SANSKRIT','ANUJA'),E('ENG','BHAWNA D.'),E('LIB','SUNITA'),E('AI','SANJAY SHARMA'),E('HINDI','MAMTA'),E('HIS/POL','SANGITA SARAN'),E('MATHS','RANJAN'),E('MUSIC','SHANKAR')),
'Saturday':  row(E('MPT','ANUJA'),E('ENG','BHAWNA D.'),E('PHY','IB JHA'),E('MATHS','RANJAN'),E('HINDI','MAMTA'),E('ROBOTICS','BHAWNA D.'),E('ACT','ANUJA'),E('ACT','ANUJA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5A  (CT: MR RANJAN KUMAR)
# ════════════════════════════════════════════════════════════════
TT['5A'] = {
'Monday':    row(E('ROBOTICS','RANJAN'),E('MATHS','RANJAN'),E('MATHS','RANJAN'),E('SST','PAMMI'),E('SCIENCE','RUPAM CH.'),E('AI','SANJAY SH.'),E('ENG','PALLAVI'),E('LIB','SUNITA')),
'Tuesday':   row(E('SST','PAMMI'),E('SCIENCE','RUPAM CH.'),E('ENG','PALLAVI'),E('HINDI','SHEELA'),E('AI LAB','SANJAY SH.'),E('PT','MK RAHUL'),E('MATHS','RANJAN'),E('SANSKRIT','SEEMA KRI.')),
'Wednesday': row(E('HINDI','SHEELA'),E('SCIENCE','RUPAM CH.'),E('GK','PAMMI'),E('MATHS','RANJAN'),E('SST','PAMMI'),E('ENG','PALLAVI'),E('SANSKRIT','SEEMA KRI.'),E('SST','PAMMI')),
'Thursday':  row(E('SST','PAMMI'),E('MATHS','RANJAN'),E('ENG','PALLAVI'),E('HINDI','SHEELA'),E('AI','SANJAY SH.'),E('SANSKRIT','SEEMA KRI.'),E('MSC','PAMMI'),E('SCIENCE','RUPAM CH.')),
'Friday':    row(E('ROBOTICS','RANJAN'),E('MATHS','RANJAN'),E('HINDI','SHEELA'),E('ART','SACHIN'),E('ENG','PALLAVI'),E('SCIENCE','RUPAM CH.'),E('SANSKRIT','SEEMA KRI.'),E('SST','PAMMI')),
'Saturday':  row(E('MPT','RANJAN'),E('SCIENCE','RUPAM CH.'),E('ENG','PALLAVI'),E('SST','PAMMI'),E('MUSIC','DEEPAK'),E('HINDI','SHEELA'),E('ACT','RANJAN'),E('ACT','RANJAN')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5B  (CT: MR AMIT KUMAR)
# ════════════════════════════════════════════════════════════════
TT['5B'] = {
'Monday':    row(E('AI','AMIT KUMAR'),E('SCIENCE','RUPAM KRI.'),E('MATHS','SAKSHI'),E('ENG','BHAWNA D.'),E('GK','GAUTAM M.'),E('HINDI','SHEELA'),E('SST','MOHITA'),E('SANSKRIT','ANJANA')),
'Tuesday':   row(E('ROBOTICS','AMIT KUMAR'),E('SCIENCE','RUPAM KRI.'),E('MATHS','SAKSHI'),E('HINDI','SHEELA'),E('MUSIC','DEEPAK'),E('ENG','BHAWNA D.'),E('SST','MOHITA'),E('MATHS','SAKSHI')),
'Wednesday': row(E('AI','AMIT KUMAR'),E('SCIENCE','RUPAM KRI.'),E('MATHS','SAKSHI'),E('ENG','BHAWNA D.'),E('SANSKRIT','ANJANA'),E('SST','MOHITA'),E('PT','BRAJESH'),E('ART','SANGITA')),
'Thursday':  row(E('ROBOTICS','AMIT KUMAR'),E('SANSKRIT','ANJANA'),E('MATHS','SAKSHI'),E('LIB','SUNITA'),E('ENG','BHAWNA D.'),E('SST','MOHITA'),E('HINDI','SHEELA'),E('SCIENCE','RUPAM KRI.')),
'Friday':    row(E('AI LAB','AMIT KUMAR'),E('SCIENCE','RUPAM KRI.'),E('MATHS','SAKSHI'),E('SST','MOHITA'),E('ENG','BHAWNA D.'),E('HINDI','SHEELA'),E('SST','MOHITA'),E('MSC','BHAWNA D.')),
'Saturday':  row(E('MPT','AMIT KUMAR'),E('SCIENCE','RUPAM KRI.'),E('ENG','BHAWNA D.'),E('MATHS','SAKSHI'),E('HINDI','SHEELA'),E('SANSKRIT','ANJANA'),E('ACT','AMIT KUMAR'),E('ACT','AMIT KUMAR')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5C  (CT: MRS KIRAN THAKUR)
# ════════════════════════════════════════════════════════════════
TT['5C'] = {
'Monday':    row(E('ENG','KIRAN T'),E('MUSIC','DEEPAK'),E('SCIENCE','MONIKA'),E('HINDI','NOMITA KRI.'),E('MATHS','DIWAKAR K'),E('SST','KALPANA KRI.'),E('SANSKRIT','ANJANA'),E('ENG','KIRAN T')),
'Tuesday':   row(E('ENG','KIRAN T'),E('SANSKRIT','ANJANA'),E('SCIENCE','MONIKA'),E('HINDI','NOMITA KRI.'),E('MATHS','DIWAKAR K'),E('SST','KALPANA KRI.'),E('AI','SANJAY SH.'),E('ROBOTICS','KIRAN T')),
'Wednesday': row(E('ENG','KIRAN T'),E('ART','SANGITA'),E('SCIENCE','MONIKA'),E('LIB','SUNITA'),E('MATHS','DIWAKAR K'),E('SANSKRIT','ANJANA'),E('AI','SANJAY SH.'),E('SST','KALPANA KRI.')),
'Thursday':  row(E('ENG','KIRAN T'),E('MATHS','DIWAKAR K'),E('SCIENCE','MONIKA'),E('HINDI','NOMITA KRI.'),E('MATHS','DIWAKAR K'),E('MSC','BHAWNA D.'),E('SST','KALPANA KRI.'),E('GK','GAUTAM M.')),
'Friday':    row(E('ENG','KIRAN T'),E('SANSKRIT','ANJANA'),E('PT','BRAJESH S.'),E('HINDI','NOMITA KRI.'),E('SCIENCE','MONIKA'),E('SST','KALPANA KRI.'),E('MATHS','DIWAKAR K'),E('ROBOTICS','KIRAN T')),
'Saturday':  row(E('MPT','KIRAN T'),E('SST','KALPANA KRI.'),E('SCIENCE','MONIKA'),E('HINDI','NOMITA KRI.'),E('MATHS','DIWAKAR K'),E('AI LAB','SANJAY SH.'),E('ACT','KIRAN T'),E('ACT','KIRAN T')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5D  (CT: MR NITISH KUMAR)
# ════════════════════════════════════════════════════════════════
TT['5D'] = {
'Monday':    row(E('MATHS','NITISH'),E('SST','PAMMI KRI.'),E('SCIENCE','RUPAM KRI.'),E('MSC','NITISH'),E('ENG','BHAWNA D.'),E('SANSKRIT','ANJANA M'),E('HINDI','NOMITA'),E('MATHS','NITISH')),
'Tuesday':   row(E('MATHS','NITISH'),E('SST','PAMMI KRI.'),E('SANSKRIT','ANJANA M'),E('ROBOTICS','NITISH'),E('ENG','BHAWNA D.'),E('SCIENCE','RUPAM KRI.'),E('HINDI','NOMITA'),E('GK','NITISH')),
'Wednesday': row(E('MATHS','NITISH'),E('SST','PAMMI KRI.'),E('SCIENCE','RUPAM KRI.'),E('AI LAB','AMIT KR.'),E('PT','MK RAHUL'),E('ENG','BHAWNA D.'),E('LIB','SUNITA'),E('MUSIC','DEEPAK')),
'Thursday':  row(E('MATHS','NITISH'),E('SST','PAMMI KRI.'),E('SCIENCE','RUPAM KRI.'),E('ENG','BHAWNA D.'),E('SANSKRIT','ANJANA M'),E('AI','AMIT KR.'),E('HINDI','NOMITA'),E('ROBOTICS','NITISH')),
'Friday':    row(E('MATHS','NITISH'),E('SST','PAMMI KRI.'),E('SCIENCE','RUPAM KRI.'),E('ENG','BHAWNA D.'),E('SANSKRIT','ANJANA M'),E('ART','SANGITA'),E('HINDI','NOMITA'),E('MATHS','NITISH')),
'Saturday':  row(E('MPT','NITISH'),E('SST','PAMMI KRI.'),E('AI','AMIT KR.'),E('SCIENCE','RUPAM KRI.'),E('ENG','BHAWNA D.'),E('HINDI','NOMITA'),E('ACT','NITISH'),E('ACT','NITISH')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5E  (CT: MRS KUMARI MADHU)
# ════════════════════════════════════════════════════════════════
TT['5E'] = {
'Monday':    row(E('HINDI','MADHU'),E('MATHS','GAUTAM'),E('ENG','KIRAN T'),E('SCIENCE','RUPAM KRI.'),E('SST','KALPANA KRI.'),E('MUSIC','SHANKAR'),E('MSC','BHAWNA D.'),E('AI','AMIT KR.')),
'Tuesday':   row(E('HINDI','MADHU'),E('MATHS','GAUTAM'),E('ENG','KIRAN T'),E('SST','KALPANA KRI.'),E('SCIENCE','RUPAM KRI.'),E('AI LAB','AMIT KR.'),E('SANSKRIT','ANJANA M'),E('GK','GAUTAM M.')),
'Wednesday': row(E('HINDI','MADHU'),E('MATHS','GAUTAM'),E('SANSKRIT','ANJANA M'),E('SST','KALPANA KRI.'),E('SCIENCE','RUPAM KRI.'),E('ROBOTICS','SANJAY SH.'),E('ENG','KIRAN T'),E('MATHS','GAUTAM')),
'Thursday':  row(E('HINDI','MADHU'),E('MATHS','GAUTAM'),E('SANSKRIT','ANJANA M'),E('SST','KALPANA KRI.'),E('SCIENCE','RUPAM KRI.'),E('ROBOTICS','SANJAY SH.'),E('PT','BRAJESH'),E('ENG','KIRAN T')),
'Friday':    row(E('HINDI','MADHU'),E('MATHS','GAUTAM'),E('ENG','KIRAN T'),E('LIB','SUNITA'),E('SCIENCE','RUPAM KRI.'),E('AI','AMIT KR.'),E('ART','SANGITA K'),E('SST','KALPANA KRI.')),
'Saturday':  row(E('MPT','MADHU'),E('MATHS','GAUTAM'),E('ENG','KIRAN T'),E('SST','KALPANA KRI.'),E('SANSKRIT','ANJANA M'),E('SCIENCE','RUPAM KRI.'),E('ACT','MADHU'),E('ACT','MADHU')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5F  (CT: MRS PRATIBHA SINGH)
# ════════════════════════════════════════════════════════════════
TT['5F'] = {
'Monday':    row(E('SCI','PRATIBHA'),E('SANSKRIT','ANJANA M'),E('MATHS','GAUTAM'),E('SST','RUNI KRI.'),E('ENG','KIRAN T'),E('ART','SACHIN'),E('HINDI','MAMTA SINHA'),E('MATHS','GAUTAM')),
'Tuesday':   row(E('SCI','PRATIBHA'),E('SST','RUNI KRI.'),E('ROBOTICS','KRI. KALPANA'),E('AI','ANIMESH'),E('ENG','KIRAN T'),E('MATHS','GAUTAM'),E('HINDI','MAMTA SINHA'),E('SCI','PRATIBHA')),
'Wednesday': row(E('SANSKRIT','ANJANA M'),E('SST','RUNI KRI.'),E('MATHS','GAUTAM'),E('SCI','PRATIBHA'),E('ENG','KIRAN T'),E('PT','MK RAHUL'),E('HINDI','MAMTA SINHA'),E('AI LAB','ANIMESH')),
'Thursday':  row(E('SCI','PRATIBHA'),E('ENG','KIRAN T'),E('MATHS','GAUTAM'),E('SANSKRIT','ANJANA M'),E('SST','RUNI KRI.'),E('AI','ANIMESH'),E('HINDI','MAMTA SINHA'),E('MSC','BHAWNA D.')),
'Friday':    row(E('SCI','PRATIBHA'),E('SST','RUNI KRI.'),E('MATHS','GAUTAM'),E('MUSIC','SHANKAR'),E('ENG','KIRAN T'),E('HINDI','MAMTA SINHA'),E('LIB','SUNITA'),E('GK','GAUTAM M.')),
'Saturday':  row(E('MPT','PRATIBHA'),E('SANSKRIT','ANJANA M'),E('ROBOTICS','KRI. KALPANA'),E('SST','RUNI KRI.'),E('ENG','KIRAN T'),E('MATHS','GAUTAM'),E('ACT','PRATIBHA'),E('ACT','PRATIBHA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 5G  (CT: MS ARCHITA RAJ SINGH)
# ════════════════════════════════════════════════════════════════
TT['5G'] = {
'Monday':    row(E('HINDI','ARCHITA'),E('MATHS','SUBOSH S'),E('SCIENCE','SHEETAL KH.'),E('ENG','KIRAN'),E('SST','RUNI KRI.'),E('LIB','SUNITA'),E('ROBOTICS','KRI. KALPANA'),E('MATHS','SUBOSH S')),
'Tuesday':   row(E('SANSKRIT','ANJANA M'),E('MATHS','SUBOSH S'),E('AI LAB','ANIMESH'),E('ENG','KIRAN'),E('HINDI','ARCHITA'),E('SST','RUNI KRI.'),E('SCIENCE','SHEETAL KH.'),E('MSC','TRIPTI M.')),
'Wednesday': row(E('HINDI','ARCHITA'),E('SANSKRIT','ANJANA M'),E('SCIENCE','SHEETAL KH.'),E('ENG','KIRAN'),E('ART','SACHIN'),E('SST','RUNI KRI.'),E('MATHS','SUBOSH S'),E('ENG','KIRAN')),
'Thursday':  row(E('SANSKRIT','ANJANA M'),E('MATHS','SUBOSH S'),E('SCIENCE','SHEETAL KH.'),E('ENG','KIRAN'),E('AI','ANIMESH'),E('SST','RUNI KRI.'),E('PT','BRAJESH'),E('HINDI','ARCHITA')),
'Friday':    row(E('HINDI','ARCHITA'),E('ENG','KIRAN'),E('AI','ANIMESH'),E('SANSKRIT','ANJANA M'),E('ROBOTICS','KRI. KALPANA'),E('SST','RUNI KRI.'),E('SCIENCE','SHEETAL KH.'),E('MATHS','SUBOSH S')),
'Saturday':  row(E('MPT','ARCHITA'),E('MATHS','SUBOSH S'),E('SCIENCE','SHEETAL KH.'),E('MUSIC','SHANKAR'),E('GK','GAUTAM M.'),E('SST','RUNI KRI.'),E('ACT','ARCHITA'),E('ACT','ARCHITA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 4A  (CT: MRS RUPAM KUMARI)
# ════════════════════════════════════════════════════════════════
TT['4A'] = {
'Monday':    row(E('SCIENCE','MONIKA'),E('SST','KALPANA KRI.'),E('HINDI','SEEMA KRI.'),E('MATHS','SAKSHI'),E('AI LAB','SANJAY SH.'),E('MATHS','SAKSHI'),E('ENG','TRIPTI M.'),E('ART','SANGITA')),
'Tuesday':   row(E('SCIENCE','MONIKA'),E('SST','KALPANA KRI.'),E('LIB','SUNITA'),E('HINDI','SEEMA KRI.'),E('ENG','TRIPTI M.'),E('MATHS','SAKSHI'),E('HINDI','SEEMA KRI.'),E('MUSIC','DEEPAK')),
'Wednesday': row(E('SCIENCE','MONIKA'),E('SST','KALPANA KRI.'),E('AI','SANJAY SH.'),E('HINDI','SEEMA KRI.'),E('ENG','TRIPTI M.'),E('MATHS','SAKSHI'),E('MSC','TRIPTI M.'),E('SCIENCE','MONIKA')),
'Thursday':  row(E('SCIENCE','MONIKA'),E('ENG','TRIPTI M.'),E('SST','KALPANA KRI.'),E('HINDI','SEEMA KRI.'),E('PT','BRAJESH'),E('MATHS','SAKSHI'),E('ROBOTICS','TRIPTI M.'),E('ENG','TRIPTI M.')),
'Friday':    row(E('SCIENCE','MONIKA'),E('SST','KALPANA KRI.'),E('ROBOTICS','TRIPTI M.'),E('HINDI','SEEMA KRI.'),E('ENG','TRIPTI M.'),E('MATHS','SAKSHI'),E('AI','SANJAY SH.'),E('GK','SANJAY SH.')),
'Saturday':  row(E('MPT','MONIKA'),E('MATHS','SAKSHI'),E('ENG','TRIPTI M.'),E('HINDI','SEEMA KRI.'),E('SST','KALPANA KRI.'),E('MATHS','SAKSHI'),E('ACT','MONIKA'),E('ACT','MONIKA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 4B  (CT: MRS MAMTA SINHA)
# ════════════════════════════════════════════════════════════════
TT['4B'] = {
'Monday':    row(E('HINDI','MAMTA SINHA'),E('MATHS','SAKSHI'),E('SST','RUNI KRI.'),E('ART','SANGITA'),E('SCIENCE','BETTY K'),E('ENG','KIRAN TH.'),E('MATHS','SAKSHI'),E('HINDI','MAMTA SINHA')),
'Tuesday':   row(E('HINDI','MAMTA SINHA'),E('SCIENCE','BETTY K'),E('SST','RUNI KRI.'),E('GK','SAKSHI'),E('LIB','SUNITA'),E('ENG','KIRAN TH.'),E('MATHS','SAKSHI'),E('AI LAB','SANJAY SH.')),
'Wednesday': row(E('HINDI','MAMTA SINHA'),E('SCIENCE','BETTY K'),E('ENG','KIRAN TH.'),E('MATHS','SAKSHI'),E('SST','RUNI KRI.'),E('ENG','KIRAN TH.'),E('MATHS','SAKSHI'),E('ROBOTICS','SAKSHI')),
'Thursday':  row(E('HINDI','MAMTA SINHA'),E('SCIENCE','BETTY K'),E('SST','RUNI KRI.'),E('AI','SANJAY SH.'),E('ROBOTICS','SAKSHI'),E('ENG','KIRAN TH.'),E('MATHS','SAKSHI'),E('HINDI','MAMTA SINHA')),
'Friday':    row(E('HINDI','MAMTA SINHA'),E('SCIENCE','BETTY K'),E('SST','RUNI KRI.'),E('MATHS','SAKSHI'),E('MSC','PAMMI'),E('ENG','KIRAN TH.'),E('MUSIC','DEEPAK'),E('AI','SANJAY SH.')),
'Saturday':  row(E('MPT','MAMTA SINHA'),E('SST','RUNI KRI.'),E('SCIENCE','BETTY K'),E('ENG','KIRAN TH.'),E('MATHS','SAKSHI'),E('PT','BRAJESH'),E('ACT','MAMTA SINHA'),E('ACT','MAMTA SINHA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 4C  (CT: MRS MOHITA SINGH)
# ════════════════════════════════════════════════════════════════
TT['4C'] = {
'Monday':    row(E('SST','MOHITA SINGH'),E('MATHS','ANURADHA SH.'),E('AI','SANJAY SH.'),E('MUSIC','DEEPAK'),E('HINDI','SEEMA KRI.'),E('ENGLISH','RANI RANJAN'),E('SCIENCE','RUPAM KRI.'),E('SST','MOHITA SINGH')),
'Tuesday':   row(E('SST','MOHITA SINGH'),E('MATHS','ANURADHA SH.'),E('HINDI','SEEMA KRI.'),E('LIB','SUNITA'),E('ENGLISH','RANI RANJAN'),E('HINDI','SEEMA KRI.'),E('SCIENCE','RUPAM KRI.'),E('MATHS','ANURADHA SH.')),
'Wednesday': row(E('SST','MOHITA SINGH'),E('MATHS','ANURADHA SH.'),E('ENGLISH','RANI RANJAN'),E('AI','SANJAY SH.'),E('ENGLISH','RANI RANJAN'),E('HINDI','SEEMA KRI.'),E('SCIENCE','RUPAM KRI.'),E('MSC','MOHITA SINGH')),
'Thursday':  row(E('SST','MOHITA SINGH'),E('SCIENCE','RUPAM KRI.'),E('MATHS','ANURADHA SH.'),E('PT','BRAJESH'),E('MATHS','ANURADHA SH.'),E('ART','SANGITA K'),E('HINDI','SEEMA KRI.'),E('ENGLISH','RANI RANJAN')),
'Friday':    row(E('SST','MOHITA SINGH'),E('MATHS','ANURADHA SH.'),E('AI LAB','SANJAY SH.'),E('ROBOTICS','SANGITA SARAN'),E('GK','MOHITA SINGH'),E('HINDI','SEEMA KRI.'),E('SCIENCE','RUPAM KRI.'),E('ENGLISH','RANI RANJAN')),
'Saturday':  row(E('MPT','MOHITA SINGH'),E('HINDI','SEEMA KRI.'),E('ENGLISH','RANI RANJAN'),E('ROBOTICS','SANGITA SARAN'),E('SCIENCE','RUPAM KRI.'),E('MATHS','ANURADHA SH.'),E('ACT','MOHITA SINGH'),E('ACT','MOHITA SINGH')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 4D  (CT: MRS RUNI KUMARI)
# ════════════════════════════════════════════════════════════════
TT['4D'] = {
'Monday':    row(E('SST','RUNI KRI'),E('HINDI','SHEELA'),E('ENGLISH','RANI RANJAN'),E('MATHS','SUBOSH SINGH'),E('SCIENCE','PRATIBHA'),E('AI LAB','AMIT KUMAR'),E('MATHS','SUBOSH SINGH'),E('ART','SACHIN')),
'Tuesday':   row(E('SST','RUNI KRI'),E('HINDI','SHEELA'),E('SCIENCE','PRATIBHA'),E('MATHS','SUBOSH SINGH'),E('ROBOTICS','PAMMI'),E('ENGLISH','RANI RANJAN'),E('GK','PAMMI'),E('SST','RUNI KRI')),
'Wednesday': row(E('SST','RUNI KRI'),E('AI','AMIT KUMAR'),E('SCIENCE','PRATIBHA'),E('MATHS','SUBOSH SINGH'),E('PT','MK RAHUL'),E('ENGLISH','RANI RANJAN'),E('MSC','RANI RANJAN'),E('HINDI','SHEELA')),
'Thursday':  row(E('SST','RUNI KRI'),E('HINDI','SHEELA'),E('ENGLISH','RANI RANJAN'),E('MATHS','SUBOSH SINGH'),E('SCIENCE','PRATIBHA'),E('ENGLISH','RANI RANJAN'),E('MUSIC','SHANKAR S'),E('MATHS','SUBOSH SINGH')),
'Friday':    row(E('SST','RUNI KRI'),E('HINDI','SHEELA'),E('SCIENCE','PRATIBHA'),E('MATHS','SUBOSH SINGH'),E('AI','AMIT KUMAR'),E('ENGLISH','RANI RANJAN'),E('ROBOTICS','PAMMI'),E('HINDI','SHEELA')),
'Saturday':  row(E('MPT','RUNI KRI'),E('HINDI','SHEELA'),E('SCIENCE','PRATIBHA'),E('MATHS','SUBOSH SINGH'),E('ENGLISH','RANI RANJAN'),E('LIB','SUNITA'),E('ACT','RUNI KRI'),E('ACT','RUNI KRI')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 4E  (CT: MS ANANTA SINHA)
# ════════════════════════════════════════════════════════════════
TT['4E'] = {
'Monday':    row(E('SST','ANANTA SINHA'),E('SCIENCE','SHEETAL KH.'),E('ROBOTICS','KALPANA KRI.'),E('MATHS','GAUTAM M.'),E('ENGLISH','NIKITA SINGH'),E('MATHS','GAUTAM M.'),E('HINDI','SHEELA'),E('SST','ANANTA SINHA')),
'Tuesday':   row(E('SST','ANANTA SINHA'),E('SCIENCE','SHEETAL KH.'),E('ENGLISH','NIKITA SINGH'),E('MATHS','GAUTAM M.'),E('ENGLISH','NIKITA SINGH'),E('ART','SACHIN'),E('ROBOTICS','KALPANA KRI.'),E('HINDI','SHEELA')),
'Wednesday': row(E('SST','ANANTA SINHA'),E('SCIENCE','SHEETAL KH.'),E('HINDI','SHEELA'),E('MATHS','GAUTAM M.'),E('ENGLISH','NIKITA SINGH'),E('AI','AMIT'),E('HINDI','SHEELA'),E('MUSIC','SHANKAR')),
'Thursday':  row(E('SST','ANANTA SINHA'),E('SCIENCE','SHEETAL KH.'),E('HINDI','SHEELA'),E('MATHS','GAUTAM M.'),E('ENGLISH','NIKITA SINGH'),E('LIB','SUNITA'),E('GK','NIKITA SINGH'),E('AI LAB','AMIT')),
'Friday':    row(E('SST','ANANTA SINHA'),E('SCIENCE','SHEETAL KH.'),E('AI','AMIT'),E('HINDI','SHEELA'),E('ENGLISH','NIKITA SINGH'),E('MATHS','GAUTAM M.'),E('MATHS','GAUTAM M.'),E('MSC','NIKITA SINGH')),
'Saturday':  row(E('MPT','ANANTA SINHA'),E('SCIENCE','SHEETAL KH.'),E('HINDI','SHEELA'),E('MATHS','GAUTAM M.'),E('ENGLISH','NIKITA SINGH'),E('PT','BRAJESH'),E('ACT','ANANTA SINHA'),E('ACT','ANANTA SINHA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 4F  (CT: MRS BHAWNA DUBEY)
# ════════════════════════════════════════════════════════════════
TT['4F'] = {
'Monday':    row(E('ENGLISH','BHAWNA D.'),E('HINDI','NOMITA K.'),E('MATHS','JYOTSANA'),E('AI LAB','AMIT'),E('MSC','SUDHANSHU R'),E('SCIENCE','SHEETAL KH.'),E('SST','PAMMI'),E('ENGLISH','BHAWNA D.')),
'Tuesday':   row(E('ENGLISH','BHAWNA D.'),E('HINDI','NOMITA K.'),E('MATHS','JYOTSANA'),E('SST','PAMMI'),E('SCIENCE','SHEETAL KH.'),E('ROBOTICS','MOHITA SINGH'),E('AI','AMIT'),E('ENGLISH','BHAWNA D.')),
'Wednesday': row(E('ENGLISH','BHAWNA D.'),E('HINDI','NOMITA K.'),E('ROBOTICS','MOHITA SINGH'),E('SST','PAMMI'),E('HINDI','NOMITA K.'),E('SCIENCE','SHEETAL KH.'),E('MATHS','JYOTSANA'),E('GK','NOMITA K.')),
'Thursday':  row(E('ENGLISH','BHAWNA D.'),E('HINDI','NOMITA K.'),E('MATHS','JYOTSANA'),E('ART','SACHIN'),E('SST','PAMMI'),E('SCIENCE','SHEETAL KH.'),E('AI','AMIT'),E('MATHS','JYOTSANA')),
'Friday':    row(E('ENGLISH','BHAWNA D.'),E('HINDI','NOMITA K.'),E('MATHS','JYOTSANA'),E('SST','PAMMI'),E('LIB','SUNITA'),E('SCIENCE','SHEETAL KH.'),E('MUSIC','SHANKAR S'),E('MATHS','JYOTSANA')),
'Saturday':  row(E('MPT','BHAWNA D.'),E('HINDI','NOMITA K.'),E('MATHS','JYOTSANA'),E('PT','MK RAHUL'),E('SST','PAMMI'),E('SCIENCE','SHEETAL KH.'),E('ACT','BHAWNA D.'),E('ACT','BHAWNA D.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 3A  (CT: MRS ANURADHA SHARMA)
# ════════════════════════════════════════════════════════════════
TT['3A'] = {
'Monday':    row(E('MATHS','ANURADHA'),E('ENG','NIKITA SINGH'),E('HINDI','MAMTA SINHA'),E('SST','MOHITA S.'),E('ART','SACHIN'),E('MATHS','ANURADHA'),E('AI','SANJAY SH.'),E('SCIENCE','BETTY K')),
'Tuesday':   row(E('MATHS','ANURADHA'),E('ENG','NIKITA SINGH'),E('HINDI','MAMTA SINHA'),E('SST','MOHITA S.'),E('MATHS','ANURADHA'),E('LIB','SUNITA'),E('SCIENCE','BETTY K'),E('SST','MOHITA S.')),
'Wednesday': row(E('MATHS','ANURADHA'),E('ENG','NIKITA SINGH'),E('HINDI','MAMTA SINHA'),E('SST','MOHITA S.'),E('SCIENCE','BETTY K'),E('MSC','BETTY K.'),E('ROBOTICS','PAMMI K'),E('ENG','NIKITA SINGH')),
'Thursday':  row(E('MATHS','ANURADHA'),E('ENG','NIKITA SINGH'),E('HINDI','MAMTA SINHA'),E('ROBOTICS','PAMMI K'),E('SCIENCE','BETTY K'),E('MUSIC','DEEPAK'),E('SST','MOHITA S.'),E('MATHS','ANURADHA')),
'Friday':    row(E('MATHS','ANURADHA'),E('HINDI','MAMTA SINHA'),E('ENG','NIKITA SINGH'),E('PT','BRAJESH'),E('SCIENCE','BETTY K'),E('AI LAB','SANJAY SH.'),E('GK','BETTY K.'),E('HINDI','MAMTA SINHA')),
'Saturday':  row(E('MPT','ANURADHA'),E('ENG','NIKITA SINGH'),E('HINDI','MAMTA SINHA'),E('SCIENCE','BETTY K'),E('AI','SANJAY SH.'),E('SST','MOHITA S.'),E('ACT','ANURADHA'),E('ACT','ANURADHA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 3B  (CT: MRS SHEETAL KHURANA)
# ════════════════════════════════════════════════════════════════
TT['3B'] = {
'Monday':    row(E('SCIENCE','SHEETAL KH.'),E('ENGLISH','RANI RANJAN'),E('HINDI','KRI. MADHU'),E('MATHS','ANURADHA'),E('ROBOTICS','MOHITA'),E('SST','ANANTA SINHA'),E('MATHS','ANURADHA'),E('HINDI','KRI. MADHU')),
'Tuesday':   row(E('SCIENCE','SHEETAL KH.'),E('ENGLISH','RANI RANJAN'),E('AI','SANJAY SH.'),E('MATHS','ANURADHA'),E('ART','SACHIN'),E('SST','ANANTA SINHA'),E('HINDI','KRI. MADHU'),E('ENGLISH','RANI RANJAN')),
'Wednesday': row(E('SCIENCE','SHEETAL KH.'),E('LIB','SUNITA'),E('HINDI','KRI. MADHU'),E('ENGLISH','RANI RANJAN'),E('MATHS','ANURADHA'),E('SST','ANANTA SINHA'),E('PT','MK RAHUL'),E('SCIENCE','SHEETAL KH.')),
'Thursday':  row(E('SCIENCE','SHEETAL KH.'),E('MUSIC','SHANKAR S.'),E('HINDI','KRI. MADHU'),E('MATHS','ANURADHA'),E('ENGLISH','RANI RANJAN'),E('SST','ANANTA SINHA'),E('AI','SANJAY SH.'),E('MSC','ANANTA SINHA')),
'Friday':    row(E('SCIENCE','SHEETAL KH.'),E('ENGLISH','RANI RANJAN'),E('HINDI','KRI. MADHU'),E('MATHS','ANURADHA'),E('SST','ANANTA SINHA'),E('ROBOTICS','MOHITA'),E('GK','ANURADHA'),E('MATHS','ANURADHA')),
'Saturday':  row(E('MPT','SHEETAL KH.'),E('ENGLISH','RANI RANJAN'),E('HINDI','KRI. MADHU'),E('AI LAB','SANJAY SH.'),E('MATHS','ANURADHA'),E('SST','ANANTA SINHA'),E('ACT','SHEETAL KH.'),E('ACT','SHEETAL KH.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 3C  (CT: MRS JYOTSNA)
# ════════════════════════════════════════════════════════════════
TT['3C'] = {
'Monday':    row(E('MATHS','JYOTSNA'),E('ENGLISH','TRIPTI'),E('LIB','SUNITA'),E('AI','SANJAY SH.'),E('HINDI','MAMTA SINHA'),E('SCIENCE','BETTY K.'),E('SST','ANANTA SINHA'),E('MATHS','JYOTSNA')),
'Tuesday':   row(E('MATHS','JYOTSNA'),E('AI LAB','SANJAY SH.'),E('ENGLISH','TRIPTI'),E('HINDI','MAMTA SINHA'),E('SST','ANANTA SINHA'),E('SCIENCE','BETTY K.'),E('ENGLISH','TRIPTI'),E('HINDI','MAMTA SINHA')),
'Wednesday': row(E('MATHS','JYOTSNA'),E('AI','SANJAY SH.'),E('ENGLISH','TRIPTI'),E('SCIENCE','BETTY K.'),E('MSC','BHAWNA D.'),E('HINDI','MAMTA SINHA'),E('SST','ANANTA SINHA'),E('MATHS','JYOTSNA')),
'Thursday':  row(E('MATHS','JYOTSNA'),E('ROBOTICS','MOHITA S'),E('ENGLISH','TRIPTI'),E('HINDI','MAMTA SINHA'),E('PT','BRAJESH'),E('SCIENCE','BETTY K.'),E('SST','ANANTA SINHA'),E('MUSIC','DEEPAK')),
'Friday':    row(E('MATHS','JYOTSNA'),E('ENGLISH','TRIPTI'),E('ART','SACHIN'),E('HINDI','MAMTA SINHA'),E('MATHS','JYOTSNA'),E('SCIENCE','BETTY K.'),E('GK','BHAWNA D.'),E('SST','ANANTA SINHA')),
'Saturday':  row(E('MPT','JYOTSNA'),E('ROBOTICS','MOHITA S'),E('SCIENCE','BETTY K.'),E('HINDI','MAMTA SINHA'),E('SST','ANANTA SINHA'),E('ENGLISH','TRIPTI'),E('ACT','JYOTSNA'),E('ACT','JYOTSNA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 3D  (CT: MRS RANI RANJAN)
# ════════════════════════════════════════════════════════════════
TT['3D'] = {
'Monday':    row(E('ENG','RANI RANJAN'),E('LIB','SUNITA'),E('SST','ANANTA SINHA'),E('ROBOTICS','TRIPTI'),E('SCIENCE','SHEETAL KH.'),E('HINDI','KRI MADHU'),E('MATHS','JYOTSANA'),E('ENG','RANI RANJAN')),
'Tuesday':   row(E('ENG','RANI RANJAN'),E('SST','ANANTA SINHA'),E('HINDI','KRI MADHU'),E('MATHS','JYOTSANA'),E('AI','AMIT KR.'),E('SCIENCE','SHEETAL KH.'),E('MATHS','JYOTSANA'),E('HINDI','KRI MADHU')),
'Wednesday': row(E('ENG','RANI RANJAN'),E('SST','ANANTA SINHA'),E('MATHS','JYOTSANA'),E('ROBOTICS','TRIPTI'),E('SCIENCE','SHEETAL KH.'),E('HINDI','KRI MADHU'),E('AI','AMIT KR.'),E('GK','ANANTA SINHA')),
'Thursday':  row(E('ENG','RANI RANJAN'),E('SST','ANANTA SINHA'),E('MSC','NIKITA SINGH'),E('MATHS','JYOTSANA'),E('SCIENCE','SHEETAL KH.'),E('HINDI','KRI MADHU'),E('MATHS','JYOTSANA'),E('SCIENCE','SHEETAL KH.')),
'Friday':    row(E('ENG','RANI RANJAN'),E('MUSIC','DEEPAK'),E('SST','ANANTA SINHA'),E('MATHS','JYOTSANA'),E('SCIENCE','SHEETAL KH.'),E('HINDI','KRI MADHU'),E('ENG','RANI RANJAN'),E('HINDI','KRI MADHU')),
'Saturday':  row(E('MPT','RANI RANJAN'),E('SST','ANANTA SINHA'),E('ART','SANGITA KRI.'),E('PT','MK RAHUL'),E('AI LAB','AMIT KR.'),E('MATHS','JYOTSANA'),E('ACT','RANI RANJAN'),E('ACT','RANI RANJAN')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 3E  (CT: MRS TRIPTI)
# ════════════════════════════════════════════════════════════════
TT['3E'] = {
'Monday':    row(E('ENG','TRIPTI'),E('AI LAB','AMIT KR.'),E('SST','MOHITA SINGH'),E('HINDI','KRI. MADHU'),E('MATHS','SUBOSH SINGH'),E('ENG','TRIPTI'),E('SCIENCE','PRATIBHA S.'),E('ROBOTICS','TRIPTI')),
'Tuesday':   row(E('ENG','TRIPTI'),E('LIB','SUNITA'),E('SST','MOHITA SINGH'),E('HINDI','KRI. MADHU'),E('MATHS','SUBOSH SINGH'),E('MUSIC','SHANKAR S.'),E('SCIENCE','PRATIBHA S.'),E('AI','AMIT KR.')),
'Wednesday': row(E('ROBOTICS','TRIPTI'),E('MATHS','SUBOSH SINGH'),E('ART','SANGITA KRI.'),E('HINDI','KRI. MADHU'),E('MATHS','SUBOSH SINGH'),E('ENG','TRIPTI'),E('SST','MOHITA SINGH'),E('SCIENCE','PRATIBHA S.')),
'Thursday':  row(E('ENG','TRIPTI'),E('AI','AMIT KR.'),E('SST','MOHITA SINGH'),E('HINDI','KRI. MADHU'),E('MATHS','SUBOSH SINGH'),E('MSC','TRIPTI'),E('SCIENCE','PRATIBHA S.'),E('HINDI','KRI. MADHU')),
'Friday':    row(E('ENG','TRIPTI'),E('SST','MOHITA SINGH'),E('MATHS','SUBOSH SINGH'),E('HINDI','KRI. MADHU'),E('MATHS','SUBOSH SINGH'),E('PT','BRAJESH'),E('SCIENCE','PRATIBHA S.'),E('GK','TRIPTI')),
'Saturday':  row(E('MPT','TRIPTI'),E('HINDI','KRI. MADHU'),E('SST','MOHITA SINGH'),E('ENG','TRIPTI'),E('MATHS','SUBOSH SINGH'),E('SCIENCE','PRATIBHA S.'),E('ACT','TRIPTI'),E('ACT','TRIPTI')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 3F  (CT: MRS NIKITA SINGH)
# ════════════════════════════════════════════════════════════════
TT['3F'] = {
'Monday':    row(E('ENGLISH','NIKITA SINGH'),E('SST','ANANTA SINHA'),E('MATHS','SUBOSH SINGH'),E('PT','BRAJESH'),E('HINDI','DIKSHA S.'),E('SCIENCE','PRATIBHA S.'),E('ENGLISH','NIKITA SINGH'),E('GK','RUPAM KRI.')),
'Tuesday':   row(E('ENGLISH','NIKITA SINGH'),E('ROBOTICS','PRATIBHA S.'),E('AI','AMIT KR.'),E('SST','ANANTA SINHA'),E('SCIENCE','PRATIBHA S.'),E('MATHS','SUBOSH SINGH'),E('HINDI','DIKSHA S.'),E('ENGLISH','NIKITA SINGH')),
'Wednesday': row(E('ENGLISH','NIKITA SINGH'),E('ROBOTICS','PRATIBHA S.'),E('MATHS','SUBOSH SINGH'),E('SST','ANANTA SINHA'),E('AI LAB','AMIT KR.'),E('MATHS','SUBOSH SINGH'),E('SCIENCE','PRATIBHA S.'),E('HINDI','DIKSHA S.')),
'Thursday':  row(E('ENGLISH','NIKITA SINGH'),E('SCIENCE','PRATIBHA S.'),E('AI','AMIT KR.'),E('SST','ANANTA SINHA'),E('HINDI','DIKSHA S.'),E('MATHS','SUBOSH SINGH'),E('HINDI','DIKSHA S.'),E('MUSIC','SHANKAR S.')),
'Friday':    row(E('ENGLISH','NIKITA SINGH'),E('HINDI','DIKSHA S.'),E('ART','SANGITA KRI.'),E('SST','ANANTA SINHA'),E('SCIENCE','PRATIBHA S.'),E('MATHS','SUBOSH SINGH'),E('MSC','TRIPTI'),E('LIB','SUNITA')),
'Saturday':  row(E('MPT','NIKITA SINGH'),E('SCIENCE','PRATIBHA S.'),E('MATHS','SUBOSH SINGH'),E('SST','ANANTA SINHA'),E('HINDI','DIKSHA S.'),E('MATHS','SUBOSH SINGH'),E('ACT','NIKITA SINGH'),E('ACT','NIKITA SINGH')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 2A  (CT: MRS APARNA)
# ════════════════════════════════════════════════════════════════
TT['2A'] = {
'Monday':    row(E('LIB','SUNITA M.'),E('AUDIO/VISUAL','APARNA K.'),E('MATHS','APARNA K.'),E('HINDI','APARNA K.'),E('EVS','APARNA K.'),E('GK','RUPAM KRI.'),E('MATHS','APARNA K.'),E('ENGLISH','APARNA K.')),
'Tuesday':   row(E('ENGLISH','APARNA K.'),E('EVS','APARNA K.'),E('MATHS','APARNA K.'),E('ART','SANGITA KRI.'),E('HINDI','APARNA K.'),E('ENGLISH','APARNA K.'),E('EVS','APARNA K.'),E('HINDI','APARNA K.')),
'Wednesday': row(E('ENGLISH','APARNA K.'),E('EVS','APARNA K.'),E('MATHS','APARNA K.'),E('EVS','APARNA K.'),E('HINDI','APARNA K.'),E('GK','RUPAM KRI.'),E('MATHS','APARNA K.'),E('ENGLISH','APARNA K.')),
'Thursday':  row(E('ENGLISH','APARNA K.'),E('AUDIO/VISUAL','APARNA K.'),E('MATHS','APARNA K.'),E('EVS','APARNA K.'),E('ART','SANGITA KRI.'),E('MSC','RUPAM KRI.'),E('MATHS','APARNA K.'),E('HINDI','APARNA K.')),
'Friday':    row(E('ENGLISH','APARNA K.'),E('EVS','APARNA K.'),E('MATHS','APARNA K.'),E('MUSIC','DEEPAK'),E('HINDI','APARNA K.'),E('MSC','RUPAM KRI.'),E('ENGLISH','APARNA K.'),E('HINDI','APARNA K.')),
'Saturday':  row(E('MPT','APARNA K.'),E('PT','BRAJESH S.'),E('ENG RECT','APARNA K.'),E('ENG WR/DICT/SPL','APARNA K.'),E('PD','APARNA K.'),E('HINDI RECT','APARNA K.'),E('ROBOTICS','APARNA K.'),E('ACT','APARNA K.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 2B  (CT: MRS MRIDULA PRASAD)
# ════════════════════════════════════════════════════════════════
TT['2B'] = {
'Monday':    row(E('MATHS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('HINDI','MRIDULA PD.'),E('ART','SACHIN'),E('EVS','MRIDULA PD.'),E('ROBOTICS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('MATHS','MRIDULA PD.')),
'Tuesday':   row(E('LIB','SUNITA M.'),E('MATHS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('ART','SACHIN'),E('EVS','MRIDULA PD.'),E('MSC','JYOTSANA'),E('AUDIO/VISUAL','JYOTSANA'),E('HINDI','MRIDULA PD.')),
'Wednesday': row(E('MATHS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('HINDI','MRIDULA PD.'),E('EVS','MRIDULA PD.'),E('EVS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('GK','BETTY K'),E('HINDI','MRIDULA PD.')),
'Thursday':  row(E('MATHS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('HINDI','MRIDULA PD.'),E('GK','BETTY K'),E('EVS','MRIDULA PD.'),E('AUDIO/VISUAL','MRIDULA PD.'),E('HINDI','MRIDULA PD.'),E('ENG','MRIDULA PD.')),
'Friday':    row(E('MATHS','MRIDULA PD.'),E('ENG','MRIDULA PD.'),E('MUSIC','DEEPAK'),E('HINDI','MRIDULA PD.'),E('EVS','MRIDULA PD.'),E('MSC','JYOTSANA'),E('EVS','MRIDULA PD.'),E('MATHS','MRIDULA PD.')),
'Saturday':  row(E('MPT','MRIDULA PD.'),E('PD','MRIDULA PD.'),E('ENG RECT','MRIDULA PD.'),E('ENG WR/DICT/SPL','MRIDULA PD.'),E('HINDI RECT','MRIDULA PD.'),E('PT','MUKESH R.'),E('ACT','MRIDULA PD.'),E('ACT','MRIDULA PD.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 2C  (CT: MRS RAJNI)
# ════════════════════════════════════════════════════════════════
TT['2C'] = {
'Monday':    row(E('MATHS','RAJNI K.'),E('ENG','RAJNI K.'),E('EVS','RAJNI K.'),E('HINDI','RAJNI K.'),E('GK','BETTY K'),E('EVS','RAJNI K.'),E('ENG','RAJNI K.'),E('MATHS','RAJNI K.')),
'Tuesday':   row(E('MATHS','RAJNI K.'),E('ART','SACHIN'),E('ENG','RAJNI K.'),E('HINDI','RAJNI K.'),E('MSC','JYOTSANA'),E('EVS','RAJNI K.'),E('ENG RECT','RANI RANJAN'),E('ENG','RAJNI K.')),
'Wednesday': row(E('LIB','SUNITA M.'),E('MATHS','RAJNI K.'),E('HINDI','RAJNI K.'),E('MUSIC','DEEPAK'),E('AUDIO/VISUAL','RAJNI K.'),E('EVS','RAJNI K.'),E('HINDI','RAJNI K.'),E('MATHS','RAJNI K.')),
'Thursday':  row(E('MATHS','RAJNI K.'),E('ENG','RAJNI K.'),E('ART','SACHIN'),E('HINDI','RAJNI K.'),E('MSC','JYOTSANA'),E('EVS','RAJNI K.'),E('MATHS','RAJNI K.'),E('HINDI','RAJNI K.')),
'Friday':    row(E('MATHS','RAJNI K.'),E('ENG','RAJNI K.'),E('EVS','RAJNI K.'),E('GK','BETTY K'),E('HINDI','RAJNI K.'),E('EVS','RAJNI K.'),E('AUDIO/VISUAL','RAJNI K.'),E('ENG','RAJNI K.')),
'Saturday':  row(E('MPT','RAJNI K.'),E('HINDI RECT','RAJNI K.'),E('PT','MUKESH R.'),E('ENG WR/DICT/SPL','RAJNI K.'),E('ROBOTICS','RAJNI K.'),E('PD','RAJNI K.'),E('ACT','RAJNI K.'),E('ACT','RAJNI K.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 2D  (CT: MRS RICHA MISHRA)
# ════════════════════════════════════════════════════════════════
TT['2D'] = {
'Monday':    row(E('EVS','RICHA MISHRA'),E('MUSIC','SHANKAR S.'),E('MATHS','RICHA MISHRA'),E('MSC','JYOTSANA'),E('GK','RICHA MISHRA'),E('HINDI','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('EVS','RICHA MISHRA')),
'Tuesday':   row(E('EVS','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('MATHS','RICHA MISHRA'),E('HINDI','RICHA MISHRA'),E('HINDI','RICHA MISHRA'),E('AUDIO/VISUAL','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('EVS','RICHA MISHRA')),
'Wednesday': row(E('EVS','RICHA MISHRA'),E('MATHS','RICHA MISHRA'),E('ART','SACHIN'),E('ENG','RICHA MISHRA'),E('MSC','JYOTSANA'),E('HINDI','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('MATHS','RICHA MISHRA')),
'Thursday':  row(E('LIB','SUNITA M.'),E('EVS','RICHA MISHRA'),E('MATHS','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('HINDI','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('AUDIO/VISUAL','RICHA MISHRA'),E('HINDI','RICHA MISHRA')),
'Friday':    row(E('EVS','RICHA MISHRA'),E('ART','SACHIN'),E('MATHS','RICHA MISHRA'),E('ENG RECT','RANI RANJAN'),E('GK','RICHA MISHRA'),E('HINDI','RICHA MISHRA'),E('ENG','RICHA MISHRA'),E('MATHS','RICHA MISHRA')),
'Saturday':  row(E('MPT','RICHA MISHRA'),E('PT','BRAJESH'),E('ENG RECT','RICHA MISHRA'),E('HINDI RECT','RICHA MISHRA'),E('ENG WR/DICT/SPL','RICHA MISHRA'),E('PD','RICHA MISHRA'),E('ROBOTICS','RICHA MISHRA'),E('ACT','RICHA MISHRA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 2E  (CT: MS VARSHA MISHRA)
# ════════════════════════════════════════════════════════════════
TT['2E'] = {
'Monday':    row(E('ENG','VARSHA'),E('MATHS','VARSHA'),E('EVS','VARSHA'),E('AUDIO/VISUAL','VARSHA'),E('MSC','JYOTSANA'),E('HINDI','VARSHA'),E('MATHS','VARSHA'),E('ENG','VARSHA')),
'Tuesday':   row(E('MATHS','VARSHA'),E('MATHS','VARSHA'),E('HINDI','VARSHA'),E('EVS','VARSHA'),E('EVS','VARSHA'),E('HINDI','VARSHA'),E('MUSIC','SHANKAR S.'),E('ENG','VARSHA')),
'Wednesday': row(E('ENG','VARSHA'),E('MSC','JYOTSANA'),E('HINDI','VARSHA'),E('ART','SACHIN'),E('MATHS','VARSHA'),E('AUDIO/VISUAL','VARSHA'),E('GK','RUNI'),E('MATHS','VARSHA')),
'Thursday':  row(E('ENG','VARSHA'),E('MATHS','VARSHA'),E('HINDI','VARSHA'),E('EVS','VARSHA'),E('ART','SACHIN'),E('HINDI','VARSHA'),E('EVS','VARSHA'),E('ENG','VARSHA')),
'Friday':    row(E('LIB','SUNITA M.'),E('ENG','VARSHA'),E('MATHS','VARSHA'),E('EVS','VARSHA'),E('GK','RUNI'),E('HINDI','VARSHA'),E('EVS','VARSHA'),E('MATHS','VARSHA')),
'Saturday':  row(E('ROBOTICS','VARSHA'),E('PD','VARSHA'),E('HINDI RECT','VARSHA'),E('ENG WR/DICT/SPL','VARSHA'),E('ENG RECT','RUNI'),E('PT','VARSHA'),E('ACT','VARSHA'),E('ACT','MUKESH R.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 2F  (CT: MRS JYOTI GUPTA)
# ════════════════════════════════════════════════════════════════
TT['2F'] = {
'Monday':    row(E('HINDI','JYOTI G.'),E('ENG','JYOTI G.'),E('MATHS','JYOTI G.'),E('LIB','SUNITA M.'),E('EVS','JYOTI G.'),E('GK','JYOTI G.'),E('ENG','JYOTI G.'),E('HINDI','JYOTI G.')),
'Tuesday':   row(E('HINDI','JYOTI G.'),E('EVS','JYOTI G.'),E('MATHS','JYOTI G.'),E('AUDIO/VISUAL','JYOTI G.'),E('EVS','JYOTI G.'),E('MSC','ANURADAHA S.'),E('ENG','JYOTI G.'),E('MATHS','JYOTI G.')),
'Wednesday': row(E('HINDI','JYOTI G.'),E('ENG','JYOTI G.'),E('MATHS','JYOTI G.'),E('AUDIO/VISUAL','JYOTI G.'),E('EVS','JYOTI G.'),E('ART','SACHIN'),E('ENG','JYOTI G.'),E('HINDI','JYOTI G.')),
'Thursday':  row(E('ENG','JYOTI G.'),E('ART','SACHIN'),E('EVS','JYOTI G.'),E('MATHS','JYOTI G.'),E('EVS','JYOTI G.'),E('HINDI','JYOTI G.'),E('ENG','JYOTI G.'),E('MATHS','JYOTI G.')),
'Friday':    row(E('HINDI','JYOTI G.'),E('GK','JYOTI G.'),E('MUSIC','SHANKAR S.'),E('MATHS','JYOTI G.'),E('EVS','JYOTI G.'),E('MSC','ANURADAHA S.'),E('ENG','JYOTI G.'),E('MATHS','JYOTI G.')),
'Saturday':  row(E('MPT','JYOTI G.'),E('ENG RECT','JYOTI G.'),E('PT','MUKESH R.'),E('ENG WR/DICT/SPL','JYOTI G.'),E('HINDI RECT','JYOTI G.'),E('PD','JYOTI G.'),E('ACT','JYOTI G.'),E('ROBOTICS','JYOTI G.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 1A  (CT: MRS BABY NEHA)
# ════════════════════════════════════════════════════════════════
TT['1A'] = {
'Monday':    row(E('EVS','BABY NEHA'),E('MATHS','BABY NEHA'),E('GK','BABY NEHA'),E('ENG','BABY NEHA'),E('HINDI','BABY NEHA'),E('AUDIO/VISUAL','BABY NEHA'),E('MUSIC','DEEPAK'),E('PT','SHABNAM M.')),
'Tuesday':   row(E('EVS','BABY NEHA'),E('MATHS','BABY NEHA'),E('HINDI','BABY NEHA'),E('ENG','BABY NEHA'),E('AUDIO/VISUAL','BABY NEHA'),E('MATHS','BABY NEHA'),E('LIB','SUNITA M.'),E('ENG','BABY NEHA')),
'Wednesday': row(E('EVS','BABY NEHA'),E('MATHS','BABY NEHA'),E('MSC','ANURADAHA S'),E('ENG','BABY NEHA'),E('HINDI','BABY NEHA'),E('EVS','BABY NEHA'),E('ENG','BABY NEHA'),E('ART','SHABNAM M.')),
'Thursday':  row(E('HINDI','BABY NEHA'),E('MATHS','BABY NEHA'),E('GK','BABY NEHA'),E('ENG','BABY NEHA'),E('HINDI','BABY NEHA'),E('EVS','BABY NEHA'),E('ENG','BABY NEHA'),E('MATHS','BABY NEHA')),
'Friday':    row(E('EVS','BABY NEHA'),E('MATHS','BABY NEHA'),E('ENG','BABY NEHA'),E('HINDI','BABY NEHA'),E('MSC','ANURADAHA S'),E('EVS','BABY NEHA'),E('HINDI','BABY NEHA'),E('ART','SHABNAM M.')),
'Saturday':  row(E('MPT','BABY NEHA'),E('ENG RECT','BABY NEHA'),E('PD','BABY NEHA'),E('ENG WR/DICT/SPL','BABY NEHA'),E('HINDI RECT','BABY NEHA'),E('HINDI WR/DICT/SPL','BABY NEHA'),E('ROBOTICS','BABY NEHA'),E('ACT','BABY NEHA')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 1B  (CT: MRS SANSKRITI PRAKASH)
# ════════════════════════════════════════════════════════════════
TT['1B'] = {
'Monday':    row(E('ENG','SANSKRITI'),E('MATHS','SANSKRITI'),E('EVS','SANSKRITI'),E('MATHS','SANSKRITI'),E('EVS','SANSKRITI'),E('HINDI','SANSKRITI'),E('AUDIO/VISUAL','SANSKRITI'),E('ART','SONALI K.')),
'Tuesday':   row(E('ENG','SANSKRITI'),E('MATHS','SANSKRITI'),E('HINDI','SANSKRITI'),E('EVS','SANSKRITI'),E('GK','SANSKRITI'),E('HINDI','SANSKRITI'),E('ENG','SANSKRITI'),E('MATHS','SANSKRITI')),
'Wednesday': row(E('HINDI','SANSKRITI'),E('MATHS','SANSKRITI'),E('ENG','SANSKRITI'),E('EVS','SANSKRITI'),E('ENG','SANSKRITI'),E('GK','SANSKRITI'),E('MSC','ANURADHA S.'),E('PT','SONALI K.')),
'Thursday':  row(E('ENG','SANSKRITI'),E('EVS','SANSKRITI'),E('LIB','SUNITA M.'),E('MATHS','SANSKRITI'),E('EVS','SANSKRITI'),E('HINDI','SANSKRITI'),E('MSC','ANURADHA S.'),E('ART','SONALI K.')),
'Friday':    row(E('HINDI','SANSKRITI'),E('ROBOTICS','SANSKRITI'),E('ENG','SANSKRITI'),E('EVS','SANSKRITI'),E('AUDIO/VISUAL','SANSKRITI'),E('HINDI','SANSKRITI'),E('MATHS','SANSKRITI'),E('MUSIC','DEEPAK')),
'Saturday':  row(E('MPT','SANSKRITI'),E('ENG RECT','SANSKRITI'),E('PD','SANSKRITI'),E('ENG WR/DICT/SPL','SANSKRITI'),E('HINDI RECT','SANSKRITI'),E('HINDI WR/DICT/SPL','SANSKRITI'),E('ACT','SANSKRITI'),E('ACT','SANSKRITI')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 1C  (CT: MRS RUBY SINGH)
# ════════════════════════════════════════════════════════════════
TT['1C'] = {
'Monday':    row(E('ENG','RUBY SINGH'),E('EVS','RUBY SINGH'),E('MATHS','RUBY SINGH'),E('MSC','PRATIBHA'),E('AUDIO/VISUAL','RUBY SINGH'),E('HINDI','RUBY SINGH'),E('EVS','RUBY SINGH'),E('ART','NIDHI AG')),
'Tuesday':   row(E('ENG','RUBY SINGH'),E('EVS','RUBY SINGH'),E('MATHS','RUBY SINGH'),E('MUSIC','DEEPAK'),E('MATHS','RUBY SINGH'),E('HINDI','RUBY SINGH'),E('EVS','RUBY SINGH'),E('ART','NIDHI AG')),
'Wednesday': row(E('HINDI','RUBY SINGH'),E('EVS','RUBY SINGH'),E('MATHS','RUBY SINGH'),E('ENG','RUBY SINGH'),E('ROBOTICS','RUBY SINGH'),E('MSC','PRATIBHA'),E('AUDIO/VISUAL','RUBY SINGH'),E('HINDI','RUBY SINGH')),
'Thursday':  row(E('HINDI','RUBY SINGH'),E('EVS','RUBY SINGH'),E('ENG','RUBY SINGH'),E('GK','RUBY SINGH'),E('LIB','SUNITA M.'),E('HINDI','RUBY SINGH'),E('ENG','RUBY SINGH'),E('MATHS','RUBY SINGH')),
'Friday':    row(E('ENG','RUBY SINGH'),E('EVS','RUBY SINGH'),E('MATHS','RUBY SINGH'),E('HINDI','RUBY SINGH'),E('ENG','RUBY SINGH'),E('GK','RUBY SINGH'),E('MATHS','RUBY SINGH'),E('PT','NIDHI AG')),
'Saturday':  row(E('MPT','RUBY SINGH'),E('ENG RECT','RUBY SINGH'),E('PD','RUBY SINGH'),E('ENG WR/DICT/SPL','RUBY SINGH'),E('HINDI RECT','RUBY SINGH'),E('HINDI WR/DICT/SPL','RUBY SINGH'),E('ACT','RUBY SINGH'),E('ACT','RUBY SINGH')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 1D  (CT: MRS MEETU KUMARI)
# ════════════════════════════════════════════════════════════════
TT['1D'] = {
'Monday':    row(E('MATHS','MEETU'),E('ENG','MEETU'),E('GK','MEETU'),E('EVS','MEETU'),E('LIB','SUNITA M.'),E('HINDI','MEETU'),E('EVS','MEETU'),E('MATHS','MEETU')),
'Tuesday':   row(E('HINDI','MEETU'),E('GK','MEETU'),E('ENG','MEETU'),E('EVS','MEETU'),E('ENG','MEETU'),E('HINDI','MEETU'),E('MATHS','MEETU'),E('ART','RUPA S.')),
'Wednesday': row(E('MATHS','MEETU'),E('ENG','MEETU'),E('HINDI','MEETU'),E('EVS','MEETU'),E('ENG','MEETU'),E('HINDI','MEETU'),E('EVS','MEETU'),E('MATHS','MEETU')),
'Thursday':  row(E('HINDI','MEETU'),E('ENG','MEETU'),E('ROBOTICS','MEETU'),E('MSC','ARCHITA'),E('AUDIO/VISUAL','MEETU'),E('EVS','MEETU'),E('MATHS','MEETU'),E('PT','RUPA S.')),
'Friday':    row(E('MATHS','MEETU'),E('MUSIC','SHANKAR S.'),E('ENG','MEETU'),E('MSC','ARCHITA'),E('EVS','MEETU'),E('AUDIO/VISUAL','MEETU'),E('HINDI','MEETU'),E('ART','RUPA S.')),
'Saturday':  row(E('MPT','MEETU'),E('ENG RECT','MEETU'),E('PD','MEETU'),E('ENG WR/DICT/SPL','MEETU'),E('HINDI RECT','MEETU'),E('HINDI WR/DICT/SPL','MEETU'),E('ACT','MEETU'),E('ACT','MEETU')),
}

# ════════════════════════════════════════════════════════════════
# CLASS 1E  (CT: MRS DIKSHA SANDILAYA)
# ════════════════════════════════════════════════════════════════
TT['1E'] = {
'Monday':    row(E('HINDI','DIKSHA S.'),E('ROBOTICS','DIKSHA S.'),E('ENG','NIKITA S.'),E('EVS','DIKSHA S.'),E('MSC','ANURADHA S.'),E('ENG','NIKITA S.'),E('MATHS','DIKSHA S.'),E('EVS','DIKSHA S.')),
'Tuesday':   row(E('HINDI','DIKSHA S.'),E('MATHS','DIKSHA S.'),E('GK','DIKSHA S.'),E('EVS','DIKSHA S.'),E('HINDI','DIKSHA S.'),E('MATHS','DIKSHA S.'),E('ENG','NIKITA S.'),E('PT','ANKITA S.')),
'Wednesday': row(E('HINDI','DIKSHA S.'),E('MATHS','NIKITA S.'),E('ENG','NIKITA S.'),E('EVS','DIKSHA S.'),E('LIB','SUNITA M.'),E('MSC','ANURADHA S.'),E('EVS','DIKSHA S.'),E('ART','ANKITA S.')),
'Thursday':  row(E('HINDI','DIKSHA S.'),E('EVS','DIKSHA S.'),E('GK','DIKSHA S.'),E('AUDIO/VISUAL','DIKSHA S.'),E('MUSIC','SHANKAR S.'),E('ENG','NIKITA S.'),E('EVS','DIKSHA S.'),E('ART','ANKITA S.')),
'Friday':    row(E('HINDI','DIKSHA S.'),E('ENG','NIKITA S.'),E('MATHS','DIKSHA S.'),E('AUDIO/VISUAL','DIKSHA S.'),E('MATHS','DIKSHA S.'),E('ENG','NIKITA S.'),E('EVS','DIKSHA S.'),E('HINDI','DIKSHA S.')),
'Saturday':  row(E('MPT','DIKSHA S.'),E('HINDI RECT','DIKSHA S.'),E('PD','DIKSHA S.'),E('ENG WR/DICT/SPL','DIKSHA S.'),E('HINDI WR/DICT/SPL','DIKSHA S.'),E('ENG RECT','PALLAVI'),E('ACT','DIKSHA S.'),E('ACT','DIKSHA S.')),
}

# ════════════════════════════════════════════════════════════════
# CLASS NURSERY  (CT: MRS NIDHI AGRAWAL) — uses P2,P3,P5,P6 only
# ════════════════════════════════════════════════════════════════
TT['NURSERY'] = {
'Monday':    [None,E('ENG WR','NIDHI'),E('EVS','NIDHI'),None,E('NUM WORK','NIDHI'),E('DANCE','NIDHI'),None,None],
'Tuesday':   [None,E('NUM WORK','NIDHI'),E('SMART','NIDHI'),None,E('HINDI DICT/WR','NIDHI'),E('ENG','NIDHI'),None,None],
'Wednesday': [None,E('HINDI','NIDHI'),E('EVS','NIDHI'),None,E('ART/CRAFT','NIDHI'),E('GAME','NIDHI'),None,None],
'Thursday':  [None,E('ENG','NIDHI'),E('SMART','NIDHI'),None,E('HINDI DICT/WR','NIDHI'),E('SINGING','NIDHI'),None,None],
'Friday':    [None,E('HINDI','NIDHI'),E('ENG','NIDHI'),None,E('NUM WORK','NIDHI'),E('STORY TELLING','NIDHI'),None,None],
'Saturday':  [None,E('ENG WR/ORAL','NIDHI'),E('EVS','NIDHI'),None,E('ACT','NIDHI'),E('ACT','NIDHI'),None,None],
}

# ════════════════════════════════════════════════════════════════
# CLASS LKG  (CT: MRS RUPA SINGH) — uses P2,P3,P5,P6 only
# ════════════════════════════════════════════════════════════════
TT['LKG'] = {
'Monday':    [None,E('ENG WR/ORAL','RUPA'),E('SMART','RUPA'),None,E('NUM WORK','RUPA'),E('GAME','RUPA'),None,None],
'Tuesday':   [None,E('NUM WORK','RUPA'),E('EVS','RUPA'),None,E('HINDI DICT/WR','RUPA'),E('ENG','RUPA'),None,None],
'Wednesday': [None,E('HINDI','RUPA'),E('SMART','RUPA'),None,E('ART/CRAFT','RUPA'),E('DANCE','RUPA'),None,None],
'Thursday':  [None,E('ENG','RUPA'),E('EVS','RUPA'),None,E('HINDI DICT/WR','RUPA'),E('SINGING','RUPA'),None,None],
'Friday':    [None,E('HINDI','RUPA'),E('ENG','RUPA'),None,E('NUM WORK','RUPA'),E('STORY TELLING','RUPA'),None,None],
'Saturday':  [None,E('ENG WR','RUPA'),E('EVS','RUPA'),None,E('ACT','RUPA'),E('ACT','RUPA'),None,None],
}

# ════════════════════════════════════════════════════════════════
# CLASS UKG A  (CT: MRS SHABNAM MIRAJ) — uses P2,P3,P5,P6 only
# ════════════════════════════════════════════════════════════════
TT['UKG A'] = {
'Monday':    [None,E('ENG WR/ORAL','SHABNAM'),E('EVS','SHABNAM'),None,E('NUM WORK','SHABNAM'),E('DANCE','SHABNAM'),None,None],
'Tuesday':   [None,E('SMART','SHABNAM'),E('NUM WORK','SHABNAM'),None,E('HINDI DICT/WR','SHABNAM'),E('GAME','SHABNAM'),None,None],
'Wednesday': [None,E('HINDI','SHABNAM'),E('EVS','SHABNAM'),None,E('ART/CRAFT','SHABNAM'),E('ENG','SHABNAM'),None,None],
'Thursday':  [None,E('HINDI','SHABNAM'),E('ENG','SHABNAM'),None,E('HINDI DICT/WR','SHABNAM'),E('SINGING','SHABNAM'),None,None],
'Friday':    [None,E('SMART','SHABNAM'),E('ENG','SHABNAM'),None,E('NUM WORK','SHABNAM'),E('STORY TELLING','SHABNAM'),None,None],
'Saturday':  [None,E('ENG WR/ORAL','SHABNAM'),E('EVS','SHABNAM'),None,E('ACT','SHABNAM'),E('ACT','SHABNAM'),None,None],
}

# ════════════════════════════════════════════════════════════════
# CLASS UKG B  (CT: MRS ANKITA SNEHI) — uses P2,P3,P5,P6 only
# ════════════════════════════════════════════════════════════════
TT['UKG B'] = {
'Monday':    [None,E('ENG WR','ANKITA'),E('EVS','ANKITA'),None,E('NUM WORK','ANKITA'),E('DANCE','ANKITA'),None,None],
'Tuesday':   [None,E('NUM WORK','ANKITA'),E('EVS','ANKITA'),None,E('HINDI WR','ANKITA'),E('ENG','ANKITA'),None,None],
'Wednesday': [None,E('HINDI','ANKITA'),E('ENG','ANKITA'),None,E('ART/CRAFT','ANKITA'),E('STORY TELLING','ANKITA'),None,None],
'Thursday':  [None,E('ENG','ANKITA'),E('EVS','ANKITA'),None,E('HINDI DICT/WR','ANKITA'),E('SINGING','ANKITA'),None,None],
'Friday':    [None,E('HINDI','ANKITA'),E('SMART','ANKITA'),None,E('NUM WORK','ANKITA'),E('GAME','ANKITA'),None,None],
'Saturday':  [None,E('SMART','ANKITA'),E('ENG WR/ORAL','ANKITA'),None,E('ACT','ANKITA'),E('ACT','ANKITA'),None,None],
}

# ════════════════════════════════════════════════════════════════
# CLASS UKG C  (CT: MRS KUMARI SALONI) — uses P2,P3,P5,P6 only
# ════════════════════════════════════════════════════════════════
TT['UKG C'] = {
'Monday':    [None,E('ENG WR/ORAL','SALONI'),E('EVS','SALONI'),None,E('NUM WORK','SALONI'),E('DANCE','SALONI'),None,None],
'Tuesday':   [None,E('HINDI','SALONI'),E('NUM WORK','SALONI'),None,E('HINDI DICT/WR','SALONI'),E('ENG','SALONI'),None,None],
'Wednesday': [None,E('SMART','SALONI'),E('ENG','SALONI'),None,E('ART/CRAFT','SALONI'),E('GAME','SALONI'),None,None],
'Thursday':  [None,E('ENG','SALONI'),E('EVS','SALONI'),None,E('HINDI DICT/WR','SALONI'),E('SINGING','SALONI'),None,None],
'Friday':    [None,E('EVS','SALONI'),E('HINDI','SALONI'),None,E('NUM WORK','SALONI'),E('STORY TELLING','SALONI'),None,None],
'Saturday':  [None,E('ENG WR','SALONI'),E('SMART','SALONI'),None,E('ACT','SALONI'),E('ACT','SALONI'),None,None],
}

# ─── period name mapping ─────────────────────────────────────────────────────
PERIOD_NAMES = ['P1','P2','P3','P4','P5','P6','P7','P8']

# ─── import logic ────────────────────────────────────────────────────────────
inserted = 0
skipped  = 0
errors   = 0
unknown_teacher = set()
unknown_subject = set()

for class_name, days in TT.items():
    cid = class_by_name.get(class_name)
    if not cid:
        print(f"[SKIP] Class not found in DB: {class_name}")
        continue

    # Fetch existing (day, period_name, teacher_id) for this class
    existing_rows = get('timetable', {'select':'day,period_name,teacher_id', 'class_id': f'eq.{cid}'})
    existing = set((r['day'], r['period_name'], r['teacher_id']) for r in existing_rows)

    for day, periods in days.items():
        for pi, entry in enumerate(periods):
            if entry is None:
                continue
            subj_abbr, tch_abbr = entry
            pname = PERIOD_NAMES[pi]

            # Resolve teacher
            tid = T.get(tch_abbr)
            if tid is None:
                unknown_teacher.add(tch_abbr)
                skipped += 1
                continue

            # Resolve subject
            sid = subj(subj_abbr)
            if sid is None:
                unknown_subject.add(subj_abbr)
                skipped += 1
                continue

            # Skip if already exists for this class+day+period+teacher
            if (day, pname, tid) in existing:
                skipped += 1
                continue

            # Insert
            row_data = {
                'class_id': cid,
                'day': day,
                'period_name': pname,
                'teacher_id': tid,
                'subject_id': sid,
                'room_type': 'CLASSROOM',
            }
            status = post_one('timetable', row_data)
            if status in (200, 201):
                inserted += 1
                existing.add((day, pname, tid))   # avoid re-inserting in same run
            elif status == 409:
                # teacher already has this slot in another class — skip
                skipped += 1
            else:
                r2 = httpx.post(f'{URL}/timetable',
                                headers={**H,'Prefer':'return=minimal'},
                                json=row_data, verify=False)
                print(f"  ERR {r2.status_code} {class_name} {day} {pname} tch={tid}: {r2.text[:80]}")
                errors += 1

print(f"\n{'='*60}")
print(f"Done. Inserted={inserted}  Skipped={skipped}  Errors={errors}")
if unknown_teacher:
    print(f"\nUnknown teachers (need mapping): {sorted(unknown_teacher)}")
if unknown_subject:
    print(f"\nUnknown subjects (need mapping): {sorted(unknown_subject)}")
