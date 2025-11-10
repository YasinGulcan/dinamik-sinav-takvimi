# src/ui/seating_view.py

import os
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from core.db import get_conn


class SeatingView(ttk.Frame):

    def __init__(self, master, exam_id, user=None, **kwargs):
        super().__init__(master, **kwargs)
        self.exam_id = exam_id
        self.user = user or {}

        # Üst bar
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="PDF Olarak Kaydet", command=self.export_pdf).pack(side="left", padx=(0,8))
        ttk.Button(bar, text="Yeniden Yerleştir", command=self.reassign).pack(side="left")

        self.info = ttk.Label(self, text="", foreground="#555")
        self.info.pack(fill="x", padx=10, pady=(0,8))

        # Liste
        cols = ("ogr_no","ad_soyad","sira","sutun","koltuk_no")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=18)
        headers = ["Öğrenci No","Ad Soyad","Sıra","Sütun","Koltuk#"]
        widths  = [120,            260,        80,    80,      80]
        for c, h, w in zip(cols, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, stretch=(c in ("ogr_no","ad_soyad")))
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        self._load_and_assign()

    # ----------------- Veriyi Yükle & Yerleştir -----------------
    def _load_and_assign(self):
        self.exam = self._fetch_exam()
        if not self.exam:
            return  # _fetch_exam hata mesajını gösteriyor

        room_id = self.exam.get("room_id")
        if room_id is None:
            messagebox.showwarning("Oturma Planı", "Bu sınava derslik atanmamış. Önce 'Otomatik Oda Ata' yapın veya derslik seçin.")
            return

        self.classroom = self._fetch_classroom(room_id)
        if not self.classroom:
            messagebox.showerror("Oturma Planı", f"Derslik bulunamadı (id={room_id}).")
            return

        self.students = self._fetch_students_of_course(self.exam["course_id"])
        self.assignments = self._assign_students(self.students, self.classroom)

        # Listeyi doldur
        for i in self.tree.get_children():
            self.tree.delete(i)
        for seat in self.assignments["seated"]:
            self.tree.insert("", "end", values=(seat["ogr_no"], seat["ad_soyad"], seat["row"], seat["col"], seat["seat_index"]))

        # Üst bilgi
        cap = self.assignments["capacity"]
        n = len(self.students)
        over = max(0, n - cap)
        header = (
            f"{self.exam['course_code']} - {self.exam['course_name']}  |  "
            f"Derslik: {self.classroom['code']} "
            f"({self.classroom['rows']}×{self.classroom['cols']}×{self.classroom['seats_per_desk']} = kapasite {cap})  |  "
            f"Tarih-Saat: {self.exam.get('exam_dt_txt','')}"
        )
        if over > 0:
            header += f"  • UYARI: Kapasite yetersiz! {n} öğrenci var; {cap} kapasite. {over} kişi sığmadı."
        self.info.configure(text=header)

        if over > 0:
            messagebox.showwarning("Kapasite Yetersiz", f"{over} öğrenci yerleşemedi. Daha büyük bir derslik atayın veya sınavı bölün.")

    def reassign(self):
        """Elle değişiklikten sonra yeniden dağıtmak istersen."""
        self._load_and_assign()

    # ----------------- DB: exam, class, students -----------------
    def _fetch_exam(self):
        with get_conn() as con:
            cur = con.cursor()

            # exams kolon adlarını öğren
            cur.execute("PRAGMA table_info(exams)")
            cols_info = cur.fetchall()
            exam_cols = {r[1] for r in cols_info}

            # tarih-saat alias (hangi kolon varsa onu kullan)
            dt_expr = "'' AS exam_dt_txt"
            if "exam_dt" in exam_cols:
                dt_expr = "e.exam_dt AS exam_dt_txt"
            elif "start_ts" in exam_cols:
                dt_expr = "e.start_ts AS exam_dt_txt"
            elif {"exam_date","exam_time"}.issubset(exam_cols):
                dt_expr = "(e.exam_date || ' ' || e.exam_time) AS exam_dt_txt"
            elif {"date","time"}.issubset(exam_cols):
                dt_expr = "(e.date || ' ' || e.time) AS exam_dt_txt"
            elif "start" in exam_cols:
                dt_expr = "e.start AS exam_dt_txt"
            elif "date" in exam_cols:
                dt_expr = "e.date AS exam_dt_txt"
            elif "time" in exam_cols:
                dt_expr = "e.time AS exam_dt_txt"

            # room_id alanı bazı şemalarda 'room' olabilir
            room_expr = "e.room_id AS room_id" if "room_id" in exam_cols else (
                        "e.room AS room_id" if "room" in exam_cols else "NULL AS room_id")

            sql = f"""
                SELECT e.id, e.course_id, {room_expr}, {dt_expr},
                       c.code AS course_code, c.name AS course_name
                  FROM exams e
                  JOIN courses c ON c.id = e.course_id
                 WHERE e.id = ?
            """

            param = (self.exam_id,)
            try:
                param = (int(self.exam_id),)
            except Exception:
                pass

            cur.execute(sql, param)
            row = cur.fetchone()
            if not row:
                messagebox.showerror(
                    "Oturma Planı",
                    f"Sınav bulunamadı (id={self.exam_id}).\n"
                    "Not: Sınav listesine gizli 'exam_id' sütunu eklendiğinden emin olun."
                )
                return None

            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    def _fetch_classroom(self, room_id):
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, code, name, capacity, rows, cols, seats_per_desk
                  FROM classrooms
                 WHERE id = ?
            """, (room_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    def _fetch_students_of_course(self, course_id):
        """
        PDF’te bu şekilde isteniyor: 'Öğrenci No' ve 'Ad Soyad' kolonları
        şemadaki mevcut isim neyse ona uyarlanır (student_no/number, name/full_name).
        """
        with get_conn() as con:
            cur = con.cursor()

            # students tablosu kolon adlarını öğren
            cur.execute("PRAGMA table_info(students)")
            s_cols_info = cur.fetchall()
            s_cols = {r[1] for r in s_cols_info}

            # numara kolonu
            if "student_no" in s_cols:
                no_col = "student_no"
            elif "number" in s_cols:
                no_col = "number"
            else:
                # yoksa id'yi kullan (boş kalmasın)
                no_col = "id"

            # ad kolonu
            if "name" in s_cols:
                name_col = "name"
            elif "full_name" in s_cols:
                name_col = "full_name"
            else:
                name_col = "name"  # yine de dene

            sql = f"""
                SELECT s.id, s.{no_col} AS ogr_no, s.{name_col} AS ad_soyad
                  FROM enrollments en
                  JOIN students s ON s.id = en.student_id
                 WHERE en.course_id = ?
              ORDER BY s.{no_col}
            """
            cur.execute(sql, (course_id,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]

    # ----------------- Yerleştirme Algoritması -----------------
    def _assign_students(self, students, classroom):
        """
        students: DB'den gelen liste (dict/tuple olabilir)
        classroom: dict (rows, cols, seats_per_desk) ya da
                   tuple (..., rows, cols, seats_per_desk)
        Dönüş: {"capacity": int, "seated": [seat_dict,...], "unseated": int}
        """
        # --- sınıf bilgileri ---
        if isinstance(classroom, dict):
            rows = int(classroom.get("rows", 0) or 0)
            cols = int(classroom.get("cols", 0) or 0)
            seats = int(classroom.get("seats_per_desk", classroom.get("seats", 1)) or 1)
        else:
            # tuple: (..., rows, cols, seats_per_desk) varsayımı
            try:
                rows = int(classroom[-3] or 0)
                cols = int(classroom[-2] or 0)
                seats = int(classroom[-1] or 1)
            except Exception:
                rows = cols = 0
                seats = 1

        capacity = rows * cols * max(1, seats)

        # --- yerleştir ---
        placements = self._assign_students_single_first(students, rows, cols, seats)

        # --- öğrenci alanlarını güvenle çıkar ---
        def _stu_fields(st):
            # dict
            if isinstance(st, dict):
                ogr_no = st.get("number") or st.get("ogr_no") or st.get("student_no") or ""
                ad_soyad = st.get("full_name") or st.get("ad_soyad") or st.get("name") or ""
                return ogr_no, ad_soyad
            # tuple/list: (id, number, full_name, ...)
            try:
                if len(st) >= 3:
                    return st[1] or "", st[2] or ""
                elif len(st) >= 2:
                    return st[0] or "", st[1] or ""
            except Exception:
                pass
            # fallback
            return "", str(st)

        seated = []
        for st, r, c, sidx in placements:
            ogr_no, ad_soyad = _stu_fields(st)
            seated.append({
                "ogr_no": ogr_no,
                "ad_soyad": ad_soyad,
                "row": r + 1,  # kullanıcıya 1-based
                "col": c + 1,
                "seat_index": sidx + 1  # 1 = ilk koltuk (tekli oturma)
            })

        unseated = max(0, len(students) - capacity)

        return {
            "capacity": capacity,
            "seated": seated,
            "unseated": unseated
        }

    # ----------------- PDF Dışa Aktarım -----------------
    def export_pdf(self):

        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
        except Exception:
            messagebox.showerror("PDF", "reportlab kurulu değil. Kur: pip install reportlab")
            return

        if not getattr(self, "assignments", None) or not getattr(self, "classroom", None) or not getattr(self, "exam",
                                                                                                         None):
            messagebox.showwarning("PDF", "Önce yerleştirme yapılmalı.")
            return

        exam = self.exam
        room = self.classroom
        seated = list(self.assignments["seated"])
        overflow = list(self.assignments.get("overflow", []))

        # Çıkış yolu
        import os
        os.makedirs("data", exist_ok=True)
        safe_code = (exam.get("course_code") or "DERS").replace("/", "-")
        out_path = os.path.join("data", f"oturma_plani_{safe_code}_{exam['id']}.pdf")

        # Sayfa ve kenar boşlukları
        page = landscape(A4)
        page_w, page_h = page
        left, right, top, bottom = 1.2 * cm, 1.2 * cm, 1.2 * cm, 1.0 * cm

        # Izgara ölçüleri
        rows = int(room.get("rows") or 1)
        cols = int(room.get("cols") or 1)
        spd = int(room.get("seats_per_desk") or 1)
        grid_w = page_w - left - right
        grid_h = page_h - top - bottom - (2.6 * cm)  # başlık/lejand için yer
        desk_w = grid_w / max(cols, 1)
        desk_h = grid_h / max(rows, 1)

        # Yardımcı: koltuk ofsetleri (masanın içine dağıtım)
        def seat_offsets(seats_per_desk: int):
            # 1: merkez; 2: solda/sağda; 3-4: köşeler; >4: 2xN ızgara
            offs = []
            if seats_per_desk <= 0:
                return [(0.5, 0.5)]
            if seats_per_desk == 1:
                return [(0.5, 0.5)]
            if seats_per_desk == 2:
                return [(0.33, 0.5), (0.67, 0.5)]
            if seats_per_desk == 3:
                return [(0.25, 0.35), (0.5, 0.7), (0.75, 0.35)]
            if seats_per_desk == 4:
                return [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)]
            # 5+: 2 satırlı düzen (üst/alt), sütun sayısı = ceil(n/2)
            import math
            cols_n = math.ceil(seats_per_desk / 2)
            xs = [(i + 0.5) / cols_n for i in range(cols_n)]
            ys = [0.33, 0.67]
            for i in range(seats_per_desk):
                r = i // cols_n
                c = i % cols_n
                y = ys[0] if r == 0 else ys[1]
                x = xs[c]
                offs.append((x, y))
            return offs

        seat_offs = seat_offsets(spd)

        c = canvas.Canvas(out_path, pagesize=page)

        def draw_header():
            y = page_h - top
            c.setFont("Helvetica-Bold", 14)
            c.drawString(left, y, "SINAV OTURMA PLANI")
            c.setFont("Helvetica", 10)
            c.drawRightString(page_w - right, y, f"Oluşturma: {datetime.now():%Y-%m-%d %H:%M}")
            y -= 0.6 * cm
            c.setFont("Helvetica", 10)
            info = f"Ders: {exam.get('course_code', '')} — {exam.get('course_name', '')}"
            c.drawString(left, y, info)
            y -= 0.45 * cm
            extra = f"Derslik: {room.get('code', '')}  •  Düzen: {rows}×{cols}×{spd}  •  Tarih-Saat: {exam.get('exam_dt_txt', '')}"
            c.drawString(left, y, extra)
            return y - 0.5 * cm  # grid üstü

        def draw_grid(y_top):
            """Masa dikdörtgenlerini ve koltuk işaretlerini çiz."""
            # Masa çerçeveleri
            c.setFont("Helvetica", 7)
            for r in range(1, rows + 1):
                for col in range(1, cols + 1):
                    x0 = left + (col - 1) * desk_w
                    y0 = y_top - r * desk_h
                    c.rect(x0, y0, desk_w, desk_h)  # masa kutusu
                    # masa etiketi (R{r}C{col})
                    c.drawString(x0 + 2, y0 + desk_h - 9, f"R{r}C{col}")

            # --- Öğrenci yerleşimi (numara üst, isim alt; iki satıra kadar sarma) ---
            def _wrap_name(text: str, max_chars: int):
                txt = (text or "").strip()
                if len(txt) <= max_chars:
                    return [txt]
                # iki satıra böl; boşluklardan kır
                first = txt[:max_chars]
                # mümkünse son boşlukta kır
                sp = first.rfind(" ")
                if sp >= 8:  # çok kısa kelimeyi tek başına bırakma
                    line1 = first[:sp]
                    rest = (txt[sp + 1:]).strip()
                else:
                    line1 = first
                    rest = txt[max_chars:].strip()
                line2 = rest[:max_chars]
                return [line1, line2]

            c.setFont("Helvetica", 8)
            for s in seated:
                r = int(s["row"])
                col = int(s["col"])
                si = int(s["seat_index"])  # 1..spd
                if not (1 <= r <= rows and 1 <= col <= cols):
                    continue

                x0 = left + (col - 1) * desk_w
                y0 = y_top - r * desk_h

                rel = seat_offs[(si - 1) % len(seat_offs)]
                cx = x0 + rel[0] * desk_w
                cy = y0 + rel[1] * desk_h

                # Nokta biraz daha küçük
                c.circle(cx, cy, 1.6, stroke=1, fill=1)

                ogr_no = str(s.get("ogr_no", ""))
                adsoy = str(s.get("ad_soyad", ""))

                # Dinamik metin boyutları ve dikey boşluk: masa yüksekliğine göre
                num_font = 8
                name_font = 6
                # numara/isim aralığı (desk_h küçükse de ayrık kalsın)
                gap = max(6, desk_h * 0.22)

                # İsim için sığdırma: yaklaşık karakter limiti masa genişliğine göre
                # (Helvetica 6pt için ~2.6 px/char varsayımı → cm cinsinden yaklaşık)
                approx_char = max(10, int(desk_w / 6.0 * 10))  # desk_w küçükse 10’a sabitle
                lines = _wrap_name(adsoy, approx_char)
                if len(lines) > 2:
                    lines = lines[:2]

                # Numara (üst)
                c.setFont("Helvetica-Bold", num_font)
                c.drawCentredString(cx, cy + gap, ogr_no)

                # İsim (alt, 1–2 satır)
                c.setFont("Helvetica", name_font)
                if len(lines) == 1:
                    c.drawCentredString(cx, cy - gap, lines[0])
                else:
                    c.drawCentredString(cx, cy - gap + 4, lines[0])
                    c.drawCentredString(cx, cy - gap - 4, lines[1])

        # SAYFA 1 — başlık + ızgara
        grid_top_y = draw_header()
        draw_grid(grid_top_y)

        # Eğer taşan öğrenci varsa, liste sayfası
        if overflow:
            c.showPage()
            y = page_h - top
            c.setFont("Helvetica-Bold", 14)
            c.drawString(left, y, "SINAV OTURMA PLANI — KAPASİTE DIŞI ÖĞRENCİLER")
            y -= 0.7 * cm
            c.setFont("Helvetica", 10)
            c.drawString(left, y, f"Ders: {exam.get('course_code', '')} — {exam.get('course_name', '')}")
            y -= 0.5 * cm
            c.drawString(left, y,
                         f"Derslik: {room.get('code', '')}  •  Düzen: {rows}×{cols}×{spd}  •  Tarih-Saat: {exam.get('exam_dt_txt', '')}")
            y -= 0.8 * cm

            # tablo başlığı
            c.setFont("Helvetica-Bold", 9)
            headers = ["#", "Öğrenci No", "Ad Soyad"]
            widths = [1.0 * cm, 3.0 * cm, 14.0 * cm]
            x0 = left
            for i, h in enumerate(headers):
                c.drawString(x0, y, h);
                x0 += widths[i]
            y -= 0.25 * cm
            c.line(left, y, left + sum(widths), y)
            y -= 0.2 * cm

            c.setFont("Helvetica", 9)
            idx = 1
            line_h = 0.5 * cm
            for st in overflow:
                if y - line_h < bottom:
                    c.showPage()
                    y = page_h - top
                    c.setFont("Helvetica-Bold", 9)
                    x0 = left
                    for i, h in enumerate(headers):
                        c.drawString(x0, y, h);
                        x0 += widths[i]
                    y -= 0.25 * cm
                    c.line(left, y, left + sum(widths), y)
                    y -= 0.2 * cm
                    c.setFont("Helvetica", 9)

                x = left
                c.drawString(x, y, str(idx));
                x += widths[0]
                c.drawString(x, y, str(st.get("ogr_no", "")));
                x += widths[1]
                c.drawString(x, y, str(st.get("ad_soyad", ""))[:60])
                y -= line_h
                idx += 1

        c.showPage()
        c.save()
        messagebox.showinfo("PDF", f"Oturma planı kaydedildi:\n{out_path}")

    def _assign_students_single_first(self, students, rows, cols, seats_per_desk):
        """
        Kural: önce her masanın seat_idx=0'ı (tekli) doldurulur; sonra 1, sonra 2...
        Dönüş: [(student_obj, r0, c0, seat_idx0)]  (hepsi 0-based index)
        """
        rows = int(rows or 0)
        cols = int(cols or 0)
        seats_per_desk = max(1, int(seats_per_desk or 1))

        desks = [(r, c) for r in range(rows) for c in range(cols)]  # satır-major
        total_slots = rows * cols * seats_per_desk

        students = list(students)[:total_slots]  # kapasite kadar kırp
        n = len(students)
        if n == 0 or rows == 0 or cols == 0:
            return []

        # katmanlar: 0 → 1 → 2 ...
        layers = [[(r, c, s) for (r, c) in desks] for s in range(seats_per_desk)]

        placements = []
        i = 0
        for layer in layers:
            for (r, c, sidx) in layer:
                if i >= n:
                    break
                placements.append((students[i], r, c, sidx))
                i += 1
            if i >= n:
                break
        return placements


