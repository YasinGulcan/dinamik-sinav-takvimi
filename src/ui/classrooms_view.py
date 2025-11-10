import tkinter as tk
from tkinter import ttk, messagebox
from core.db import get_conn

class ClassroomsView(ttk.Frame):
    def __init__(self, master, user, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user or {}
        self.search_id = tk.StringVar()  # ID ile arama
        self.is_admin = (self.user or {}).get("role") == "admin"

        # --- Bölüm listesi (admin) ---
        self.dept_filter_var = tk.StringVar(value="Tümü")  # sadece admin
        self._dept_list = []          # [(id, name), ...]
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

        # ---------- Form ----------
        frm = ttk.LabelFrame(self, text="Derslik Ekle")
        frm.pack(side="top", fill="x", padx=10, pady=10)

        self.code_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.rows_var = tk.StringVar()
        self.cols_var = tk.StringVar()
        self.seats_var = tk.StringVar(value="2")  # sıra tipi (bir sırada kaç kişi)
        self.cap_pdf_var = tk.StringVar()         # PDF kapasitesi (opsiyonel/manuel)
        self._cap_hint = tk.StringVar(value="Öneri: rows×cols×seats = 0")  # canlı öneri etiketi

        r = 0
        ttk.Label(frm, text="Kod").grid(row=r, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=self.code_var, width=18).grid(row=r, column=1, padx=6, pady=4)

        ttk.Label(frm, text="Ad").grid(row=r, column=2, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=self.name_var, width=26).grid(row=r, column=3, padx=6, pady=4)

        r += 1
        ttk.Label(frm, text="Satır (rows)").grid(row=r, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=self.rows_var, width=10).grid(row=r, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(frm, text="Sütun (cols)").grid(row=r, column=2, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=self.cols_var, width=10).grid(row=r, column=3, sticky="w", padx=6, pady=4)

        r += 1
        ttk.Label(frm, text="Sıra Tipi").grid(row=r, column=0, sticky="e", padx=6, pady=4)
        ttk.Combobox(frm, textvariable=self.seats_var, values=["1", "2", "3"], state="readonly", width=8)\
            .grid(row=r, column=1, sticky="w", padx=6, pady=4)

        # --- KAPASİTE (PDF) MANUEL GİRİŞ ---
        r += 1
        ttk.Label(frm, text="Kapasite (PDF)").grid(row=r, column=0, sticky="e", padx=6, pady=4)
        ttk.Entry(frm, textvariable=self.cap_pdf_var, width=10).grid(row=r, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(frm, textvariable=self._cap_hint, foreground="#666").grid(row=r, column=2, sticky="w", padx=6)

        ttk.Button(frm, text="Ekle", command=self.add_classroom).grid(row=r, column=3, padx=10, sticky="w")

        for c in range(5):
            frm.columnconfigure(c, weight=1)

        # rows/cols/seats değiştikçe kapasiteyi canlı güncelle
        def _recalc(*_args):
            try:
                rr = int(self.rows_var.get() or 0)
                cc = int(self.cols_var.get() or 0)
                ss = int(self.seats_var.get() or 0)
                cap = rr * cc * ss
                self._cap_hint.set(f"Öneri: rows×cols×seats = {cap}")
                if not (self.cap_pdf_var.get() or "").strip():
                    self.cap_pdf_var.set(str(cap))
            except Exception:
                self._cap_hint.set("Öneri: rows×cols×seats = ?")

        self.rows_var.trace_add("write", _recalc)
        self.cols_var.trace_add("write", _recalc)
        self.seats_var.trace_add("write", _recalc)
        _recalc()

        # ---------- Liste ----------
        list_frame = ttk.LabelFrame(self, text="Derslikler")
        list_frame.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

        # Admin'e bölüm filtresi
        if self.is_admin:
            dept_bar = ttk.Frame(list_frame)
            dept_bar.pack(fill="x", padx=6, pady=(4, 6))
            ttk.Label(dept_bar, text="Bölüm:").pack(side="left")
            ttk.Combobox(
                dept_bar, textvariable=self.dept_filter_var,
                values=["Tümü"] + [name for (_, name) in self._dept_list],
                state="readonly", width=32
            ).pack(side="left", padx=6)
            ttk.Button(dept_bar, text="Uygula", command=self.refresh).pack(side="left")

        search_bar = ttk.Frame(list_frame)
        search_bar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Label(search_bar, text="Sınıf ID ile ara:").pack(side="left")
        ttk.Entry(search_bar, textvariable=self.search_id, width=12).pack(side="left", padx=6)
        ttk.Button(search_bar, text="Ara", command=self.refresh).pack(side="left")
        ttk.Button(search_bar, text="Temizle",
                   command=lambda: (self.search_id.set(""), self.refresh())).pack(side="left", padx=(6, 0))

        # Sütunlar
        if self.is_admin:
            cols = ("dept", "id", "code", "name", "capacity", "rows", "cols", "seats")
            headers = ("Bölüm", "ID", "Kod", "Ad", "Kapasite", "Rows", "Cols", "Sıra Tipi")
            self._id_col_index = 1
        else:
            cols = ("id", "code", "name", "capacity", "rows", "cols", "seats")
            headers = ("ID", "Kod", "Ad", "Kapasite", "Rows", "Cols", "Sıra Tipi")
            self._id_col_index = 0

        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=12)
        for c, text in zip(cols, headers):
            self.tree.heading(c, text=text)
            base_w = 90 if c in ("id", "rows", "cols", "seats") else 140
            if c == "dept":
                base_w = 180
            self.tree.column(c, width=base_w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        btns = ttk.Frame(list_frame)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btns, text="Yenile", command=self.refresh).pack(side="left")
        ttk.Button(btns, text="Sil (seçili)", command=self.delete_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="Düzenle (seçili)", command=self._edit_selected_classroom).pack(side="left", padx=6)
        self.tree.bind("<Double-1>", lambda e: self.after(1, self._edit_selected_classroom))

        # ---------- Görselleştirme ----------
        vis_frame = ttk.LabelFrame(self, text="Oturma Düzeni (Önizleme)")
        vis_frame.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=10)

        self.canvas = tk.Canvas(vis_frame, width=420, height=320, background="#fafafa")
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        ttk.Button(vis_frame, text="Seçiliyi Görselleştir", command=self.visualize_selected).pack(pady=(0, 8))

        self.refresh()

    # ----- DB İşlemleri -----
    def add_classroom(self):
        code = (self.code_var.get() or "").strip()
        name = (self.name_var.get() or "").strip()
        rows = (self.rows_var.get() or "").strip()
        cols = (self.cols_var.get() or "").strip()
        seats = (self.seats_var.get() or "").strip()

        if not (code and name and rows and cols and seats):
            messagebox.showwarning("Uyarı", "Kod, Ad, rows, cols ve sıra tipi zorunludur.")
            return
        try:
            rows_i = int(rows); cols_i = int(cols); seats_i = int(seats)
            if rows_i <= 0 or cols_i <= 0 or seats_i <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Hata", "rows/cols/sıra tipi pozitif tam sayı olmalıdır.")
            return

        capacity_auto = rows_i * cols_i * seats_i
        cap_pdf_txt = (self.cap_pdf_var.get() or "").strip()
        capacity_pdf = int(cap_pdf_txt) if cap_pdf_txt.isdigit() else None

        dept_id = self.user.get("department_id") or 1

        try:
            with get_conn() as con:
                cur = con.cursor()
                # aynı bölümde aynı kod varsa engelle
                cur.execute("SELECT 1 FROM classrooms WHERE dept_id=? AND code=?", (dept_id, code))
                if cur.fetchone():
                    messagebox.showerror("Hata", f"Bu bölümde {code} kodlu derslik zaten var.")
                    return

                cur.execute("""
                    INSERT INTO classrooms
                        (dept_id, code, name, capacity, rows, cols, seats_per_desk, capacity_pdf)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (dept_id, code, name, capacity_auto, rows_i, cols_i, seats_i, capacity_pdf))
            self._clear_form()
            self.refresh()
            messagebox.showinfo("Başarılı", "Derslik eklendi.")
        except Exception as e:
            messagebox.showerror("Hata", f"Kayıt eklenemedi: {e}")

    def _clear_form(self):
        self.code_var.set("")
        self.name_var.set("")
        self.rows_var.set("")
        self.cols_var.set("")
        self.seats_var.set("2")
        self.cap_pdf_var.set("")
        # ipucunu sıfırla
        self._cap_hint.set("Öneri: rows×cols×seats = 0")

    def _selected_dept_filter_id(self):
        """Admin filtre seçiminden dept_id döndür (yoksa None)."""
        if not self.is_admin:
            return None
        val = (self.dept_filter_var.get() or "").strip()
        if not val or val == "Tümü":
            return None
        return self._dept_name_to_id.get(val)

    def refresh(self):
        # tabloyu temizle
        for i in self.tree.get_children():
            self.tree.delete(i)

        q_id = (self.search_id.get() or "").strip()
        dept_filter_id = self._selected_dept_filter_id()
        user_dept_id = self.user.get("department_id")

        with get_conn() as con:
            cur = con.cursor()

            base_select = """
                SELECT
                    d.name AS dept_name,
                    c.id,
                    c.code,
                    c.name,
                    COALESCE(c.capacity_pdf, c.capacity) AS capacity,
                    c.rows,
                    c.cols,
                    c.seats_per_desk
                FROM classrooms c
                LEFT JOIN departments d ON d.id = c.dept_id
            """

            if q_id:
                # ID ile arama (JOIN'li)
                cur.execute(base_select + " WHERE c.id = ?", (q_id,))
                rows = cur.fetchall()
            else:
                where = []
                params = []

                if self.is_admin:
                    if dept_filter_id:
                        where.append("c.dept_id = ?")
                        params.append(dept_filter_id)
                else:
                    # koordinator ise sadece kendi bölümü
                    if user_dept_id:
                        where.append("c.dept_id = ?")
                        params.append(user_dept_id)

                sql = base_select
                if where:
                    sql += " WHERE " + " AND ".join(where)
                sql += " ORDER BY d.name NULLS LAST, c.code"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

        # satırları uygun kolon dizilişine göre ekle
        if self.is_admin:
            # (dept, id, code, name, capacity, rows, cols, seats)
            for dept_name, _id, code, name, capacity, rows_i, cols_i, seats_i in rows:
                self.tree.insert("", "end",
                                 values=(dept_name or "", _id, code, name, capacity, rows_i, cols_i, seats_i))
        else:
            # (id, code, name, capacity, rows, cols, seats)
            for _dept, _id, code, name, capacity, rows_i, cols_i, seats_i in rows:
                self.tree.insert("", "end",
                                 values=(_id, code, name, capacity, rows_i, cols_i, seats_i))

    def delete_selected(self):
        cid = self._get_selected_id()
        if cid is None:
            messagebox.showerror("Derslik", "Seçim okunamadı.")
            return

        if not messagebox.askyesno("Onay", f"ID={cid} derslik silinsin mi?"):
            return
        try:
            with get_conn() as con:
                cur = con.cursor()
                cur.execute("DELETE FROM classrooms WHERE id=?", (cid,))
            self.refresh()
        except Exception as e:
            messagebox.showerror("Hata", f"Silinemedi: {e}")

    # ----- DÜZENLEME -----
    def _edit_selected_classroom(self):
        classroom_id = self._get_selected_id()
        if classroom_id is None:
            messagebox.showerror("Derslik", "Seçim okunamadı.")
            return

        with get_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, code, name, rows, cols, seats_per_desk, COALESCE(capacity_pdf, capacity)
                FROM classrooms
                WHERE id=?
            """, (classroom_id,))
            row = cur.fetchone()
        if not row:
            messagebox.showerror("Derslik", "Kayıt bulunamadı.")
            return

        _id, _code, _name, _rows, _cols, _spd, _cap = row

        # Diyalog
        win = tk.Toplevel(self)
        win.title(f"Derslik Düzenle — {str(_code)}")
        win.geometry("420x320")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        frm = ttk.Frame(win); frm.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Kod:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        v_code = tk.StringVar(value=str(_code))
        ttk.Entry(frm, textvariable=v_code, width=16).grid(row=0, column=1, sticky="w")

        ttk.Label(frm, text="Ad:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        v_name = tk.StringVar(value=str(_name or ""))
        ttk.Entry(frm, textvariable=v_name, width=28).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Satır (rows):").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        v_rows = tk.StringVar(value=str(_rows or 0))
        ttk.Entry(frm, textvariable=v_rows, width=8).grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Sütun (cols):").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        v_cols = tk.StringVar(value=str(_cols or 0))
        ttk.Entry(frm, textvariable=v_cols, width=8).grid(row=3, column=1, sticky="w")

        ttk.Label(frm, text="Sıra başı koltuk (2/3/4):").grid(row=4, column=0, sticky="e", padx=6, pady=6)
        v_spd = tk.StringVar(value=str(_spd or 1))
        ttk.Entry(frm, textvariable=v_spd, width=8).grid(row=4, column=1, sticky="w")

        ttk.Label(frm, text="Kapasite (PDF):").grid(row=5, column=0, sticky="e", padx=6, pady=6)
        v_cap = tk.StringVar(value=str(_cap or 0))
        ttk.Entry(frm, textvariable=v_cap, width=10).grid(row=5, column=1, sticky="w")

        v_hint = tk.StringVar(value="")

        def _mk_hint(*_):
            try:
                r = int(v_rows.get()); c = int(v_cols.get()); s = int(v_spd.get())
                v_hint.set(f"Öneri: rows×cols×seats = {r * c * s}")
            except Exception:
                v_hint.set("Öneri: rows×cols×seats = ?")

        for var in (v_rows, v_cols, v_spd):
            var.trace_add("write", _mk_hint)
        _mk_hint()
        ttk.Label(frm, textvariable=v_hint, foreground="#666").grid(row=5, column=2, columnspan=2, sticky="w", padx=6)

        def _recalc_capacity(*_):
            try:
                r = int(v_rows.get()); c = int(v_cols.get()); s = int(v_spd.get())
                if r < 0 or c < 0 or s <= 0: raise ValueError
                v_cap.set(str(r * c * s))
            except Exception:
                v_cap.set("0")

        for var in (v_rows, v_cols, v_spd):
            var.trace_add("write", _recalc_capacity)
        _recalc_capacity()

        btnf = ttk.Frame(win); btnf.pack(fill="x", padx=12, pady=(0,12))

        def _save():
            code = v_code.get().strip()
            name = v_name.get().strip()
            try:
                rows = int(v_rows.get()); cols = int(v_cols.get()); spd = int(v_spd.get())
                if rows <= 0 or cols <= 0 or spd <= 0: raise ValueError
            except Exception:
                messagebox.showerror("Derslik", "Rows/Cols/SPD pozitif tam sayı olmalı.")
                return
            try:
                capacity = int(v_cap.get())
                if capacity <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("Derslik", "Kapasite (PDF) pozitif tam sayı olmalı.")
                return

            try:
                with get_conn() as con2:
                    cur2 = con2.cursor()
                    # Aynı bölümde aynı koddan ikinci bir kayıt olmasın (kendisi hariç)
                    cur2.execute("""
                        SELECT 1 FROM classrooms
                        WHERE code=? AND id<>?
                    """, (code, classroom_id))
                    if cur2.fetchone():
                        messagebox.showerror("Derslik", f"{code} kodu başka bir derslikte kullanılıyor.")
                        return

                    cur2.execute("""
                        UPDATE classrooms
                        SET code=?, name=?, rows=?, cols=?, seats_per_desk=?, capacity=?
                        WHERE id=?
                    """, (code, name, rows, cols, spd, capacity, classroom_id))
                try:
                    self.refresh()
                except Exception:
                    pass
                win.destroy()
            except Exception as e:
                messagebox.showerror("Derslik", f"Güncellenemedi: {e}")

        ttk.Button(btnf, text="Kaydet", command=_save).pack(side="right")
        ttk.Button(btnf, text="İptal", command=win.destroy).pack(side="right", padx=8)

    # ----- Görselleştirme -----
    def visualize_selected(self):
        item = self.tree.selection()
        if not item:
            messagebox.showwarning("Uyarı", "Önizleme için listeden bir derslik seçin.")
            return
        vals = self.tree.item(item[0], "values") or ()
        try:
            if self.is_admin:
                # (dept, id, code, name, capacity, rows, cols, seats)
                _, _, code, name, capacity, rows, cols, seats = vals
            else:
                # (id, code, name, capacity, rows, cols, seats)
                _, code, name, capacity, rows, cols, seats = vals
        except Exception:
            messagebox.showerror("Önizleme", "Seçim okunamadı.")
            return

        try:
            self.draw_layout(int(rows), int(cols), int(seats),
                             title=f"{code} - {name}  (kap: {capacity})")
        except Exception as e:
            messagebox.showerror("Önizleme", f"Çizim sırasında hata: {e}")

    def draw_layout(self, rows, cols, seats, title=""):
        self.canvas.update_idletasks()
        self.canvas.delete("all")
        pad = 12
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        desk_w = max(24, int((cw - 2*pad) / max(cols,1)) - 8)
        desk_h = max(20, int((ch - 2*pad) / max(rows,1)) - 8)

        self.canvas.create_text(10, 12, anchor="nw", text=title, font=("Segoe UI", 9, "bold"))

        y = pad + 18
        for r in range(rows):
            x = pad
            for c in range(cols):
                self.canvas.create_rectangle(x, y, x+desk_w, y+desk_h, outline="#666")
                self.canvas.create_text(x+desk_w/2, y+desk_h/2, text=f"{seats}", font=("Segoe UI", 9))
                x += desk_w + 8
            y += desk_h + 8

    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0], "values") or ()
        id_idx = 1 if self.is_admin else 0
        if len(vals) <= id_idx:
            return None
        try:
            return int(str(vals[id_idx]).strip())
        except Exception:
            return None
