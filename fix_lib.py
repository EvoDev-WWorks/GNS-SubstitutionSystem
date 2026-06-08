"""
Fix LIB periods: update class_id on existing timetable rows from
fake "1A LIB" class → real "1A" class, for all LIB classes.
"""
import httpx, warnings
warnings.filterwarnings('ignore')

URL = 'https://lvsdwybkfvzioykhnfai.supabase.co/rest/v1'
KEY = 'sb_secret_PRxcOI5xO1eG05s2DMIyYQ_uf1rtw8V'
H   = {'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'}

# Get all classes
classes = httpx.get(f'{URL}/classes', headers=H,
    params={'select':'id,name','limit':'2000'}, verify=False).json()
name_to_id = {c['name']: c['id'] for c in classes}

# All fake "X LIB" classes
lib_classes = [c for c in classes if c['name'].endswith(' LIB')]
print(f'Found {len(lib_classes)} LIB fake classes\n')

updated = 0
missing = 0

for lc in lib_classes:
    real_name = lc['name'].replace(' LIB', '')
    real_id   = name_to_id.get(real_name)
    if not real_id:
        print(f'  NO REAL CLASS: {lc["name"]}')
        missing += 1
        continue

    # Update all timetable rows for this fake class → point to real class
    r = httpx.patch(
        f'{URL}/timetable',
        headers={**H, 'Prefer': 'return=minimal'},
        params={'class_id': f'eq.{lc["id"]}'},
        json={'class_id': real_id},
        verify=False
    )
    if r.status_code in (200, 201, 204):
        updated += 1
        print(f'  ✓ {lc["name"]} → {real_name}')
    else:
        print(f'  ERR {r.status_code} on {lc["name"]}: {r.text[:80]}')

print(f'\nDone. Updated {updated} classes, {missing} missing real class.')
