import os
import httpx
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_PROJECT_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

tid = 77
r = httpx.get(f"{SUPABASE_URL}/rest/v1/timetable?teacher_id=eq.{tid}&select=*,classes(*)", headers=headers)
for row in r.json():
    print(f"ID: {row['id']} | Day: {row['day_of_week']}, Period: {row['period_name']}, Class: {row['classes']['name']}, Grade: {row['classes']['grade']}")
