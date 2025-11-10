
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core.db import get_conn


class StudentsView(ttk.Frame):

    def __init__(self, master, user=None, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user or {}

        # ---- ROL/DEPARTMAN DURUMU ----
        self.is_admin = (self.user or {}).get("role") == "admin"
        self.dept_filter_var = tk.StringVar(value="Tümü")   # sadece admin
        self._dept_list = []        # [(id, name)]
        self._dept_name_to_id = {}  # {"Bilgisayar Mühendisliği": 1, ...}

        def _load_departments():
            with get_conn() as con:
                cur = con.cursor()
                cur.execute("SELECT id, name FROM departments ORDER BY name")
                rows = cur.fetchall() or []
            self._dept_list = rows
            self._dept_name_to_id = {name: did for (did, name) in rows}

        if self.is_admin:
            _load_departments()

        # ÜST BAR
        title = ttk.Label(self, text="Öğrenci / Ders Kayıtları", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", padx=12, pady=(10, 0))

        from ui.widgets import Toolbar
        tb = Toolbar(self)

        left = ttk.Frame(tb._left)  # arama kutusu grubu
        left.pack(side="left", padx=0)
        ttk.Label(left, text="Ara (no/ad):").pack(side="left")
        self.q = tk.StringVar()
        ttk.Entry(left, textvariable=self.q, width=30).pack(side="left", padx=6)
        ttk.Button(left, text="Ara", command=self.search).pack(side="left")
        ttk.Button(left, text="Yenile", command=lambda: [self.q.set(''), self.search()]).pack(side="left", padx=6)

        tb.add_right("İçe Aktar", self.open_import_dialog)

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=10, pady=(0, 6))

        # Admin'e bölüm filtresi çubuğu
        if self.is_admin:
            dept_bar = ttk.Frame(self)
            dept_bar.pack(fill="x", padx=10, pady=(0, 6))
            ttk.Label(dept_bar, text="Bölüm:").pack(side="left")
            ttk.Combobox(
                dept_bar,
                textvariable=self.dept_filter_var,
                values=["Tümü"] + [name for (_, name) in self._dept_list],
                state="readonly",
                width=32
            ).pack(side="left", padx=6)
            ttk.Button(dept_bar, text="Uygula", command=self.search).pack(side="left")

        # SOL/SAĞ BÖLME
        split = ttk.Panedwindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=10, pady=8)

        # SOL — Öğrenciler
        left = ttk.LabelFrame(split, text="Öğrenciler")
        split.add(left, weight=1)

        if self.is_admin:
            cols = ("dept", "id", "number", "full_name", "class_year")
            headers = ("Bölüm", "ID", "Numara", "Ad Soyad", "Sınıf")
        else:
            cols = ("id", "number", "full_name", "class_year")
            headers = ("ID", "Numara", "Ad Soyad", "Sınıf")

        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        for c, h in zip(cols, headers):
            w = 120
            if c == "full_name": w = 220
            if c == "dept": w = 180
            if c in ("id",): w = 90
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")
        from ui.ui_theme import enable_treeview_features
        enable_treeview_features(self.tree)

        # ID'yi gizle (tekil kimlik olarak tutuluyor)
        # (kolon sırası admin/koord. durumuna göre değiştiği için dinamik index bulacağız)
        self._id_col_index = list(self.tree["columns"]).index("id")
        self.tree.column("id", width=0, minwidth=0, stretch=False)

        self.tree.bind("<<TreeviewSelect>>", lambda e: self.load_courses())
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        # SAĞ — Aldığı Dersler
        right = ttk.LabelFrame(split, text="Aldığı Dersler")
        split.add(right, weight=1)

        ccols = ("code", "name", "class_year", "instructor")
        cheaders = ("Kod", "Ad", "Sınıf", "Hoca")
        self.ctree = ttk.Treeview(right, columns=ccols, show="headings", height=16)
        for c, h in zip(ccols, cheaders):
            self.ctree.heading(c, text=h)
            self.ctree.column(c, width=140 if c != "name" else 220, anchor="center")

        self.ctree.pack(fill="both", expand=True, padx=6, pady=6)
        enable_treeview_features(self.ctree)
        # İlk veri yükle
        self.search()

    # ---------- Yardımcılar ----------

    def _dept_clause(self, table_alias: str):
        """Kullanıcının bölümüne göre WHERE filtresi döndürür (admin ise filtre yok)."""
        role = (self.user or {}).get("role")
        dept_id = (self.user or {}).get("department_id")
        if role == "admin" or dept_id is None:
            return "", ()
        return f" AND {table_alias}.dept_id=?", (dept_id,)

    # ---------- Arama & Listeleme ----------

    def search(self):
        qtxt = f"%{self.q.get().strip()}%"

        with get_conn() as con:
            cur = con.cursor()
            if self.is_admin:
                # Admin: opsiyonel bölüm filtresi + bölüm adını göster
                where = ["(s.number LIKE ? OR s.full_name LIKE ?)"]
                params = [qtxt, qtxt]
                chosen = self.dept_filter_var.get()
                if chosen and chosen != "Tümü":
                    did = self._dept_name_to_id.get(chosen)
                    where.append("s.dept_id = ?")
                    params.append(did)
                where_sql = " WHERE " + " AND ".join(where) if where else ""
                cur.execute(f"""
                    SELECT d.name, s.id, s.number, s.full_name, s.class_year
                    FROM students s
                    JOIN departments d ON d.id = s.dept_id
                    {where_sql}
                    ORDER BY d.name, s.class_year, s.number
                """, params)
                rows = cur.fetchall()
            else:
                # Koordinatör: sadece kendi bölümü
                where_dept, dept_params = self._dept_clause("s")
                cur.execute(f"""
                    SELECT s.id, s.number, s.full_name, s.class_year
                    FROM students s
                    WHERE (s.number LIKE ? OR s.full_name LIKE ?)
                    {where_dept}
                    ORDER BY s.class_year, s.number
                """, (qtxt, qtxt, *dept_params))
                rows = cur.fetchall()

        # Sol tabloyu doldur
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in rows:
            self.tree.insert("", "end", values=tuple("" if x is None else x for x in r))

        # Sağ tabloyu temizle
        for i in self.ctree.get_children():
            self.ctree.delete(i)

        # İlk satırı seçip dersleri getir (varsa)
        kids = self.tree.get_children()
        if kids:
            first = kids[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.load_courses()

    def load_courses(self):
        sel = self.tree.selection()
        if not sel:
            f = self.tree.focus()
            if f:
                sel = (f,)
            else:
                return

        values = self.tree.item(sel[0], "values")
        if not values:
            return

        # ID, kolonların sırasına göre dinamik index’ten okunur
        try:
            sid = int(values[self._id_col_index])
        except Exception:
            return

        # Dersleri çek
        where_dept, dept_params = self._dept_clause("c")
        sql = f"""
            SELECT c.code, c.name, c.class_year, COALESCE(c.instructor,'')
            FROM enrollments e
            JOIN courses c ON c.id = e.course_id
            WHERE e.student_id=? {where_dept}
            ORDER BY c.class_year, c.code
        """
        params = (sid, *dept_params)

        with get_conn() as con:
            cur = con.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        # Sağ tabloyu doldur
        for i in self.ctree.get_children():
            self.ctree.delete(i)
        for r in rows:
            code, name, yr, inst = r
            self.ctree.insert("", "end", values=(
                "" if code is None else code,
                "" if name is None else name,
                "" if yr   is None else yr,
                "" if inst is None else inst
            ))

    # ---------- İçe Aktarım ----------

    def open_import_dialog(self):
        """ImportView'i diyalog olarak açar (Önizle → Sütun Eşle → Dry-Run → DB'ye Aktar)."""
        from ui.import_view import ImportView
        top = tk.Toplevel(self)
        top.title("Veri İçe Aktarımı")
        top.geometry("980x560")
        ImportView(top, user=self.user).pack(fill="both", expand=True)
