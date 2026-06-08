-- Run this ONCE in Supabase SQL Editor
-- Creates 2 helper functions used by the substitution optimizer

-- Function 1: teacher grades across all classes they teach
CREATE OR REPLACE FUNCTION get_teacher_grades()
RETURNS TABLE(teacher_id int, grade int, grade_band text)
LANGUAGE sql SECURITY DEFINER AS $$
  SELECT DISTINCT t.teacher_id, c.grade, c.grade_band
  FROM timetable t
  JOIN classes c ON c.id = t.class_id
  WHERE t.teacher_id IS NOT NULL;
$$;

-- Function 2: total weekly period count per teacher
CREATE OR REPLACE FUNCTION get_weekly_load()
RETURNS TABLE(teacher_id int, cnt bigint)
LANGUAGE sql SECURITY DEFINER AS $$
  SELECT teacher_id, COUNT(*) AS cnt
  FROM timetable
  WHERE teacher_id IS NOT NULL
  GROUP BY teacher_id;
$$;
