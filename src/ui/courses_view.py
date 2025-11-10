# src/ui/courses_view.py
# Dersleri listeler; seçilince dersi alan öğrencileri gösterir (bilgi etiketi + CSV dışa aktarım)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
from core.db import get_conn


class CoursesView(ttk.Frame):

    def __init__(self, master, user, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user or {}

        # ---- ROL & BÖLÜM DURUMU ----
        self.is_admin = (self.user or {}).get("role") == "admin"
        self.dept_filter_var = tk.StringVar(value="Tümü")
        self._dept_list = []          # [(id, name)]
        self._dept_name_to_id = {}    # {"Bilgisayar Mühendisliği": 1, ...}

        def _load_departments():
            with get_conn() as con:
                cur = con.cursor()
                cur.execute("SELECT id, name FROM departments ORDER BY name")
                rows = cur.fetchall() or []
            self._dept_list = rows
            self._dept_name_to_id = {name: did for (did, name) in rows}

        if self.is_admin:
            _load_departments()

        # ÜST BAR — arama (kod/ad)
        title = ttk.Label(self, text="Dersler", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", padx=12, pady=(10, 0))

        from ui.widgets import Toolbar
        tb = Toolbar(self)

        # Sol tarafta arama
        left = ttk.Frame(tb._left)
        left.pack(side="left")
        ttk.Label(left, text="Ara (kod/ad):").pack(side="left")
        self.q = tk.StringVar()
        ttk.Entry(left, textvariable=self.q, width=30).pack(side="left", padx=6)
        ttk.Button(left, text="Ara", command=self.refresh).pack(side="left")
        ttk.Button(left, text="Yenile", command=lambda: [self.q.set(""), self.refresh()]).pack(side="left", padx=6)

        # Sağ tarafta bölüm filtresi (sadece admin)
        if self.is_admin:
            right = ttk.Frame(tb._right)
            right.pack(side="left")
            ttk.Label(right, text="Bölüm:").pack(side="left")
            ttk.Combobox(
                right, textvariable=self.dept_filter_var,
                values=["Tümü"] + [name for (_id, name) in self._dept_list],
                state="readonly", width=28
            ).pack(side="left", padx=6)
            ttk.Button(right, text="Uygula", command=self.refresh).pack(side="left")

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=10, pady=(0, 6))

        # İÇERİK — sol/sağ paneller
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        # SOL — Ders listesi
        left = ttk.LabelFrame(content, text="Dersler")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        if self.is_admin:
            cols = ("dept", "id", "code", "name", "class_year", "is_compulsory", "instructor")
            headers = ("Bölüm", "ID", "Kod", "Ad", "Sınıf", "Zorunlu(1/0)", "Hoca")
        else:
            cols = ("id", "code", "name", "class_year", "is_compulsory", "instructor")
            headers = ("ID", "Kod", "Ad", "Sınıf", "Zorunlu(1/0)", "Hoca")

        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        for c, h in zip(cols, headers):
            w = 110
            if c == "name": w = 220
            if c == "dept": w = 180
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")

        from ui.ui_theme import enable_treeview_features
        enable_treeview_features(self.tree)

        # ID sütununu gizle (tekil kimlik için saklı)
        self._id_col_index = list(self.tree["columns"]).index("id")
        self.tree.column("id", width=0, minwidth=0, stretch=False)

        self.tree.bind("<<TreeviewSelect>>", lambda e: self.load_students())
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        # SAĞ — Dersi alan öğrenciler
        right = ttk.LabelFrame(content, text="Dersi Alan Öğrenciler")
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        info_bar = ttk.Frame(right)
        info_bar.pack(fill="x", padx=6, pady=(6, 0))

        # Seçili ders bilgisi etiketi
        self.info = ttk.Label(info_bar, text="Bir ders seçiniz.", foreground="#444")
        self.info.pack(side="left")

        ttk.Button(info_bar, text="Dışa Aktar (CSV)", command=self.export_csv).pack(side="right")

        scols = ("number", "full_name", "class_year")
        sheaders = ("Numara", "Ad Soyad", "Sınıf")
        self.stree = ttk.Treeview(right, columns=scols, show="headings", height=16)
        for c, h in zip(scols, sheaders):
            self.stree.heading(c, text=h)
            self.stree.column(c, width=160 if c != "full_name" else 220, anchor="center")
        self.stree.pack(fill="both", expand=True, padx=6, pady=6)
        enable_treeview_features(self.stree)

        self.refresh()

    # --------- Yardımcılar ---------

    def _active_dept_id(self):
        """Admin için seçili bölümün id'si, koordinator için kendi dept id'si."""
        if self.is_admin:
            name = self.dept_filter_var.get()
            if name == "Tümü":
                return None
            return self._dept_name_to_id.get(name)
        return (self.user or {}).get("department_id")

    def _dept_clause(self, table_alias: str):
        """Koordinatörler için WHERE filtresi döndürür; admin seçili bölüme göre sınırlandırılır."""
        dept_id = self._active_dept_id()
        if not dept_id:
            return "", ()
        return f" AND {table_alias}.dept_id=?", (dept_id,)

    # --------- Veri yükleme ---------

    def refresh(self):
        qtxt_like = f"%{self.q.get().strip()}%"
        dept_id = self._active_dept_id()

        with get_conn() as con:
            cur = con.cursor()
            if self.is_admin:
                where = ["(c.code LIKE ? OR c.name LIKE ?)"]
                params = [qtxt_like, qtxt_like]
                if dept_id:
                    where.append("c.dept_id=?")
                    params.append(dept_id)
                where_sql = " WHERE " + " AND ".join(where)
                cur.execute(f"""
                    SELECT d.name AS dept_name,
                           c.id,
                           c.code,
                           c.name,
                           c.class_year,
                           COALESCE(c.is_compulsory, 0),
                           COALESCE(c.instructor, '')
                    FROM courses c
                    JOIN departments d ON d.id = c.dept_id
                    {where_sql}
                    ORDER BY d.name, c.class_year, c.code
                """, params)
                rows = cur.fetchall()
            else:
                where_dept, dept_params = self._dept_clause("c")
                cur.execute(f"""
                    SELECT
                        c.id,
                        c.code,
                        c.name,
                        c.class_year,
                        COALESCE(c.is_compulsory, 0),
                        COALESCE(c.instructor, '')
                    FROM courses c
                    WHERE (c.code LIKE ? OR c.name LIKE ?)
                    {where_dept}
                    ORDER BY c.class_year, c.code
                """, (qtxt_like, qtxt_like, *dept_params))
                rows = cur.fetchall()

        # Sol tabloyu doldur
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in rows:
            self.tree.insert("", "end", values=tuple("" if x is None else x for x in r))

        # Sağ paneli temizle
        for i in self.stree.get_children():
            self.stree.delete(i)
        self.info.config(text="Bir ders seçiniz.", foreground="#444")

    def load_students(self):
        """Seçili dersin öğrencilerini sağ tarafa yükler ve üstte bilgi etiketini günceller."""
        sel = self.tree.selection()
        if not sel:
            return

        values = self.tree.item(sel[0], "values")
        if not values:
            return

        # ID sütunu dinamik konumda
        try:
            cid = int(values[self._id_col_index])
        except Exception:
            return

        # Diğer sütunlara göre pozisyon (admin'de bir kayma var)
        code = values[self._id_col_index + 1]
        name = values[self._id_col_index + 2]
        class_year = values[self._id_col_index + 3]
        is_compulsory = values[self._id_col_index + 4]
        instructor = values[self._id_col_index + 5] if len(values) > self._id_col_index + 5 else ""

        with get_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT s.number, s.full_name, s.class_year
                FROM enrollments e
                JOIN students s ON s.id = e.student_id
                WHERE e.course_id=?
                ORDER BY s.class_year, s.number
            """, (cid,))
            rows = cur.fetchall()

        # Sağ tabloyu doldur
        for i in self.stree.get_children():
            self.stree.delete(i)
        for r in rows:
            num = r[0] if r[0] is not None else ""
            ful = r[1] if r[1] is not None else ""
            yr  = r[2] if r[2] is not None else ""
            self.stree.insert("", "end", values=(num, ful, yr))

        # Bilgi etiketi
        count = len(rows)
        z_text = "Zorunlu" if str(is_compulsory) == "1" else "Seçmeli"
        instr_text = f" • Hoca: {instructor}" if instructor else ""
        self.info.config(
            text=f"{code} — {name} • Sınıf: {class_year} • Öğrenci: {count} • {z_text}{instr_text}",
            foreground="#222"
        )

    # --------- CSV dışa aktarım ---------

    def export_csv(self):
        """Sağdaki öğrenci listesini CSV olarak dışa aktarır."""
        rows = [self.stree.item(it, "values") for it in self.stree.get_children()]
        if not rows:
            messagebox.showinfo("Bilgi", "Dışa aktarılacak öğrenci bulunmuyor. Önce bir ders seçin.")
            return

        path = filedialog.asksaveasfilename(
            title="CSV olarak kaydet",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["number", "full_name", "class_year"])
                for r in rows:
                    writer.writerow(r)
            messagebox.showinfo("Tamam", "Liste CSV olarak kaydedildi.")
        except Exception as e:
            messagebox.showerror("Hata", f"Kaydetme sırasında hata oluştu:\n{e}")
