-- ============================================================
-- Gyan Niketan School — Substitution System
-- Run this in Supabase SQL Editor FIRST, then import CSVs
-- ============================================================

CREATE TABLE IF NOT EXISTS subjects (
    id   SERIAL PRIMARY KEY,
    code TEXT   UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id           SERIAL PRIMARY KEY,
    teacher_no   TEXT   UNIQUE NOT NULL,
    full_name    TEXT   NOT NULL,
    subject      TEXT,
    designation  TEXT   DEFAULT 'TEACHER',
    abbreviation TEXT,
    is_excluded  BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS teacher_subjects (
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (teacher_id, subject_id)
);

CREATE TABLE IF NOT EXISTS classes (
    id         SERIAL PRIMARY KEY,
    name       TEXT   UNIQUE NOT NULL,
    grade      INTEGER,
    section    TEXT,
    grade_band TEXT
);

CREATE TABLE IF NOT EXISTS class_teachers (
    class_id   INTEGER REFERENCES classes(id)  ON DELETE CASCADE,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    PRIMARY KEY (class_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS period_config (
    id           SERIAL PRIMARY KEY,
    grade_band   TEXT NOT NULL,
    period_name  TEXT NOT NULL,
    period_order INTEGER NOT NULL,
    is_alpha     BOOLEAN DEFAULT FALSE,
    is_active    BOOLEAN DEFAULT TRUE,
    UNIQUE (grade_band, period_name)
);

CREATE TABLE IF NOT EXISTS labs (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    lab_type TEXT NOT NULL,
    block    TEXT,
    sub_type TEXT
);

CREATE TABLE IF NOT EXISTS timetable (
    id           SERIAL PRIMARY KEY,
    class_id     INTEGER REFERENCES classes(id)  ON DELETE CASCADE,
    teacher_id   INTEGER REFERENCES teachers(id),
    subject_id   INTEGER REFERENCES subjects(id),
    day          TEXT NOT NULL,
    period_name  TEXT NOT NULL,
    room_type    TEXT DEFAULT 'CLASSROOM',
    is_practical BOOLEAN DEFAULT FALSE,
    lab_section  TEXT,
    UNIQUE (teacher_id, day, period_name, room_type)
);

CREATE TABLE IF NOT EXISTS gk_msc (
    id             SERIAL PRIMARY KEY,
    class_id       INTEGER REFERENCES classes(id) ON DELETE CASCADE,
    gk_teacher_id  INTEGER REFERENCES teachers(id),
    msc_teacher_id INTEGER REFERENCES teachers(id),
    UNIQUE (class_id)
);

CREATE TABLE IF NOT EXISTS absences (
    id           SERIAL PRIMARY KEY,
    teacher_id   INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    absence_date DATE    NOT NULL,
    day_of_week  TEXT    NOT NULL,
    reason       TEXT,
    marked_by    TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (teacher_id, absence_date)
);

CREATE TABLE IF NOT EXISTS substitutions (
    id                    SERIAL PRIMARY KEY,
    absence_id            INTEGER REFERENCES absences(id) ON DELETE CASCADE,
    class_id              INTEGER REFERENCES classes(id),
    period_name           TEXT NOT NULL,
    absent_teacher_id     INTEGER REFERENCES teachers(id),
    substitute_teacher_id INTEGER REFERENCES teachers(id),
    subject_id            INTEGER REFERENCES subjects(id),
    room_type             TEXT DEFAULT 'CLASSROOM',
    score                 INTEGER DEFAULT 0,
    reason                TEXT,
    status                TEXT DEFAULT 'SUGGESTED',
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_load (
    id                   SERIAL PRIMARY KEY,
    teacher_id           INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    load_date            DATE NOT NULL,
    regular_classes      INTEGER DEFAULT 0,
    substitution_classes INTEGER DEFAULT 0,
    UNIQUE (teacher_id, load_date)
);
