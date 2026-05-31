from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.settings import Settings


class PitcherTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, settings: Settings, **kwargs):
        super().__init__(parent, **kwargs)
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(frame, text="Team Best Pitcher Stats",
                  font=("Arial", 18, "bold")).pack(pady=(0, 8))
        ttk.Label(frame, text="Coming Soon",
                  font=("Arial", 13), foreground="#888888").pack()

    def apply(self) -> None:
        pass
