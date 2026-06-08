"""Fetch teachers, subjects, classes from Supabase for building import mappings."""
import httpx, warnings, json
warnings.filterwarnings('ignore')
URL='https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'
KEY='sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V'
H={'apikey':KEY,'Authorization':f'Bearer {KEY}'}

teachers = httpx.get(f'{URL}/teachers',headers=H,params={'select':'id,teacher_no,full_name,abbreviation','limit':'500'},verify=False).json()
subjects = httpx.get(f'{URL}/subjects',headers=H,params={'select':'id,code,name','limit':'200'},verify=False).json()
classes  = httpx.get(f'{URL}/classes',headers=H,params={'select':'id,name','limit':'500'},verify=False).json()

print("=== TEACHERS ===")
for t in sorted(teachers, key=lambda x: x['id']):
    print(f"  id={t['id']}  no={t['teacher_no']}  abbr={t.get('abbreviation','')}  name={t['full_name']}")

print("\n=== SUBJECTS ===")
for s in sorted(subjects, key=lambda x: x['id']):
    print(f"  id={s['id']}  code={s['code']}  name={s['name']}")

print("\n=== CLASSES ===")
for c in sorted(classes, key=lambda x: x['name']):
    print(f"  id={c['id']}  name={c['name']}")
