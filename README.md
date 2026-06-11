# GNS Substitution System

**Teacher Substitution Management System**  
Gyan Niketan School — Session 2026–27

Automatically recommends substitute teachers using Google OR-Tools CP-SAT optimizer the moment a teacher is marked absent — respecting all school rules, load limits, and subject preferences.

---

## What it does

- Mark one or multiple teachers as absent for a date
- OR-Tools optimizer finds the best available substitute for every vacant period simultaneously
- Applies 10 substitution rules (same subject, same stream, load balancing, etc.)
- Generates a printable substitution report in seconds

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML / CSS / JS (embedded in Python) |
| Backend | FastAPI (Python) |
| Optimizer | Google OR-Tools CP-SAT |
| Database | Supabase (PostgreSQL) |
| Desktop | pywebview (native app window) |

---

## Project Structure

```
GNS-SubstitutionSystem/
│
├── app.py                    # Main app — FastAPI + OR-Tools + UI
├── launch.py                 # Desktop launcher (pywebview)
├── START.bat                 # Double-click to run
├── SETUP.bat                 # First-time setup
├── .env.example              # Credentials template
│
├── database/
│   ├── schema.sql            # Create all tables
│   ├── drop_tables.sql       # Drop all tables
│   ├── supabase_functions.sql# Optimizer SQL functions
│   ├── verify_supabase.sql   # Row count check
│   └── seed/
│       ├── seed_data.sql     # All teachers, timetable, subjects etc.
│       └── class_teachers.sql# Class-teacher mappings
│
├── etl/                      # One-time data prep scripts (run once per academic year)
│   ├── etl_supabase.py
│   ├── build_final_csv.py
│   ├── gen_class_teachers.py
│   └── generate_import_csvs.py
│
└── data/                     # Source CSV files
    ├── master_timetable.csv
    ├── teacher_master.csv
    ├── CT 2026-27.csv
    └── gk_msc_master.csv
```

---

## First-time Setup

### 1. Clone the repo
```bash
git clone https://github.com/EvoDev-WWorks/GNS-SubstitutionSystem.git
cd GNS-SubstitutionSystem
```

### 2. Add Supabase credentials
Copy `.env.example` to `.env` and fill in your credentials:
```
SUPABASE_PROJECT_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_XXXXXXXXXXXXXXXXXXXX
```

Then update the same values in `app.py`:
```python
SUPABASE_PROJECT_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_SERVICE_KEY = "your_service_role_key"
```

### 3. Set up Supabase database
Run these files in order in your Supabase SQL Editor:

| Step | File |
|---|---|
| 1 | `database/schema.sql` |
| 2 | `database/seed/seed_data.sql` |
| 3 | `database/seed/class_teachers.sql` |
| 4 | `database/supabase_functions.sql` |
| 5 | `database/verify_supabase.sql` (check row counts) |

### 4. Install dependencies & run
Double-click `SETUP.bat` (first time only), then `START.bat` to launch.

---

## Running the App

Double-click **`START.bat`**

The app opens as a **native desktop window** (no browser needed).  
Also accessible on school LAN at `http://<PC_IP>:8000`

---

## Substitution Rules (OR-Tools CP-SAT)

### Hard Constraints
| Rule | Description |
|---|---|
| Principal / VP excluded | Never assigned as substitute |
| No double-booking | Teacher already teaching that period is skipped |
| Daily cap | Max 7 periods per teacher per day |
| Load spreading | Max 2 substitution periods per teacher per day |

### Soft Scoring
| Rule | Score |
|---|---|
| Same subject | +35 |
| Same stream (Class 11/12) | +40 |
| Same grade band | +25 |
| Grade proximity (within 2) | +20 |
| Grade proximity (within 4) | +5 |
| Too far from grade level | −15 |
| Senior teacher to junior class | −5 |
| PT teacher for grade 10/11/12 | −30 |
| Existing load penalty | −8 per class |
| Weekly overload (>35 periods) | −10 |

---

## Period Rules

| Grade Band | Valid Periods |
|---|---|
| NURSERY | P2 – P6 |
| LOWER (1–5) | P1 – P8 |
| MIDDLE (6–10) | P1 – P8 |
| HIGHER (11–12) | α1, α2, P1 – P4 |

---

## Database Tables

| Table | Description | Rows |
|---|---|---|
| teachers | All 134 teachers | 134 |
| classes | All classes | 299 |
| timetable | Full weekly timetable | 4743 |
| subjects | Subject codes | 20 |
| class_teachers | Class-teacher mappings | 91 |
| gk_msc | GK / MSC assignments | 56 |
| period_config | Active periods per grade band | 40 |
| labs | Lab definitions | 5 |
| absences | Absence records (runtime) | — |
| substitutions | Substitution records (runtime) | — |

---
