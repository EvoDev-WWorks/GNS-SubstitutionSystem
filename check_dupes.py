import httpx, warnings
warnings.filterwarnings('ignore')
URL='https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'
KEY='sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V'
H={'apikey':KEY,'Authorization':f'Bearer {KEY}'}

# Get all classes to check broadly
all_classes = httpx.get(f'{URL}/classes',headers=H,params={'select':'id,name','limit':'2000'},verify=False).json()
name_to_id = {c['name']:c['id'] for c in all_classes}

cid = name_to_id['10E']
rows = httpx.get(f'{URL}/timetable',headers=H,params={
    'select':'id,day,period_name,room_type,teachers(teacher_no,full_name),subjects(code)',
    'class_id':f'eq.{cid}','order':'day.asc,period_name.asc','limit':'200'},verify=False).json()

from collections import defaultdict
slots = defaultdict(list)
for r in rows:
    key = r['day']+'__'+r['period_name']
    slots[key].append(r)

print('DUPLICATE SLOTS for 10E:')
for k,v in sorted(slots.items()):
    if len(v)>1:
        for r in v:
            t=(r.get('teachers') or {})
            s=(r.get('subjects') or {})
            rid = r['id']
            day = r['day']
            per = r['period_name']
            room = r['room_type']
            tname = t.get('full_name','?')
            scode = s.get('code','?')
            print(f"  id={rid}  {day} {per}  room={room}  {tname} / {scode}")
        print()

print('MISSING periods vs full P1-P8 per day:')
DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
ALL=['P1','P2','P3','P4','P5','P6','P7','P8']
for day in DAYS:
    have=set(r['period_name'] for r in rows if r['day']==day)
    missing=[p for p in ALL if p not in have]
    if missing:
        print(f"  {day}: missing {missing}")
