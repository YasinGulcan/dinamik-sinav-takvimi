# src/ui/data_status_view.py
# Veri Durumu: sayımlar + eksikler + çakışmalar + kapasite kontrolü (PDF akışına uygun)

import tkinter as tk
from tkinter import ttk, messagebox
from core.db import get_conn


class DataStatusView(ttk.Frame):


    def __init__(self, master, user=None, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user or {}
        self.dept_id = self.user.get("department_id") or 1

        # Üst: Sayım kartları
        cards = ttk.Frame(self); cards.pack(fill="x", padx=10, pady=(10, 6))
        self.lbl_courses = self._card(cards, "Ders", 0)
        self.lbl_students = self._card(cards, "Öğrenci", 1)
        self.lbl_exams = self._card(cards, "Sınav", 2)
        self.lbl_rooms = self._card(cards, "Derslik", 3)

        # Sekmeler
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tab_missing = ttk.Frame(nb)
        self.tab_conflict = ttk.Frame(nb)
        self.tab_capacity = ttk.Frame(nb)
        nb.add(self.tab_missing, text="Eksikler")
        nb.add(self.tab_conflict, text="Çakışmalar")
        nb.add(self.tab_capacity, text="Kapasite")

        # Eksikler sekmesi
        self.tree_noexam = self._make_tree(self.tab_missing, ("code", "name", "year"), ("Kod", "Ad", "Sınıf"))
        self.tree_noroom = self._make_tree(self.tab_missing, ("code", "name", "start"),
                                           ("Kod", "Ad", "Başlangıç"))
        ttk.Label(self.tab_missing, text="Sınavı olmayan dersler").pack(anchor="w", padx=4, pady=(6, 0))
        self.tree_noexam.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        ttk.Label(self.tab_missing, text="Odasız sınavlar").pack(anchor="w", padx=4, pady=(6, 0))
        self.tree_noroom.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # Çakışmalar sekmesi
        self.tree_stu_conf = self._make_tree(
            self.tab_conflict,
            ("student_no", "student_name", "course1", "course2", "start"),
            ("Öğrenci No", "Ad Soyad", "Ders 1", "Ders 2", "Zaman"))
        self.tree_room_conf = self._make_tree(
            self.tab_conflict,
            ("room", "course1", "course2", "start"),
            ("Derslik", "Ders 1", "Ders 2", "Zaman"))
        ttk.Label(self.tab_conflict, text="Öğrenci çakışmaları (aynı saatte birden fazla sınav)").pack(anchor="w", padx=4, pady=(6, 0))
        self.tree_stu_conf.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        ttk.Label(self.tab_conflict, text="Derslik çakışmaları (aynı saatte aynı derslikte birden fazla sınav)").pack(anchor="w", padx=4, pady=(6, 0))
        self.tree_room_conf.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # Kapasite sekmesi
        self.tree_capacity = self._make_tree(
            self.tab_capacity,
            ("code", "name", "start", "room", "need", "cap"),
            ("Kod", "Ad", "Zaman", "Derslik", "Öğrenci", "Kapasite"))
        ttk.Label(self.tab_capacity, text="Kapasite yetersiz sınavlar").pack(anchor="w", padx=4, pady=(6, 0))
        self.tree_capacity.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # Çift tık detay bilgi
        self.tree_noexam.bind("<Double-1>", lambda e: self._row_info(self.tree_noexam))
        self.tree_noroom.bind("<Double-1>", lambda e: self._row_info(self.tree_noroom))
        self.tree_stu_conf.bind("<Double-1>", lambda e: self._row_info(self.tree_stu_conf))
        self.tree_room_conf.bind("<Double-1>", lambda e: self._row_info(self.tree_room_conf))
        self.tree_capacity.bind("<Double-1>", lambda e: self._row_info(self.tree_capacity))

        self.refresh()

    # ---------------- UI yardımcıları ----------------

    def _card(self, parent, title, col):
        f = ttk.Frame(parent, relief="groove", padding=8)
        f.grid(row=0, column=col, padx=6, sticky="ew")
        parent.grid_columnconfigure(col, weight=1)
        ttk.Label(f, text=title, font=("", 10, "bold")).pack(anchor="w")
        lbl = ttk.Label(f, text="-", font=("", 12))
        lbl.pack(anchor="w")
        return lbl

    @staticmethod
    def _make_tree(parent, cols, headers):
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        for c, h in zip(cols, headers):
            tree.heading(c, text=h)
            tree.column(c, width=140 if c not in ("name",) else 240)
        return tree

    @staticmethod
    def _row_info(tree: ttk.Treeview):
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        messagebox.showinfo("Detay", "\n".join(str(v) for v in vals))

    # ---------------- Veri çekme / hesaplama ----------------

    def refresh(self):
        # Sayımlar
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM courses WHERE dept_id=?", (self.dept_id,))
            n_courses = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM students WHERE dept_id=?", (self.dept_id,))
            n_students = cur.fetchone()[0]
            # exams bölüme course üzerinden bağlı
            cur.execute("""
                SELECT COUNT(*)
                FROM exams e
                JOIN courses c ON c.id = e.course_id
                WHERE c.dept_id=?
            """, (self.dept_id,))
            n_exams = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM classrooms WHERE dept_id=?", (self.dept_id,))
            n_rooms = cur.fetchone()[0]

        self.lbl_courses.config(text=str(n_courses))
        self.lbl_students.config(text=str(n_students))
        self.lbl_exams.config(text=str(n_exams))
        self.lbl_rooms.config(text=str(n_rooms))

        # Listeleri doldur
        self._load_missing()
        self._load_conflicts()
        self._load_capacity()

    def _load_missing(self):
        for t in (self.tree_noexam, self.tree_noroom):
            for i in t.get_children(): t.delete(i)
        with get_conn() as con:
            cur = con.cursor()
            # Sınavı olmayan dersler
            cur.execute("""
                SELECT c.code, c.name, c.class_year
                FROM courses c
                LEFT JOIN exams e ON e.course_id = c.id
                WHERE c.dept_id=? AND e.id IS NULL
                ORDER BY c.class_year, c.code
            """, (self.dept_id,))
            for r in cur.fetchall():
                self.tree_noexam.insert("", "end", values=r)

            # Odası olmayan sınavlar
            cur.execute("""
                SELECT c.code, c.name, e.exam_start
                FROM exams e
                JOIN courses c ON c.id = e.course_id
                WHERE c.dept_id=? AND e.room_id IS NULL
                ORDER BY e.exam_start, c.code
            """, (self.dept_id,))
            for r in cur.fetchall():
                self.tree_noroom.insert("", "end", values=r)

    def _load_conflicts(self):
        for t in (self.tree_stu_conf, self.tree_room_conf):
            for i in t.get_children(): t.delete(i)
        with get_conn() as con:
            cur = con.cursor()
            # Öğrenci çakışmaları (aynı anda iki dersin sınavı)
            cur.execute("""
                WITH enroll AS (
                    SELECT DISTINCT student_id, course_id FROM enrollments
                )
                SELECT
                    s.number AS student_no,
                    s.full_name AS student_name,
                    c1.code AS course1,
                    c2.code AS course2,
                    ex1.exam_start AS start
                FROM enroll e1
                JOIN enroll e2
                     ON e1.student_id = e2.student_id
                    AND e1.course_id  < e2.course_id
                JOIN exams  ex1 ON ex1.course_id = e1.course_id
                JOIN exams  ex2 ON ex2.course_id = e2.course_id
                               AND ex1.exam_start = ex2.exam_start
                JOIN courses c1 ON c1.id = e1.course_id AND c1.dept_id = ?
                JOIN courses c2 ON c2.id = e2.course_id AND c2.dept_id = ?
                JOIN students s ON s.id = e1.student_id
                ORDER BY ex1.exam_start, s.number
            """, (self.dept_id, self.dept_id))
            for r in cur.fetchall():
                self.tree_stu_conf.insert("", "end", values=r)

            # Derslik çakışmaları (aynı ts + aynı room_id, 1'den fazla sınav)
            cur.execute("""
                SELECT cl.code AS room,
                       MIN(c.code) AS course1,
                       MAX(c.code) AS course2,
                       e.exam_start AS start
                FROM exams e
                JOIN courses c ON c.id = e.course_id
                LEFT JOIN classrooms cl ON cl.id = e.room_id
                WHERE c.dept_id=? AND e.room_id IS NOT NULL
                GROUP BY e.exam_start, e.room_id
                HAVING COUNT(*) > 1
                ORDER BY e.exam_start, room
            """, (self.dept_id,))
            for r in cur.fetchall():
                self.tree_room_conf.insert("", "end", values=r)

    def _load_capacity(self):
        for i in self.tree_capacity.get_children(): self.tree_capacity.delete(i)
        with get_conn() as con:
            cur = con.cursor()
            # Sınav öğrenci sayısı vs derslik kapasitesi
            cur.execute("""
                WITH need AS (
                    SELECT e.id AS exam_id,
                           COUNT(en.student_id) AS n
                    FROM exams e
                    JOIN courses c ON c.id = e.course_id
                    LEFT JOIN enrollments en ON en.course_id = c.id
                    WHERE c.dept_id=?
                    GROUP BY e.id
                )
                SELECT c.code, c.name, e.exam_start,
                       COALESCE(cl.code, '') AS room_code,
                       n.n AS need,
                       COALESCE(cl.capacity, 0) AS cap
                FROM exams e
                JOIN courses c ON c.id = e.course_id
                LEFT JOIN classrooms cl ON cl.id = e.room_id
                LEFT JOIN need n ON n.exam_id = e.id
                WHERE c.dept_id=?
                ORDER BY e.exam_start, c.code
            """, (self.dept_id, self.dept_id))
            rows = cur.fetchall()

        # sadece kapasite yetersizleri göster
        for code, name, start, room_code, need, cap in rows:
            try:
                need_i = int(need or 0)
                cap_i  = int(cap or 0)
            except Exception:
                need_i, cap_i = (0, 0)
            if cap_i and need_i > cap_i:
                self.tree_capacity.insert("", "end",
                                          values=(code, name, start, room_code, need_i, cap_i))
