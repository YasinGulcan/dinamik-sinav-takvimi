# src/ui/ui_theme.py
import tkinter as tk
from tkinter import ttk

def setup_theme(root: tk.Tk):
    """Uygulama genelinde tutarlı, ferah bir görünüm."""
    style = ttk.Style(root)

    # Varsayılan 'clam' genelde daha modern görünür
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # Renkler ve paddings
    style.configure(".", font=("Segoe UI", 10))
    style.configure("TButton", padding=(10, 6), anchor="center")
    style.configure("TLabel", padding=(2, 2))
    style.configure("TLabelframe", padding=(8, 6))
    style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
    style.configure("TEntry", padding=2)
    style.configure("TCombobox", padding=2)
    style.configure("Treeview", rowheight=26)

    # Toolbar stili
    style.configure("Toolbar.TFrame", background="#f7f7f9")
    style.configure("Toolbar.TButton", padding=(10, 6))
    style.map("TButton",
              relief=[("pressed", "sunken"), ("active", "raised")])

def stripe_treeview(tv: ttk.Treeview):
    """Zebra satır desenleri."""
    tv.tag_configure("oddrow", background="#fafafa")
    for i, iid in enumerate(tv.get_children()):
        tv.item(iid, tags=("oddrow",) if i % 2 else ())
def enable_treeview_features(tv):
    """Zebra desen + sütun tıklayınca sıralama özelliklerini aktif eder."""
    stripe_treeview(tv)  # zebra satırlar

    def treeview_sort_column(tv, col, reverse):
        data = [(tv.set(k, col), k) for k in tv.get_children("")]
        # sayısal değerleri düzgün sıralamak için
        def _key(x):
            v = x[0]
            try:
                return float(v)
            except Exception:
                return str(v)
        data.sort(key=_key, reverse=reverse)
        for index, (_, k) in enumerate(data):
            tv.move(k, "", index)
        stripe_treeview(tv)  # zebra’yı yeniden uygula
        # sütuna tekrar tıklanınca yönü ters çevir
        tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))

    for col in tv["columns"]:
        tv.heading(col, command=lambda c=col: treeview_sort_column(tv, c, False))
