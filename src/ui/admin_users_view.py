# admin_users_view.py – Admin için kullanıcı yönetimi (listeleme + ekleme)
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import hashlib

from core.db import get_conn

try:
    # Varsa db._hash_pw kullan (demo için basit sha256)
    from core.db import _hash_pw as hash_password
except Exception:
    def hash_password(pw: str) -> str:
        return hashlib.sha256(pw.encode("utf-8")).hexdigest()


class AdminUsersView(ttk.Frame):

    def __init__(self, master, user, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user

        # Üst bar
        bar = ttk.Frame(self); bar.pack(fill="x", padx=10, pady=8)
        ttk.Label(bar, text="Kullanıcı Yönetimi (yalnızca admin)").pack(side="left")

        # Split: Sol (liste), Sağ (ekleme formu)
        split = ttk.Panedwindow(self, orient="horizontal"); split.pack(fill="both", expand=True, padx=10, pady=8)

        # Sol: kullanıcı listesi
        left = ttk.LabelFrame(split, text="Kullanıcılar")
        split.add(left, weight=3)

        cols = ("id", "email", "role", "department")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18)
        headers = ("ID", "E-posta", "Rol", "Bölüm")
        widths  = (60, 260, 120, 240)
        for c,h,w in zip(cols, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        # Sağ: ekleme formu
        right = ttk.LabelFrame(split, text="Yeni Kullanıcı Ekle")
        split.add(right, weight=2)

        frm = ttk.Frame(right); frm.pack(fill="x", padx=10, pady=10)

        ttk.Label(frm, text="E-posta:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.email_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.email_var, width=32).grid(row=0, column=1, sticky="w")

        ttk.Label(frm, text="Şifre:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.pw_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.pw_var, width=32, show="•").grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Rol:").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        self.role_var = tk.StringVar(value="koordinator")
        ttk.Combobox(frm, textvariable=self.role_var, values=["admin","koordinator"], state="readonly", width=29)\
            .grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Bölüm:").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        self.dept_var = tk.StringVar()
        self.dept_cb = ttk.Combobox(frm, textvariable=self.dept_var, state="readonly", width=29)
        self.dept_cb.grid(row=3, column=1, sticky="w")

        btns = ttk.Frame(right); btns.pack(fill="x", padx=10, pady=(0,10))
        ttk.Button(btns, text="Kullanıcı Ekle", command=self.add_user).pack(side="left")
        ttk.Button(btns, text="Yenile", command=self.refresh).pack(side="left", padx=8)

        # veri yükle
        self._load_departments()
        self.refresh()

    # --- Data loaders ---

    def _load_departments(self):
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT id, name FROM departments ORDER BY name")
            rows = cur.fetchall()
        self._departments = rows  # [(id, name), ...]
        self.dept_cb["values"] = [r[1] for r in rows]
        if rows and not self.dept_var.get():
            self.dept_var.set(rows[0][1])

    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT u.id, u.email, u.role, COALESCE(d.name,'(yok)')
                FROM users u
                LEFT JOIN departments d ON d.id = u.department_id
                ORDER BY u.role DESC, u.email
            """)
            rows = cur.fetchall()
        for r in rows:
            self.tree.insert("", "end", values=r)

    # --- Actions ---

    def _dept_id_from_name(self, name: str):
        for did, dname in getattr(self, "_departments", []):
            if dname == name:
                return did
        return None

    def add_user(self):
        email = self.email_var.get().strip()
        pw    = self.pw_var.get().strip()
        role  = self.role_var.get().strip()
        dept_name = self.dept_var.get().strip()
        dept_id = self._dept_id_from_name(dept_name)

        # basit kontroller
        if not email or "@" not in email:
            messagebox.showwarning("Uyarı", "Geçerli bir e-posta giriniz.")
            return
        if not pw or len(pw) < 6:
            messagebox.showwarning("Uyarı", "Şifre en az 6 karakter olmalı.")
            return
        if role not in ("admin","koordinator"):
            messagebox.showwarning("Uyarı", "Rol 'admin' veya 'koordinator' olmalı.")
            return

        try:
            with get_conn() as con:
                cur = con.cursor()
                cur.execute("""
                    INSERT INTO users(email, password_hash, role, department_id)
                    VALUES (?, ?, ?, ?)
                """, (email, hash_password(pw), role, dept_id))
            messagebox.showinfo("Tamam", "Kullanıcı eklendi.")
            # alanları temizle
            self.pw_var.set("")
            self.refresh()
        except sqlite3.IntegrityError:
            messagebox.showerror("Hata", "Bu e-posta zaten kayıtlı.")
        except Exception as e:
            messagebox.showerror("Hata", f"Kullanıcı eklenemedi: {e}")
