# src/ui/main_view.py

import tkinter as tk
from tkinter import ttk
from core.db import get_conn

from .classrooms_view import ClassroomsView
from .import_view import ImportView
from .data_status_view import DataStatusView
from .courses_view import CoursesView
from .students_view import StudentsView
from .schedule_view import ScheduleView


class MainView(ttk.Frame):

    def __init__(self, master, user, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user

        # === ÜST MENÜ BAR =============
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=6)

        # --- sadece ADMIN'e görünür: Kullanıcı Yönetimi
        if self.user.get("role") == "admin":
            self.btn_user_mgmt = ttk.Button(bar, text="Kullanıcı Yönetimi", command=self.open_user_mgmt)
            self.btn_user_mgmt.pack(side="left", padx=8)
        else:
            self.btn_user_mgmt = None

        ttk.Label(bar, text=f"Ana Ekran — Rol: {user.get('role', '')}").pack(side="left", padx=8)

        # Veri durumu (her zaman erişilebilir)
        self.btn_status = ttk.Button(bar, text="Veri Durumu", command=self.open_status)
        self.btn_status.pack(side="left", padx=8)

        # Sınav Programı
        self.btn_schedule = ttk.Button(bar, text="Sınav Programı", command=self.open_schedule)
        self.btn_schedule.pack(side="left", padx=8)

        # Diğer menüler
        self.btn_classrooms = ttk.Button(bar, text="Derslikler", command=self.open_classrooms)
        self.btn_classrooms.pack(side="left", padx=8)

        self.btn_import = ttk.Button(bar, text="İçe Aktarım", command=self.open_import)
        self.btn_import.pack(side="left", padx=8)

        self.btn_courses = ttk.Button(bar, text="Ders Menüsü", command=self.open_courses)
        self.btn_courses.pack(side="left", padx=8)

        self.btn_students = ttk.Button(bar, text="Öğrenci Menüsü", command=self.open_students)
        self.btn_students.pack(side="left", padx=8)

        # Hızlı yenile (derslik eklendikten sonra kilit durumunu güncelle)
        ttk.Button(bar, text="Yenile", command=self._apply_lock_state).pack(side="left", padx=8)

        # === KULLANICI ROZETİ + ÇIKIŞ ===============
        user_bar = ttk.Frame(self)
        user_bar.pack(fill="x", padx=10, pady=(0, 4))

        who = f"{user.get('email', '?')} ({user.get('role', '?')})"
        dept = user.get("department_id")
        ttk.Label(
            user_bar,
            text=f"Hoş geldiniz: {who}  • Bölüm ID: {dept}",
            foreground="#444"
        ).pack(side="left")

        def _logout():
            # Ekranı temizle, login ekranına dön
            root = self.winfo_toplevel()
            for w in root.winfo_children():
                w.destroy()
            from ui.login_view import LoginView
            LoginView(root, on_success=lambda u: __class__(root, u).pack(fill='both', expand=True)).pack(fill="both", expand=True)

        ttk.Button(user_bar, text="Çıkış Yap", command=_logout).pack(side="right")

        # === ANA İÇERİK MESAJI ========
        self.info_label = ttk.Label(self, text="Menüler: Derslikler, İçe Aktarım, Program, Oturma Planı...")
        self.info_label.pack(pady=40)

        # İlk açılışta kilit durumunu uygula
        self._apply_lock_state()

    # --- PENCERE AÇAN YARDIMCI METOTLAR ----
    def open_import(self):
        top = tk.Toplevel(self)
        top.title("İçe Aktarım (Önizleme)")
        top.geometry("900x520")
        ImportView(top, user=self.user).pack(fill="both", expand=True)

    def open_classrooms(self):
        top = tk.Toplevel(self)
        top.title("Derslikler")
        top.geometry("900x520")
        ClassroomsView(top, user=self.user).pack(fill="both", expand=True)

        # Pencere kapatılınca kilit durumunu tazele
        def _on_close():
            try:
                top.destroy()
            finally:
                self._apply_lock_state()
        top.protocol("WM_DELETE_WINDOW", _on_close)

    def open_status(self):
        top = tk.Toplevel(self)
        top.title("Veri Durumu")
        top.geometry("900x520")
        # Bölüm filtresi doğru çalışsın diye user'ı da geçiriyoruz
        DataStatusView(top, user=self.user).pack(fill="both", expand=True)

    def open_courses(self):
        top = tk.Toplevel(self)
        top.title("Ders Menüsü")
        top.geometry("1000x560")
        view = CoursesView(top, self.user)  # user parametresi pozisyonel
        view.pack(fill="both", expand=True)

    def open_students(self):
        top = tk.Toplevel(self)
        top.title("Öğrenci Menüsü")
        top.geometry("1000x560")
        # Tutarlı: direkt user ile başlat
        view = StudentsView(top, user=self.user)
        view.pack(fill="both", expand=True)

    def open_schedule(self):
        top = tk.Toplevel(self)
        top.title("Sınav Programı")
        top.geometry("1000x600")
        ScheduleView(top, user=self.user).pack(fill="both", expand=True)

    def open_user_mgmt(self):
        top = tk.Toplevel(self)
        top.title("Kullanıcı Yönetimi")
        top.geometry("900x560")
        # lazy import: döngüsel import riskini azaltır
        from .admin_users_view import AdminUsersView
        AdminUsersView(top, user=self.user).pack(fill="both", expand=True)

    # --- KİLİT KONTROL -----
    def _has_min_classrooms(self) -> bool:
        with get_conn() as con:
            cur = con.cursor()
            role = self.user.get("role")
            dept = self.user.get("department_id")
            if role == "admin" or not dept:
                cur.execute("SELECT COUNT(*) FROM classrooms")
            else:
                cur.execute("SELECT COUNT(*) FROM classrooms WHERE dept_id=?", (dept,))
            count = cur.fetchone()[0]
        return count > 0

    def _apply_lock_state(self):
        """
        Derslik yoksa: yalnızca 'Derslikler' açık, diğer menüler kilitli.
        Derslik varsa: tüm menüler açılır.
        """
        has_rooms = self._has_min_classrooms()

        def _set(btn, enabled: bool):
            if not btn:
                return
            if enabled:
                try:
                    btn.state(("!disabled",))
                except Exception:
                    btn["state"] = "normal"
            else:
                try:
                    btn.state(("disabled",))
                except Exception:
                    btn["state"] = "disabled"

        # Derslik dışı menüler kilitlenir/açılır
        _set(self.btn_import,   has_rooms)
        _set(self.btn_courses,  has_rooms)
        _set(self.btn_students, has_rooms)
        _set(self.btn_schedule, has_rooms)
        _set(self.btn_status,   True)       # Veri Durumu her zaman açık
        _set(self.btn_classrooms, True)     # Derslikler her zaman açık

        # Bilgilendirici not
        if not has_rooms:
            self.info_label.configure(
                text="Not: Diğer menüler derslik eklenmeden açılmaz.\nLütfen önce en az bir derslik ekleyin."
            )
        else:
            self.info_label.configure(
                text="Menüler: Derslikler, İçe Aktarım, Program, Oturma Planı..."
            )
