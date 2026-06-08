-- Run this FIRST to clear all existing tables
-- Then run schema.sql, then seed_data.sql

DROP TABLE IF EXISTS daily_load        CASCADE;
DROP TABLE IF EXISTS substitutions     CASCADE;
DROP TABLE IF EXISTS absences          CASCADE;
DROP TABLE IF EXISTS gk_msc            CASCADE;
DROP TABLE IF EXISTS timetable         CASCADE;
DROP TABLE IF EXISTS labs              CASCADE;
DROP TABLE IF EXISTS period_config     CASCADE;
DROP TABLE IF EXISTS class_teachers    CASCADE;
DROP TABLE IF EXISTS classes           CASCADE;
DROP TABLE IF EXISTS teacher_subjects  CASCADE;
DROP TABLE IF EXISTS teachers          CASCADE;
DROP TABLE IF EXISTS subjects          CASCADE;
