# src/ui/widgets.py
import tkinter as tk
from tkinter import ttk

class Toolbar(ttk.Frame):
    """Düğmeleri tek hizada, ferah bir üst bar olarak göstermek için."""
    def __init__(self, master, **kw):
        super().__init__(master, style="Toolbar.TFrame", **kw)
        self.pack(fill="x", padx=10, pady=8)
        self._left = ttk.Frame(self, style="Toolbar.TFrame")
        self._left.pack(side="left")
        self._right = ttk.Frame(self, style="Toolbar.TFrame")
        self._right.pack(side="right")

    def add_left(self, text, command=None, width=None):
        b = ttk.Button(self._left, text=text, command=command, style="Toolbar.TButton")
        if width: b.config(width=width)
        b.pack(side="left", padx=4)
        return b

    def add_right(self, text, command=None, width=None):
        b = ttk.Button(self._right, text=text, command=command, style="Toolbar.TButton")
        if width: b.config(width=width)
        b.pack(side="left", padx=4)
        return b
