

# Bölümler (departments)
DEPARTMENTS_SQL = """
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
"""

# Kullanıcılar (users)
USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'koordinator')),
    department_id INTEGER NULL,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);
"""

# Derslikler (classrooms)

CLASSROOMS_SQL = """
CREATE TABLE IF NOT EXISTS classrooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dept_id INTEGER NOT NULL,
    code TEXT NOT NULL,                  -- ör: 3001, 301, LAB-1
    name TEXT NOT NULL,                  -- ör: Bilgisayar Lab-1
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    rows INTEGER NOT NULL CHECK (rows > 0),
    cols INTEGER NOT NULL CHECK (cols > 0),
    seats_per_desk INTEGER NOT NULL CHECK (seats_per_desk IN (2,3)),
    UNIQUE(dept_id, code),
    FOREIGN KEY (dept_id) REFERENCES departments(id)
);
"""

CLASSROOMS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_classrooms_dept ON classrooms(dept_id);
"""
STUDENTS_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dept_id INTEGER NOT NULL,
    number TEXT NOT NULL,
    full_name TEXT NOT NULL,
    class_year INTEGER NOT NULL CHECK (class_year BETWEEN 1 AND 8),
    UNIQUE(dept_id, number),
    FOREIGN KEY (dept_id) REFERENCES departments(id)
);
CREATE INDEX IF NOT EXISTS idx_students_dept   ON students(dept_id);
CREATE INDEX IF NOT EXISTS idx_students_num    ON students(number);
"""


COURSES_SQL = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dept_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    instructor TEXT,
    class_year INTEGER NOT NULL CHECK (class_year BETWEEN 1 AND 8),
    is_compulsory INTEGER NOT NULL DEFAULT 1, -- 1: zorunlu, 0: seçmeli
    UNIQUE(dept_id, code),
    FOREIGN KEY (dept_id) REFERENCES departments(id)
);
CREATE INDEX IF NOT EXISTS idx_courses_dept ON courses(dept_id);
CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code);
"""


ENROLLMENTS_SQL = """
CREATE TABLE IF NOT EXISTS enrollments (
    student_id INTEGER NOT NULL,
    course_id  INTEGER NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_enroll_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enroll_course  ON enrollments(course_id);
"""
# exams – her ders için sınav kaydı (tarih/saat/yer)
EXAMS_SQL = """
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    exam_start TEXT NOT NULL,    -- ISO: '2025-01-15 09:00'
    duration_min INTEGER NOT NULL DEFAULT 120,
    room_id INTEGER NULL,
    UNIQUE(course_id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (room_id) REFERENCES classrooms(id)
);
CREATE INDEX IF NOT EXISTS idx_exams_start ON exams(exam_start);
"""
