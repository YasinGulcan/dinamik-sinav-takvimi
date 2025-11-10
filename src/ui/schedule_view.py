# src/ui/schedule_view.py
# Sınav Programı: listeleme + otomatik plan + çakışma kontrolü + elle düzenleme + otomatik oda atama

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from core.db import get_conn


class ScheduleView(ttk.Frame):
    def __init__(self, master, user, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user

        # ---- Rol / Bölüm filtresi (yalnız admin) ----
        self.is_admin = (self.user or {}).get("role") == "admin"
        self.dept_filter_var = tk.StringVar(value="")
        self._dept_list = []          # [(id, name)]
        self._dept_name_to_id = {}    # {"Bilgisayar Mühendisliği": 1, ...}

        def _load_departments():
            with get_conn() as con:
                cur = con.cursor()
                cur.execute("SELECT id, name FROM departments ORDER BY name")
                rows = cur.fetchall() or []
            self._dept_list = rows
            self._dept_name_to_id = {name: did for (did, name) in rows}
            if rows and not self.dept_filter_var.get():
                # admin için bir başlangıç değeri seç
                self.dept_filter_var.set(rows[0][1])

        if self.is_admin:
            _load_departments()

        # ÜST BAR
        # Başlık
        title = ttk.Label(self, text="Sınav Programı", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", padx=12, pady=(10, 0))

        # Toolbar
        from ui.widgets import Toolbar
        tb = Toolbar(self)
        tb.add_left("Otomatik Planla", self.auto_plan)
        tb.add_left("Çakışma Hesapla", self.check_conflicts)
        tb.add_left("Otomatik Oda Ata", self.auto_assign_rooms)
        tb.add_left("Saat/Derslik Düzenle", self.edit_selected_exam)

        tb.add_right("Kısıtlar", self.open_constraints)
        tb.add_right("Programı PDF", self.export_program_pdf)
        tb.add_right("PDF Kaydet", self.export_pdf)
        tb.add_right("Excel Dışa Aktar", self.export_excel)
        tb.add_right("Sınavları Temizle", self.clear_plan)
        tb.add_right("Oturma Planı", self.open_seating)

        # Admin'e "Bölüm" filtresi
        if self.is_admin:
            dept_box = ttk.Frame(self)
            dept_box.pack(fill="x", padx=10, pady=(0, 6))
            ttk.Label(dept_box, text="Bölüm:").pack(side="left")
            ttk.Combobox(
                dept_box,
                textvariable=self.dept_filter_var,
                values=[name for (_id, name) in self._dept_list],
                state="readonly",
                width=32
            ).pack(side="left", padx=6)
            ttk.Button(dept_box, text="Uygula", command=self.refresh).pack(side="left")

        # Kısıtlar için varsayılanlar
        self.constraints = {
            "date_start": None,             # datetime.date
            "date_end": None,               # datetime.date
            "exclude_days": set(),          # {5,6} -> Cts/Paz
            "default_duration": 75,         # dk
            "cooldown_min": 15,             # öğrenci başına min bekleme (dk)
            "single_exam_at_a_time": False, # aynı anda yalnızca tek sınav
            "exam_type": "Vize",            # not: şimdilik kayıt amaçlı
            "excluded_courses": set(),
        }

        # BİLGİ ETİKETİ
        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=10, pady=(0, 6))

        # TreeView: gizli exam_id ilk sütun (PDF gereği satırdan tekil kimlik ile çalışacağız)
        cols = ("exam_id", "course", "name", "year", "start", "room")
        headers = ("ID", "Kod", "Ad", "Sınıf", "Başlangıç", "DerslikID")

        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=18)
        for c, h in zip(cols, headers):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=100)
        from ui.ui_theme import enable_treeview_features
        enable_treeview_features(self.tree)

        # ID’yi GİZLE
        self.tree.column("exam_id", width=0, minwidth=0, stretch=False)

        self.tree.pack(fill="both", expand=True, padx=10, pady=8)
        # Çift tıkla düzenleme (detay penceresi) — seçim kesinleşsin
        self.tree.bind("<Double-1>", lambda e: self.after(1, self.edit_selected_exam))
        # Bilgi etiketi (toplam ders / plan sayısı)
        self.info = ttk.Label(self, text="", foreground="#444", font=("Segoe UI", 9, "italic"))
        self.info.pack(anchor="w", padx=12, pady=(0, 4))

        self.refresh()

    # ----------------- YARDIMCI -----------------

    def _active_dept_id(self):
        """Admin için combobox’tan seçilen bölüm; koordinator için kendi bölümü."""
        if self.is_admin:
            return self._dept_name_to_id.get(self.dept_filter_var.get())
        return (self.user or {}).get("department_id") or 1

    def _dept_clause(self, table_alias: str):
        role = (self.user or {}).get("role")
        dept_id = (self.user or {}).get("department_id")
        if role == "admin" or dept_id is None:
            return "", ()
        return f" AND {table_alias}.dept_id=?", (dept_id,)

    # ----------------- MESAJ FORMATLAYICILAR (PDF uyumlu) -----------------

    def _fmt_hhmm(self, ts: str) -> str:
        if not ts:
            return ""
        s = str(ts)
        try:
            if len(s) >= 16:
                return s[:16]
        except Exception:
            pass
        return s

    def _msg_capacity(self, code: str, room: str, need: int, maxcap: int, ts: str) -> str:
        ts_s = self._fmt_hhmm(ts)
        return f"Ders {code} için {room} kapasitesi yetersiz (ihtiyaç: {need}, bu slotta en fazla: {maxcap}) — {ts_s}"

    def _msg_no_room(self, code: str, need: int, ts: str) -> str:
        ts_s = self._fmt_hhmm(ts)
        return f"{code} için uygun boş derslik yok (ihtiyaç: {need}) — {ts_s}"

    def _msg_conflicts_summary(self, total: int, per_slot_rows: list, examples: list) -> str:
        if total == 0:
            return "✅ Hiç çakışma bulunamadı."
        parts = [f"⚠️ {total} çakışma bulundu.", ""]
        if per_slot_rows:
            parts.append("— Zamanlara göre sayım —")
            for ts, cnt in per_slot_rows:
                parts.append(f"  {self._fmt_hhmm(ts)}: {cnt}")
            parts.append("")
        if examples:
            parts.append("Örnekler (ilk 5):")
            for num, ad, c1, c2, ts in examples[:5]:
                parts.append(f"  {num} - {ad}: {c1} ve {c2} ({self._fmt_hhmm(ts)})")
        return "\n".join(parts)

    # ----------------- TEMEL İŞLEMLER -----------------

    def refresh(self):
        # tabloyu temizle
        for i in self.tree.get_children():
            self.tree.delete(i)

        dept_id = self._active_dept_id()

        where_dept = " AND c.dept_id=?" if dept_id else ""
        params = (dept_id,) if dept_id else tuple()

        sql = f"""
            SELECT
                e.id           AS exam_id,
                c.code         AS course,
                c.name         AS name,
                c.class_year   AS class_year,
                e.exam_start   AS exam_start,
                e.room_id      AS room_id
            FROM courses c
            LEFT JOIN exams e ON e.course_id = c.id
            WHERE 1=1
            {where_dept}
            ORDER BY c.class_year, c.code
        """
        with get_conn() as con:
            cur = con.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

            # info: bölüm adı
            dept_name = None
            if dept_id:
                cur.execute("SELECT name FROM departments WHERE id=?", (dept_id,))
                r = cur.fetchone()
                dept_name = r[0] if r and r[0] else f"Bölüm {dept_id}"
            else:
                dept_name = "Tüm Bölümler"

        # rows: (exam_id, course, name, class_year, exam_start, room_id)
        for r in rows:
            exam_id, course, name, class_year, exam_start, room_id = r
            self.tree.insert("", "end", values=(exam_id, course, name, class_year, exam_start, room_id))

        planned = sum(1 for r in rows if r[4])  # r[4] = exam_start
        self.info.config(text=f"[{dept_name}] Toplam ders: {len(rows)} | Planlanan sınav: {planned}")

    def export_program_pdf(self):
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
        except Exception:
            messagebox.showerror("PDF", "reportlab kurulu değil. Kur: pip install reportlab")
            return

        dept_id = self._active_dept_id()

        # Bölüm adı (varsa) — yoksa "Tüm Bölümler"
        with get_conn() as con:
            cur = con.cursor()
            dept_name = "Tüm Bölümler"
            if dept_id:
                cur.execute("SELECT name FROM departments WHERE id=?", (dept_id,))
                r = cur.fetchone()
                if r and r[0]:
                    dept_name = r[0]

            # Program verisi
            where_dept = "WHERE c.dept_id=?" if dept_id else ""
            params = (dept_id,) if dept_id else tuple()
            cur.execute(f"""
                SELECT
                    DATE(e.exam_start) AS d,
                    TIME(e.exam_start) AS t,
                    c.code,
                    c.name,
                    c.class_year,
                    COALESCE(cl.code,'') AS room
                FROM exams e
                JOIN courses c ON c.id = e.course_id
                LEFT JOIN classrooms cl ON cl.id = e.room_id
                {where_dept}
                ORDER BY d, t, c.class_year, c.code
            """, params)
            rows = cur.fetchall()

        if not rows:
            messagebox.showinfo("Programı PDF", "Kaydedilecek sınav bulunamadı.")
            return

        # Tarih aralığı (başlık altı için)
        dates = [r[0] for r in rows if r[0]]
        date_span = ""
        if dates:
            dmin = min(dates)
            dmax = max(dates)
            date_span = f"{dmin} — {dmax}"

        # PDF kurulumu
        out_dir = "data"
        import os
        os.makedirs(out_dir, exist_ok=True)
        fname = f"sinav_programi_{dept_id or 'tum'}_{datetime.now():%Y%m%d_%H%M}.pdf"
        out_path = os.path.join(out_dir, fname)

        c = canvas.Canvas(out_path, pagesize=landscape(A4))
        page_w, page_h = landscape(A4)

        left = 1.6 * cm
        right = 1.6 * cm
        top = 1.6 * cm
        bottom = 1.2 * cm

        def weekday_tr(dstr: str) -> str:
            try:
                d = datetime.strptime(dstr, "%Y-%m-%d").date()
                names = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cts", "Paz"]
                return names[d.weekday()]
            except Exception:
                return ""

        title = "Sınav Programı"
        subtitle = f"{dept_name}"
        if date_span:
            subtitle += f"  •  {date_span}"
        etype = (getattr(self, "constraints", {}) or {}).get("exam_type")
        if etype:
            subtitle += f"  •  {etype}"

        headers = ["Saat", "Kod", "Ad", "Sınıf", "Derslik"]
        widths = [3.0 * cm, 3.5 * cm, 13.0 * cm, 2.5 * cm, 3.5 * cm]
        x0 = left
        x_positions = [x0]
        for w in widths[:-1]:
            x_positions.append(x_positions[-1] + w)

        line_h = 0.6 * cm

        def draw_page_header():
            y = page_h - top
            c.setFont("Helvetica-Bold", 16)
            c.drawString(left, y, title)
            c.setFont("Helvetica", 10)
            c.drawRightString(page_w - right, y, f"Oluşturma: {datetime.now():%Y-%m-%d %H:%M}")
            y -= 0.7 * cm
            c.setFont("Helvetica", 11)
            c.drawString(left, y, subtitle)
            return y - 0.5 * cm

        def draw_day_header(day_str, y):
            c.setFont("Helvetica-Bold", 11)
            wd = weekday_tr(day_str)
            c.drawString(left, y, f"{day_str}  ({wd})")
            y -= 0.35 * cm
            c.setFont("Helvetica-Bold", 9)
            for i, h in enumerate(headers):
                c.drawString(x_positions[i], y, h)
            y -= 0.2 * cm
            c.line(left, y, page_w - right, y)
            return y - 0.2 * cm

        def ensure_space(y, need_lines=1):
            needed = need_lines * line_h + 1.2 * cm
            if y - needed < bottom:
                c.showPage()
                return draw_page_header(), True
            return y, False

        y = draw_page_header()

        from itertools import groupby
        def key_day(r): return r[0]

        for day, group in groupby(rows, key=key_day):
            y, _ = ensure_space(y, need_lines=3)
            y = draw_day_header(day, y)

            c.setFont("Helvetica", 9)
            for rec in list(group):
                _d, t, code, name, cy, room = rec
                y, newp = ensure_space(y, need_lines=1)
                if newp:
                    y = draw_day_header(day, y)

                vals = [
                    (t or "")[:5],
                    str(code or ""),
                    str(name or "")[:90],
                    str(cy or ""),
                    str(room or ""),
                ]
                for i, val in enumerate(vals):
                    c.drawString(x_positions[i], y, val)
                y -= line_h

        c.showPage()
        c.save()

        messagebox.showinfo("Programı PDF", f"PDF başarıyla kaydedildi:\n{out_path}")

    def export_seating_pdf(self):
        messagebox.showinfo("Oturma Planı (PDF)", "Oturma planı PDF çıktısı bu sürümde devre dışı.")

    def clear_plan(self):
        """Sınav kayıtlarını siler (admin: tüm bölümler ya da seçili bölüm, koordinator: kendi bölümü)."""
        dept_id = self._active_dept_id()

        with get_conn() as con:
            cur = con.cursor()
            if self.is_admin and not dept_id:
                # admin + 'tüm bölümler' seçili ise her şeyi temizle
                cur.execute("DELETE FROM exams")
            else:
                cur.execute("""
                    DELETE FROM exams
                    WHERE course_id IN (SELECT id FROM courses WHERE dept_id = ?)
                """, (dept_id,))
        self.refresh()
        messagebox.showinfo("Bilgi", "Sınav kayıtları silindi.")

    # ----------------- ÇAKIŞMA KONTROL -----------------

    def check_conflicts(self):
        dept_id = self._active_dept_id()

        with get_conn() as con:
            cur = con.cursor()

            cur.execute("""
                WITH enroll AS (
                    SELECT DISTINCT student_id, course_id
                    FROM enrollments
                )
                SELECT
                    s.number,
                    s.full_name,
                    c1.code AS course1,
                    c2.code AS course2,
                    ex1.exam_start
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
            """, (dept_id, dept_id))
            rows = cur.fetchall()

            cur.execute("""
                WITH enroll AS (
                    SELECT DISTINCT student_id, course_id
                    FROM enrollments
                ),
                base AS (
                    SELECT ex1.exam_start AS ts
                    FROM enroll e1
                    JOIN enroll e2
                         ON e1.student_id = e2.student_id
                        AND e1.course_id  < e2.course_id
                    JOIN exams  ex1 ON ex1.course_id = e1.course_id
                    JOIN exams  ex2 ON ex2.course_id = e2.course_id
                                   AND ex1.exam_start = ex2.exam_start
                    JOIN courses c1 ON c1.id = e1.course_id AND c1.dept_id = ?
                    JOIN courses c2 ON c2.id = e2.course_id AND c2.dept_id = ?
                )
                SELECT ts, COUNT(*) AS cnt
                FROM base
                GROUP BY ts
                ORDER BY ts
            """, (dept_id, dept_id))
            per_slot = cur.fetchall()

        if not rows:
            messagebox.showinfo("Çakışma Kontrolü", self._msg_conflicts_summary(0, [], []))
            return

        total = len(rows)
        msg = self._msg_conflicts_summary(total, per_slot, rows)
        messagebox.showwarning("Çakışma Detayı", msg)

    # ----------------- OTOMATİK PLAN -----------------

    def auto_plan(self):
        """
        Çakışma-farkında basit yerleştirici:
        - Slotlar: 10 gün * [09:00, 11:00, 13:30, 15:30, 17:00, 19:00]
        - Dersler, öğrencisi ortak olduğu derslerle aynı anda olmadan yerleştirilir.
        """
        dept_id = self._active_dept_id()

        # --- SLOT HAVUZU (Kısıtlar varsa onlara göre üret)
        daily_times = [(9, 0), (11, 0), (13, 30), (15, 30), (17, 0), (19, 0)]
        slots = []

        c = getattr(self, "constraints", None)
        if c and c.get("date_start") and c.get("date_end"):
            cur_day = c["date_start"]
            while cur_day <= c["date_end"]:
                if cur_day.weekday() not in c.get("exclude_days", set()):
                    for h, m in daily_times:
                        slots.append(datetime(cur_day.year, cur_day.month, cur_day.day, h, m))
                cur_day += timedelta(days=1)
        else:
            start_day = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            days = [start_day + timedelta(days=d) for d in range(10)]
            for d in days:
                for h, m in daily_times:
                    slots.append(d.replace(hour=h, minute=m))

        with get_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, code, class_year
                FROM courses
                WHERE dept_id=?
                ORDER BY code
            """, (dept_id,))
            courses = cur.fetchall()  # [(cid, code, class_year), ...]

            excluded_ids = set(self.constraints.get("excluded_courses", set()) or set())
            if excluded_ids:
                courses = [row for row in courses if row[0] not in excluded_ids]

            if not courses:
                messagebox.showinfo("Otomatik Plan", "Programlanacak ders kalmadı (tüm dersler çıkarılmış olabilir).")
                return

            # Bu bölümün sınavlarını temizle
            cur.execute("""
                DELETE FROM exams
                WHERE course_id IN (SELECT id FROM courses WHERE dept_id=?)
            """, (dept_id,))

            # Her dersin öğrenci kümesi / boyutu / sınıf yılı
            course_students = {}
            course_sizes = {}
            course_year = {}
            for cid, _, cy in courses:
                cur.execute("SELECT student_id FROM enrollments WHERE course_id=?", (cid,))
                sids = {r[0] for r in cur.fetchall()}
                course_students[cid] = sids
                course_sizes[cid] = len(sids)
                course_year[cid] = cy

            # Çakışma grafı
            neighbors = {cid: set() for cid, _, _ in courses}
            cids = [cid for cid, _, _ in courses]
            for i in range(len(cids)):
                a = cids[i]
                Sa = course_students[a]
                for j in range(i + 1, len(cids)):
                    b = cids[j]
                    if not Sa or not course_students[b]:
                        continue
                    if Sa.intersection(course_students[b]):
                        neighbors[a].add(b)
                        neighbors[b].add(a)

            # Yerleştirme sırası
            order = sorted(cids, key=lambda x: (course_sizes[x], len(neighbors[x])), reverse=True)

            # Greedy yerleştirme
            placed_time = {}          # cid -> slot(datetime)
            used_by_slot = {}         # slot -> set(cid)
            last_exam = {}            # student_id -> datetime
            from collections import defaultdict
            used_days_by_year = defaultdict(set)  # class_year -> {date}

            for cid in order:
                forbiddens = set()
                for nb in neighbors[cid]:
                    if nb in placed_time:
                        forbiddens.add(placed_time[nb])

                chosen = None
                cy = course_year.get(cid, None)

                def _can_place_at(ts):
                    if ts in forbiddens:
                        return False
                    if self.constraints.get("single_exam_at_a_time", False) and used_by_slot.get(ts):
                        return False
                    for other in used_by_slot.get(ts, set()):
                        if course_students[cid] & course_students[other]:
                            return False
                    cooldown = int(self.constraints.get("cooldown_min", 0) or 0)
                    if cooldown > 0:
                        for sid in course_students[cid]:
                            last = last_exam.get(sid)
                            if last is not None:
                                delta_min = abs((ts - last).total_seconds()) / 60.0
                                if delta_min < cooldown:
                                    return False
                    return True

                # Aşama 1: Aynı sınıf yılına farklı gün
                if cy is not None:
                    for ts in slots:
                        if not _can_place_at(ts):
                            continue
                        day = ts.date()
                        if day not in used_days_by_year[cy]:
                            chosen = ts
                            break

                # Aşama 2: Genel ilk uygun slot
                if chosen is None:
                    for ts in slots:
                        if _can_place_at(ts):
                            chosen = ts
                            break

                if chosen is None:
                    chosen = slots[-1]

                placed_time[cid] = chosen
                used_by_slot.setdefault(chosen, set()).add(cid)
                for sid in course_students[cid]:
                    last_exam[sid] = chosen
                if cy is not None and chosen is not None:
                    used_days_by_year[cy].add(chosen.date())

            # Veritabanına yaz
            exam_type = self.constraints.get("exam_type", "Vize")
            if exam_type not in ("Vize", "Final", "Bütünleme"):
                exam_type = "Vize"

            for cid, ts in placed_time.items():
                cur.execute(
                    "INSERT INTO exams(course_id, exam_start, exam_type) VALUES (?, ?, ?)",
                    (cid, ts, exam_type)
                )

        self.refresh()
        messagebox.showinfo("Tamam", "Çakışma-farkında taslak sınav planı oluşturuldu.")

    # ----------------- ELLE DÜZENLEME (Çift tık) -----------------

    def edit_selected_exam(self):
        """Seçili satır için sınav başlangıç/oda düzenleme penceresi."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Uyarı", "Önce bir sınav satırı seçin.")
            return

        values = self.tree.item(sel[0], "values")
        if not values:
            messagebox.showerror("Hata", "Satır okunamadı.")
            return

        # Yeni sütun sırası: (exam_id, course(code), name, class_year, exam_start, room_id)
        exam_id = values[0]
        code    = values[1]
        start   = values[4]
        room_id = values[5]

        dept_id = self._active_dept_id()

        with get_conn() as con:
            cur = con.cursor()
            # course_id
            cur.execute("SELECT id FROM courses WHERE code=? AND dept_id=?", (code, dept_id))
            row = cur.fetchone()
            if not row:
                messagebox.showerror("Hata", "Ders bulunamadı.")
                return
            course_id = row[0]

            # mevcut exam (varsa id üzerinden, yoksa course_id ile)
            if exam_id:
                try:
                    cur.execute("SELECT id, exam_start, room_id FROM exams WHERE id=?", (int(exam_id),))
                except Exception:
                    cur.execute("SELECT id, exam_start, room_id FROM exams WHERE id=?", (exam_id,))
            else:
                cur.execute("SELECT id, exam_start, room_id FROM exams WHERE course_id=?", (course_id,))
            ex = cur.fetchone()

            exam_id_val = ex[0] if ex else None
            exam_start = ex[1] if ex else (datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M"))
            exam_room = ex[2] if ex else None

            # derslikler
            cur.execute("""
                SELECT id, code, name, capacity
                FROM classrooms
                WHERE dept_id=?
                ORDER BY code
            """, (dept_id,))
            rooms = cur.fetchall()

        # Pencere
        win = tk.Toplevel(self)
        win.title(f"Sınav Düzenle — {code}")
        win.geometry("420x200")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        frm = ttk.Frame(win); frm.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Tarih-Saat (YYYY-MM-DD HH:MM):").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        v_start = tk.StringVar(value=(exam_start or ""))
        ttk.Entry(frm, textvariable=v_start, width=24).grid(row=0, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(frm, text="Derslik:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        room_disp_list = ["(boş bırak)"] + [f"{r[0]} — {r[1]} ({r[2]}) cap:{r[3]}" for r in rooms]
        pre = "(boş bırak)"
        if exam_room:
            for s in room_disp_list:
                if s.startswith(str(exam_room) + " —"):
                    pre = s; break
        v_room = tk.StringVar(value=pre)
        ttk.Combobox(frm, textvariable=v_room, values=room_disp_list, state="readonly", width=36) \
            .grid(row=1, column=1, sticky="w", padx=6, pady=6)

        btnf = ttk.Frame(win); btnf.pack(fill="x", padx=12, pady=(0, 12))

        def _save():
            val_start = v_start.get().strip()
            try:
                _ = datetime.strptime(val_start, "%Y-%m-%d %H:%M")
            except Exception:
                messagebox.showerror("Hata", "Tarih formatı hatalı. Örn: 2025-01-15 13:30")
                return

            sel_text = v_room.get()
            new_room_id = None
            if sel_text != "(boş bırak)":
                try:
                    new_room_id = int(sel_text.split(" — ")[0])
                except Exception:
                    new_room_id = None

            with get_conn() as con2:
                cur2 = con2.cursor()
                if exam_id_val:
                    cur2.execute("UPDATE exams SET exam_start=?, room_id=? WHERE id=?",
                                 (val_start, new_room_id, exam_id_val))
                else:
                    cur2.execute("INSERT INTO exams(course_id, exam_start, room_id) VALUES (?,?,?)",
                                 (course_id, val_start, new_room_id))

            self.refresh()
            win.destroy()

        ttk.Button(btnf, text="Kaydet", command=_save).pack(side="right")
        ttk.Button(btnf, text="İptal", command=win.destroy).pack(side="right", padx=8)

    # ----------------- OTOMATİK ODA ATAMA -----------------

    def auto_assign_rooms(self):
        """Her sınav için, aynı anda boş olan ve kapasitesi yeten bir derslik ata."""
        dept_id = self._active_dept_id()
        assigned = 0
        skipped_no_room = 0
        skipped_capacity = 0
        examples_capacity = []  # (code, need, maxcap, ts)
        examples_noroom = []    # (code, need, ts)

        with get_conn() as con:
            cur = con.cursor()

            # Odalar: kapasite DESC
            cur.execute("""
                SELECT id, code, COALESCE(capacity_pdf, capacity) AS capacity
                FROM classrooms
                WHERE dept_id=?
                ORDER BY capacity DESC, code ASC
            """, (dept_id,))
            rooms = cur.fetchall()

            if not rooms:
                messagebox.showwarning("Oda Atama", "Bu bölüm için kayıtlı derslik yok.")
                return

            # Oda atanmamış sınavlar + öğrenci sayısı + ders kodu
            cur.execute("""
                SELECT e.id, e.course_id, e.exam_start, c.code,
                       (SELECT COUNT(*) FROM enrollments en WHERE en.course_id=e.course_id) AS need
                FROM exams e
                JOIN courses c ON c.id = e.course_id
                WHERE c.dept_id=? AND e.room_id IS NULL
                ORDER BY e.exam_start, c.class_year, c.code
            """, (dept_id,))
            exams = cur.fetchall()

            # aynı anda kullanılan odalar
            cur.execute("SELECT exam_start, room_id FROM exams WHERE room_id IS NOT NULL")
            used_by_ts = {}
            for ts, rid in cur.fetchall():
                used_by_ts.setdefault(ts, set()).add(rid)

            for ex_id, course_id, ts, code, need in exams:
                used = used_by_ts.get(ts, set())

                # bu ts'te boş olan odalar
                candidates = [(rid, rcode, cap) for (rid, rcode, cap) in rooms if rid not in used]
                if not candidates:
                    skipped_no_room += 1
                    examples_noroom.append((code, need, ts))
                    continue

                # kapasitesi yetenler
                fits = [(rid, rcode, cap) for (rid, rcode, cap) in candidates if cap >= need]
                if not fits:
                    maxcap = max(c[2] for c in candidates) if candidates else 0
                    skipped_capacity += 1
                    examples_capacity.append((code, need, maxcap, ts))
                    continue

                # en az kapasiteli uygun oda
                fits.sort(key=lambda x: x[2])
                rid, _, _ = fits[0]
                cur.execute("UPDATE exams SET room_id=? WHERE id=?", (rid, ex_id))
                used_by_ts.setdefault(ts, set()).add(rid)
                assigned += 1

            con.commit()

        lines = [f"Atanan: {assigned}"]
        if skipped_no_room or skipped_capacity:
            lines.append(f"Atlanan (boş oda yok): {skipped_no_room}")
            lines.append(f"Atlanan (kapasite yetersiz): {skipped_capacity}")
        if examples_capacity:
            lines.append("\nKapasite yetersiz örnekler (ilk 5):")
            for c_, need_, mx, ts in examples_capacity[:5]:
                lines.append("  - " + self._msg_capacity(code=c_, room="—", need=need_, maxcap=mx, ts=ts))
        if examples_noroom:
            lines.append("\nBoş oda bulunamayan örnekler (ilk 5):")
            for c_, need_, ts in examples_noroom[:5]:
                lines.append("  - " + self._msg_no_room(code=c_, need=need_, ts=ts))

        messagebox.showinfo("Oda Atama", "\n".join(lines))
        self.refresh()

    # ----------------- DIŞA AKTAR -----------------

    def export_excel(self):
        """Ekrandaki planı Excel'e kaydet."""
        dept_id = self._active_dept_id()
        with get_conn() as con:
            cur = con.cursor()
            where_dept = "WHERE c.dept_id=?" if dept_id else ""
            params = (dept_id,) if dept_id else tuple()
            cur.execute(f"""
                SELECT c.code AS Kod,
                       c.name AS Ad,
                       c.class_year AS Sınıf,
                       e.exam_start AS Başlangıç,
                       COALESCE(cl.code, '') AS Derslik
                FROM courses c
                LEFT JOIN exams e ON e.course_id=c.id
                LEFT JOIN classrooms cl ON cl.id = e.room_id
                {where_dept}
                ORDER BY c.class_year, c.code
            """, params)
            rows = cur.fetchall()

        if not rows:
            messagebox.showinfo("Dışa Aktar", "Aktarılacak kayıt bulunamadı.")
            return

        df = pd.DataFrame(rows, columns=["Kod", "Ad", "Sınıf", "Başlangıç", "Derslik"])
        out_dir = Path("data"); out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"sinav_plani_{dept_id or 'tum'}_{datetime.now():%Y%m%d_%H%M}.xlsx"
        df.to_excel(out_path.as_posix(), index=False)
        messagebox.showinfo("Dışa Aktar", f"Excel dosyası kaydedildi:\n{out_path}")

    def export_pdf(self):
        """Sınav planını PDF olarak dışa aktar."""
        dept_id = self._active_dept_id()
        with get_conn() as con:
            cur = con.cursor()
            where_dept = "WHERE c.dept_id=?" if dept_id else ""
            params = (dept_id,) if dept_id else tuple()
            cur.execute(f"""
                SELECT c.code, c.name, c.class_year, e.exam_start, COALESCE(cl.code, '')
                FROM courses c
                LEFT JOIN exams e ON e.course_id=c.id
                LEFT JOIN classrooms cl ON cl.id = e.room_id
                {where_dept}
                ORDER BY c.class_year, e.exam_start
            """, params)
            rows = cur.fetchall()

        if not rows:
            messagebox.showinfo("PDF", "Kaydedilecek sınav bulunamadı.")
            return

        pdf_path = f"data/sinav_programi_{dept_id or 'tum'}_{datetime.now():%Y%m%d_%H%M}.pdf"
        c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2 * cm, 19 * cm, "Sınav Programı")

        headers = ["Kod", "Ad", "Sınıf", "Başlangıç", "Derslik"]
        c.setFont("Helvetica-Bold", 10)
        y = 18 * cm
        for i, h in enumerate(headers):
            c.drawString((2 + i * 6) * cm, y, h)

        c.setFont("Helvetica", 9)
        y -= 0.8 * cm
        for code, name, year, start, room in rows:
            c.drawString(2 * cm, y, str(code))
            c.drawString(8 * cm, y, str(name)[:40])
            c.drawString(17 * cm, y, str(year))
            c.drawString(20 * cm, y, str(start))
            c.drawString(27 * cm, y, str(room))
            y -= 0.6 * cm
            if y < 2 * cm:
                c.showPage()
                c.setFont("Helvetica", 9)
                y = 18 * cm

        c.save()
        messagebox.showinfo("PDF", f"PDF başarıyla kaydedildi:\n{pdf_path}")

    # ----------------- DİĞER PDF’LER / YARDIMCILAR -----------------

    def _get_selected_course_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        code = values[1]
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM courses WHERE dept_id=? AND code=?",
                        (self._active_dept_id(), code))
            row = cur.fetchone()
            return row[0] if row else None

    def edit_selected(self):
        return self.edit_selected_exam()

    # ----------------- KISITLAR -----------------

    def open_constraints(self):
        top = tk.Toplevel(self)
        top.title("Kısıtlar")
        top.geometry("620x560")  # liste için biraz daha yüksek

        # --- Girdi değişkenleri
        v_start = tk.StringVar(value="")
        v_end = tk.StringVar(value="")
        v_cool = tk.StringVar(value=str(self.constraints.get("cooldown_min", 15)))
        v_defdur = tk.StringVar(value=str(self.constraints.get("default_duration", 75)))
        v_single = tk.BooleanVar(value=self.constraints.get("single_exam_at_a_time", False))
        v_exam_type = tk.StringVar(value=self.constraints.get("exam_type", "Vize"))

        # --- Tarih aralığı
        frm_dates = ttk.LabelFrame(top, text="Tarih Aralığı")
        frm_dates.pack(fill="x", padx=10, pady=8)
        ttk.Label(frm_dates, text="Başlangıç (YYYY-MM-DD):").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm_dates, textvariable=v_start, width=16).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(frm_dates, text="Bitiş (YYYY-MM-DD):").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm_dates, textvariable=v_end, width=16).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        # --- Hariç günler
        frm_days = ttk.LabelFrame(top, text="Hariç Günler")
        frm_days.pack(fill="x", padx=10, pady=8)
        v_excl = {d: tk.BooleanVar(value=(d in self.constraints.get("exclude_days", set()))) for d in range(7)}
        text_map = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cts", "Paz"]
        for i in range(7):
            ttk.Checkbutton(frm_days, text=text_map[i], variable=v_excl[i]).grid(row=0, column=i, padx=4, pady=4)

        # --- Süre & bekleme
        frm_dur = ttk.LabelFrame(top, text="Süre ve Bekleme")
        frm_dur.pack(fill="x", padx=10, pady=8)
        ttk.Label(frm_dur, text="Varsayılan süre (dk):").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm_dur, textvariable=v_defdur, width=8).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(frm_dur, text="Bekleme süresi (dk):").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm_dur, textvariable=v_cool, width=8).grid(row=1, column=1, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(frm_dur, text="Aynı anda yalnızca tek sınav", variable=v_single).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=6
        )

        # --- Sınav Türü
        frm_type = ttk.LabelFrame(top, text="Sınav Türü")
        frm_type.pack(fill="x", padx=10, pady=8)
        ttk.Label(frm_type, text="Tür:").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        ttk.Combobox(
            frm_type,
            textvariable=v_exam_type,
            state="readonly",
            values=["Vize", "Final", "Bütünleme"],
            width=18
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        # --- Programdan çıkarılacak dersler
        frm_exclude = ttk.LabelFrame(top, text="Programdan çıkarılacak dersler")
        frm_exclude.pack(fill="both", padx=10, pady=8, expand=True)

        dept_id = self._active_dept_id()
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, code, name
                FROM courses
                WHERE dept_id=?
                ORDER BY code
            """, (dept_id,))
            _courses_rows = cur.fetchall()

        ttk.Label(
            frm_exclude,
            text="Seçilen dersler programa DAHİL EDİLMEYECEK (Ctrl/Shift ile çoklu seçim):"
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))

        lb_exclude = tk.Listbox(
            frm_exclude, selectmode="extended",
            height=10, width=52, exportselection=False
        )
        lb_exclude.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        frm_exclude.rowconfigure(1, weight=1)
        frm_exclude.columnconfigure(0, weight=1)

        display_to_id = {}
        for cid, code, name in _courses_rows:
            label = f"{code} - {name}"
            lb_exclude.insert("end", label)
            display_to_id[label] = cid

        _prev_excluded = set(self.constraints.get("excluded_courses", set()) or set())
        if _prev_excluded:
            indices_to_select = []
            for idx in range(lb_exclude.size()):
                lbl = lb_exclude.get(idx)
                if display_to_id.get(lbl) in _prev_excluded:
                    indices_to_select.append(idx)
            for i in indices_to_select:
                lb_exclude.selection_set(i)

        btns = ttk.Frame(top)
        btns.pack(fill="x", padx=10, pady=8)

        def _save():
            ds = v_start.get().strip()
            de = v_end.get().strip()
            try:
                d_start = datetime.strptime(ds, "%Y-%m-%d").date() if ds else None
                d_end = datetime.strptime(de, "%Y-%m-%d").date() if de else None
            except ValueError:
                messagebox.showerror("Hata", "Tarih formatı YYYY-MM-DD olmalı.")
                return

            excl = {d for d, val in v_excl.items() if val.get()}
            try:
                self.constraints["default_duration"] = int(v_defdur.get())
                self.constraints["cooldown_min"] = int(v_cool.get())
            except ValueError:
                messagebox.showerror("Hata", "Süre/bekleme sayısal olmalı.")
                return

            selected_labels = [lb_exclude.get(i) for i in lb_exclude.curselection()]
            excluded_ids = {display_to_id[lbl] for lbl in selected_labels}

            self.constraints["date_start"] = d_start
            self.constraints["date_end"] = d_end
            self.constraints["exclude_days"] = excl
            self.constraints["single_exam_at_a_time"] = bool(v_single.get())
            self.constraints["exam_type"] = v_exam_type.get()
            self.constraints["excluded_courses"] = excluded_ids

            messagebox.showinfo("Kısıtlar", "Kısıtlar kaydedildi. Otomatik planlamayı tekrar çalıştırın.")
            top.destroy()

        ttk.Button(btns, text="Kaydet", command=_save).pack(side="right")

    # ----------------- OTURMA PLANI -----------------

    def open_seating(self):
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        if not sel:
            messagebox.showwarning("Oturma Planı", "Lütfen önce listeden bir sınav seçin.")
            return

        item = self.tree.item(sel[0])
        values = item.get("values") or []
        if not values:
            messagebox.showwarning("Oturma Planı", "Seçim okunamadı.")
            return

        exam_id = values[0]

        from .seating_view import SeatingView
        top = tk.Toplevel(self)
        top.title("Oturma Planı")
        top.geometry("1000x600")
        SeatingView(top, exam_id=exam_id, user=getattr(self, "user", None)).pack(fill="both", expand=True)
