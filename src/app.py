import tkinter as tk
from tkinter import ttk
from ui.ui_theme import setup_theme
from core.db import init_db
from ui.login_view import LoginView
from ui.main_view import MainView

def open_main(root, user):
    # Tüm içeriği temizle ve MainView'i yerleştir
    for w in root.winfo_children():
        w.destroy()

    root.title("Sınav Takvimi - Ana Ekran")
    MainView(root, user).pack(fill="both", expand=True)

def main():
    init_db()

    root = tk.Tk()
    setup_theme(root)

    root.title("Sınav Takvimi - Giriş")
    root.geometry("480x240")

    # LoginView'i kur: başarılı olunca open_main çağrılacak
    view = LoginView(root, on_success=lambda user: open_main(root, user))
    view.pack(fill="both", expand=True)
    root.mainloop()

if __name__ == "__main__":
    main()
