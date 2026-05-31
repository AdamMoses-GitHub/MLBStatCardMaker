from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from app.settings import Settings


class SettingsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, settings: Settings, **kwargs):
        super().__init__(parent, **kwargs)
        self.settings = settings
        self._build()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}

        # ---- Working Directory ----
        dir_frame = ttk.LabelFrame(self, text="Working Directory")
        dir_frame.pack(fill="x", padx=16, pady=(16, 8))

        self._working_dir_var = tk.StringVar(value=self.settings.working_dir)
        ttk.Label(dir_frame, text="Output folder for cards, logos, and settings:").pack(
            anchor="w", **pad)
        dir_row = ttk.Frame(dir_frame)
        dir_row.pack(fill="x", **pad)
        ttk.Entry(dir_row, textvariable=self._working_dir_var, width=52).pack(
            side="left", fill="x", expand=True)
        ttk.Button(dir_row, text="Browse…", command=self._browse_dir).pack(
            side="left", padx=(6, 0))

        # ---- Default Card Size ----
        size_frame = ttk.LabelFrame(self, text="Default Card Size")
        size_frame.pack(fill="x", padx=16, pady=8)

        self._width_var = tk.DoubleVar(value=self.settings.card_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.card_height_in)

        row = ttk.Frame(size_frame)
        row.pack(anchor="w", **pad)
        ttk.Label(row, text="Width (in):").pack(side="left")
        ttk.Spinbox(row, from_=1.0, to=24.0, increment=0.5,
                    textvariable=self._width_var, width=6,
                    command=self._update_orientation).pack(side="left", padx=4)
        ttk.Label(row, text="Height (in):").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row, from_=1.0, to=24.0, increment=0.5,
                    textvariable=self._height_var, width=6,
                    command=self._update_orientation).pack(side="left", padx=4)
        self._orientation_lbl = ttk.Label(row, text="", foreground="#555555")
        self._orientation_lbl.pack(side="left", padx=(12, 0))
        self._update_orientation()

        # ---- Export DPI ----
        dpi_frame = ttk.LabelFrame(self, text="Export DPI")
        dpi_frame.pack(fill="x", padx=16, pady=8)

        self._dpi_var = tk.IntVar(value=self.settings.dpi)
        dpi_row = ttk.Frame(dpi_frame)
        dpi_row.pack(anchor="w", **pad)
        for dpi_val in (72, 150, 300):
            ttk.Radiobutton(dpi_row, text=str(dpi_val), variable=self._dpi_var,
                            value=dpi_val).pack(side="left", padx=4)
        ttk.Label(dpi_row, text="Custom:").pack(side="left", padx=(16, 0))
        ttk.Spinbox(dpi_row, from_=72, to=1200, increment=50,
                    textvariable=self._dpi_var, width=6).pack(side="left", padx=4)

        # ---- Default Background Color ----
        bg_frame = ttk.LabelFrame(self, text="Default Background Color")
        bg_frame.pack(fill="x", padx=16, pady=8)

        self._bg_color_var = tk.StringVar(value=self.settings.bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_color_var, width=10).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=4, relief="sunken",
                                   background=self.settings.bg_color)
        self._bg_swatch.pack(side="left", padx=4)
        ttk.Button(bg_row, text="Pick Color…", command=self._pick_bg_color).pack(side="left")
        self._bg_color_var.trace_add("write", self._on_bg_color_changed)

        # ---- Data Cache ----
        cache_frame = ttk.LabelFrame(self, text="Data Cache")
        cache_frame.pack(fill="x", padx=16, pady=8)

        self._cache_ttl_var = tk.IntVar(value=self.settings.data_cache_ttl_minutes)
        cache_row = ttk.Frame(cache_frame)
        cache_row.pack(anchor="w", **pad)
        ttk.Label(cache_row, text="Standings cache TTL:").pack(side="left")
        ttk.Spinbox(cache_row, from_=1, to=1440, increment=5,
                    textvariable=self._cache_ttl_var, width=6).pack(
            side="left", padx=4)
        ttk.Label(cache_row, text="minutes").pack(side="left")
        ttk.Label(cache_frame,
                  text="Cached data is re-used within this window. Use '↺ Refresh' to force a live fetch.",
                  foreground="#555555", wraplength=420).pack(
            anchor="w", padx=12, pady=(0, 6))

        ttk.Button(cache_frame, text="Clear Memory Cache",
                   command=self._clear_mem_cache).pack(anchor="w", padx=12, pady=(0, 8))

        # ---- Column Explainer Separator ----
        sep_frame = ttk.LabelFrame(self, text="Column Explainer Separator")
        sep_frame.pack(fill="x", padx=16, pady=8)

        self._expl_sep_var = tk.StringVar(value=self.settings.col_explainer_sep)
        sep_row = ttk.Frame(sep_frame)
        sep_row.pack(anchor="w", padx=12, pady=6)
        for sep_val, sep_label in [
            ("=", "= \u00b7 e.g.  OPS=OBP+SLG"),
            (":", ": \u00b7 e.g.  OPS: OBP+SLG"),
            ("\u2013", "\u2013 \u00b7 e.g.  OPS\u2013OBP+SLG"),
        ]:
            ttk.Radiobutton(sep_row, text=sep_label,
                            variable=self._expl_sep_var,
                            value=sep_val).pack(side="left", padx=(0, 20))

        # ---- Save button ----
        ttk.Button(self, text="Save Settings", command=self.apply).pack(
            anchor="e", padx=16, pady=(8, 16))

    # ------------------------------------------------------------------
    def _browse_dir(self) -> None:
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Working Directory",
                                       initialdir=self._working_dir_var.get())
        if path:
            self._working_dir_var.set(path)

    def _update_orientation(self) -> None:
        try:
            w = self._width_var.get()
            h = self._height_var.get()
        except tk.TclError:
            return
        label = "Landscape" if w >= h else "Portrait"
        self._orientation_lbl.config(text=f"({label})")

    def _pick_bg_color(self) -> None:
        from tkinter import colorchooser
        color = colorchooser.askcolor(
            initialcolor=self._bg_color_var.get(),
            title="Choose Background Color"
        )
        if color and color[1]:
            self._bg_color_var.set(color[1])

    def _on_bg_color_changed(self, *_) -> None:
        try:
            self._bg_swatch.config(background=self._bg_color_var.get())
        except tk.TclError:
            pass

    def _clear_mem_cache(self) -> None:
        from app.data.mlb_api import clear_standings_cache
        clear_standings_cache()
        tk.messagebox.showinfo("Cache Cleared", "In-memory standings cache cleared.")

    # ------------------------------------------------------------------
    def apply(self) -> None:
        """Write UI values back to the settings object."""
        self.settings.working_dir = self._working_dir_var.get()
        self.settings.card_width_in = self._width_var.get()
        self.settings.card_height_in = self._height_var.get()
        self.settings.dpi = self._dpi_var.get()
        self.settings.bg_color = self._bg_color_var.get()
        self.settings.data_cache_ttl_minutes = self._cache_ttl_var.get()
        self.settings.col_explainer_sep = self._expl_sep_var.get()
