-- Run this in Supabase SQL Editor to verify all tables
SELECT 'teachers'      AS table_name, COUNT(*) AS rows FROM teachers
UNION ALL
SELECT 'subjects',      COUNT(*) FROM subjects
UNION ALL
SELECT 'classes',       COUNT(*) FROM classes
UNION ALL
SELECT 'timetable',     COUNT(*) FROM timetable
UNION ALL
SELECT 'gk_msc',        COUNT(*) FROM gk_msc
UNION ALL
SELECT 'class_teachers',COUNT(*) FROM class_teachers
UNION ALL
SELECT 'period_config', COUNT(*) FROM period_config
UNION ALL
SELECT 'labs',          COUNT(*) FROM labs
ORDER BY table_name;
