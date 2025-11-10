import sqlite3
from pathlib import Path
import hashlib
from . import models
from contextlib import contextmanager

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "data" / "app.db"


# --- basit sha256 şifreleme ---
def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


@contextmanager
def get_conn():
    """SQLite bağlantısı oluşturur, foreign key açık, otomatik commit/rollback yapar."""
    con = sqlite3.connect(DB_PATH.as_posix())
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    """Tabloları oluşturur ve başlangıç verilerini ekler."""

    with get_conn() as con:
        cur = con.cursor()

        # 1) Tablolar
        cur.execute(models.DEPARTMENTS_SQL)
        cur.execute(models.USERS_SQL)
        cur.execute(models.CLASSROOMS_SQL)
        cur.execute(models.CLASSROOMS_INDEX_SQL)
        cur.executescript(models.STUDENTS_SQL)
        cur.executescript(models.COURSES_SQL)
        cur.executescript(models.ENROLLMENTS_SQL)
        cur.executescript(models.EXAMS_SQL)

        _ensure_unique_course_index(con)
        con.commit()

        _add_exam_type_column_if_missing(con)  # <-- BURAYA EKLE
        con.commit()

    with get_conn() as con:
        _add_capacity_pdf_column_if_missing(con)

    # 2) Tek noktadan seed
    seed_admin()
    seed_demo_coordinator()  # ✅ yeni eklendi

def _ensure_unique_course_index(conn):
    cur = conn.cursor()
    # 1) Aynı bölümde aynı koddan çoğul kayıt varsa fazlaları sil (ilk id kalsın)
    cur.execute("""
        WITH dups AS (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                         PARTITION BY dept_id, UPPER(REPLACE(code,' ','')) 
                         ORDER BY id
                       ) AS rn
                FROM courses
            )
            WHERE rn > 1
        )
        DELETE FROM courses WHERE id IN (SELECT id FROM dups)
    """)
    # 2) UNIQUE index
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_courses_dept_code
        ON courses(dept_id, code)
    """)
    conn.commit()



def verify_user(email: str, password: str):
    """email+şifre doğruysa kullanıcıyı döndürür"""
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, email, role, department_id, password_hash FROM users WHERE email=?", (email,))
        row = cur.fetchone()
        if not row:
            return None
        uid, e, role, dept_id, pw_hash = row
        if pw_hash == _hash_pw(password):
            return {"id": uid, "email": e, "role": role, "department_id": dept_id}
        return None


def seed_admin():
    """Bölümleri ve varsayılan admin kullanıcısını ekler."""
    departments = [
        "Bilgisayar Mühendisliği",
        "Yazılım Mühendisliği",
        "Elektrik Mühendisliği",
        "Elektronik Mühendisliği",
        "İnşaat Mühendisliği",
    ]

    admin_email = "admin@kocaeli.edu.tr"
    admin_password = "Admin123!"

    with get_conn() as con:
        cur = con.cursor()

        # Bölümleri ekle (varsa atla)
        for name in departments:
            cur.execute("INSERT OR IGNORE INTO departments(name) VALUES(?)", (name,))

        # Admin var mı kontrol et
        cur.execute("SELECT 1 FROM users WHERE email=?", (admin_email,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO users(email, password_hash, role, department_id)
                VALUES (?, ?, 'admin', NULL)
            """, (admin_email, _hash_pw(admin_password)))

        con.commit()


def seed_demo_coordinator():
    """Bölüm koordinatörü örneği ekler."""
    email = "koor.bilgisayar@kocaeli.edu.tr"
    password = "Koor123!"

    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM departments WHERE name=?", ("Bilgisayar Mühendisliği",))
        row = cur.fetchone()
        if not row:
            return
        dept_id = row[0]

        cur.execute("SELECT 1 FROM users WHERE email=?", (email,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO users(email, password_hash, role, department_id)
                VALUES (?, ?, 'koordinator', ?)
            """, (email, _hash_pw(password), dept_id))

        con.commit()

def _add_exam_type_column_if_missing(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(exams);")
    cols = [row[1] for row in cur.fetchall()]  # sütun adları
    if "exam_type" not in cols:
        cur.execute("ALTER TABLE exams ADD COLUMN exam_type TEXT DEFAULT 'Vize';")
        conn.commit()

def _add_capacity_pdf_column_if_missing(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(classrooms);")
    cols = [row[1] for row in cur.fetchall()]
    if "capacity_pdf" not in cols:
        cur.execute("ALTER TABLE classrooms ADD COLUMN capacity_pdf INTEGER;")
        conn.commit()
