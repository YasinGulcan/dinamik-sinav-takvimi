# ui/login_view.py
# Basit giriş penceresi: email + şifre -> verify_user

import tkinter as tk
from tkinter import ttk, messagebox

from core.db import verify_user


class LoginView(ttk.Frame):
    def __init__(self, master, on_success, **kwargs):
        """
        on_success: başarılı girişte çağrılacak fonksiyon (parametre: user dict)
        """
        super().__init__(master, **kwargs)
        self.on_success = on_success

        self.email_var = tk.StringVar()
        self.pass_var = tk.StringVar()

        # Başlık
        ttk.Label(self, text="Sınav Takvimi - Giriş", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(10, 8)
        )

        # Email
        ttk.Label(self, text="E-posta").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        e_email = ttk.Entry(self, textvariable=self.email_var, width=32)
        e_email.grid(row=1, column=1, padx=8, pady=6)

        # Şifre
        ttk.Label(self, text="Şifre").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        e_pass = ttk.Entry(self, textvariable=self.pass_var, width=32, show="•")
        e_pass.grid(row=2, column=1, padx=8, pady=6)

        # Giriş butonu
        ttk.Button(self, text="Giriş", command=self._do_login).grid(
            row=3, column=0, columnspan=2, pady=(10, 12)
        )

        # Basit ipucu
        ttk.Label(self, text="İlk giriş için: admin@kocaeli.edu.tr / Admin123!").grid(
            row=4, column=0, columnspan=2, pady=(0, 10)
        )

        # Enter ile giriş
        self.bind_all("<Return>", lambda _e: self._do_login())

        # Odak
        e_email.focus_set()

        for i in range(2):
            self.columnconfigure(i, weight=1)

    def _do_login(self):
        email = (self.email_var.get() or "").strip().lower()
        password = self.pass_var.get() or ""

        if not email or not password:
            messagebox.showwarning("Uyarı", "E-posta ve şifre zorunludur.")
            return

        user = verify_user(email, password)
        if not user:
            messagebox.showerror("Hata", "Giriş başarısız. Bilgileri kontrol edin.")
            return

        messagebox.showinfo("Başarılı", f"Hoş geldiniz: {user['email']}")
        self.on_success(user)
