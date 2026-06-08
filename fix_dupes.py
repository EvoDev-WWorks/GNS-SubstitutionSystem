"""
Fix duplicate LIB entries caused by the LIB migration.
Where the same class has TWO different LIB teachers for the same day+period,
keep the one with teacher T110 (SUNITA KUMARI) and delete the T111/T112 duplicate.
"""
import httpx, warnings
warnings.filterwarnings('ignore')
URL='https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'
KEY='sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V'
H={'apikey':KEY,'Authorization':f'Bearer {KEY}','Content-Type':'application/json'}

# Get all timetable rows with subject=LIB
rows = httpx.get(f'{URL}/timetable',headers=H,params={
    'select':'id,class_id,day,period_name,teacher_id',
    'subject_id':'eq.6','limit':'2000'},verify=False).json()

from collections import defaultdict
# Group by class+day+period
slots = defaultdict(list)
for r in rows:
    key = f"{r['class_id']}__{r['day']}__{r['period_name']}"
    slots[key].append(r)

deleted = 0
for key, entries in slots.items():
    if len(entries) <= 1:
        continue
    # Keep the one with teacher_id=110 (SUNITA), delete others
    keep_ids = {e['id'] for e in entries if e['teacher_id'] == 110}
    if not keep_ids:
        # No T110 — keep the first, delete rest
        keep_ids = {entries[0]['id']}
    for e in entries:
        if e['id'] not in keep_ids:
            r = httpx.delete(f'{URL}/timetable', headers=H,
                params={'id': f'eq.{e["id"]}'}, verify=False)
            if r.status_code in (200,204):
                print(f"Deleted id={e['id']} class={e['class_id']} {e['day']} {e['period_name']} teacher={e['teacher_id']}")
                deleted += 1
            else:
                print(f"ERR {r.status_code}: {r.text[:60]}")

print(f'\nDone. Deleted {deleted} duplicate LIB entries.')
