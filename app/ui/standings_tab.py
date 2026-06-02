from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageTk

from app.settings import Settings
from app.utils.image_utils import apply_export_margin
from app.cards.standings_card import (
    StandingsCardConfig, StandingsCardRenderer,
    suggest_column_mode, EXTENDED_MIN_WIDTH_IN,
)
from app.data.mlb_api import SCOPE_OPTIONS

# Thumbnail dimensions (fits inside the preview panel)
THUMB_W = 480
THUMB_H = 320


class StandingsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, settings: Settings, **kwargs):
        super().__init__(parent, **kwargs)
        self.settings = settings
        self._card_image: Image.Image | None = None
        self._thumb_photo: ImageTk.PhotoImage | None = None
        self._fetching = False
        self._build()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build(self) -> None:
        # Split into left controls + right preview
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        controls = ttk.Frame(paned, width=280)
        paned.add(controls, weight=0)

        preview_frame = ttk.LabelFrame(paned, text="Preview")
        paned.add(preview_frame, weight=1)

        self._build_controls(controls)
        self._build_preview(preview_frame)

    def _build_controls(self, parent: ttk.Frame) -> None:
        pad = {"padx": 8, "pady": 4}

        # ---- Card Size ----
        size_frame = ttk.LabelFrame(parent, text="Card Size")
        size_frame.pack(fill="x", padx=8, pady=(8, 4))

        self._width_var = tk.DoubleVar(value=self.settings.standings_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.standings_height_in)

        row = ttk.Frame(size_frame)
        row.pack(anchor="w", **pad)
        ttk.Label(row, text="W (in):").pack(side="left")
        self._w_spin = ttk.Spinbox(row, from_=2.0, to=24.0, increment=0.5,
                              textvariable=self._width_var, width=5)
        self._w_spin.pack(side="left", padx=3)
        self._w_spin.bind("<FocusOut>", self._on_size_changed)
        self._w_spin.bind("<<Increment>>", self._on_size_changed)
        self._w_spin.bind("<<Decrement>>", self._on_size_changed)

        ttk.Label(row, text="H (in):").pack(side="left", padx=(8, 0))
        self._h_spin = ttk.Spinbox(row, from_=2.0, to=24.0, increment=0.5,
                              textvariable=self._height_var, width=5)
        self._h_spin.pack(side="left", padx=3)
        self._h_spin.bind("<FocusOut>", self._on_size_changed)
        self._h_spin.bind("<<Increment>>", self._on_size_changed)
        self._h_spin.bind("<<Decrement>>", self._on_size_changed)

        self._use_global_size_var = tk.BooleanVar(
            value=self.settings.standings_use_global_size)
        self._use_global_chk = ttk.Checkbutton(
            size_frame, variable=self._use_global_size_var,
            command=self._on_use_global_size_changed)
        self._use_global_chk.pack(anchor="w", padx=8, pady=(0, 2))

        self._orient_lbl = ttk.Label(size_frame, text="", foreground="#555555")
        self._orient_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        if self.settings.standings_use_global_size:
            self._w_spin.config(state="disabled")
            self._h_spin.config(state="disabled")
        self._update_orientation_label()
        self._refresh_global_size_label()

        # ---- Scope ----
        scope_frame = ttk.LabelFrame(parent, text="Scope")
        scope_frame.pack(fill="x", padx=8, pady=4)

        self._scope_var = tk.StringVar(value=self.settings.standings_scope)
        ttk.Combobox(scope_frame, textvariable=self._scope_var,
                     values=SCOPE_OPTIONS, state="readonly", width=18).pack(
            anchor="w", **pad)

        # ---- Columns ----
        col_frame = ttk.LabelFrame(parent, text="Columns")
        col_frame.pack(fill="x", padx=8, pady=4)

        self._col_mode_var = tk.StringVar(value=self.settings.standings_column_mode)
        for val, label in (("auto", "Auto (suggested)"),
                            ("standard", "Standard  (W L PCT GB)"),
                            ("extended", "Extended  (+Home Away L10 Streak)")):
            ttk.Radiobutton(col_frame, text=label, variable=self._col_mode_var,
                            value=val, command=self._update_col_suggestion).pack(
                anchor="w", padx=8, pady=1)

        self._col_suggest_lbl = ttk.Label(col_frame, text="", foreground="#2255aa")
        self._col_suggest_lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self._update_col_suggestion()

        # ---- Display Options ----
        opt_frame = ttk.LabelFrame(parent, text="Display Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        self._show_logos_var = tk.BooleanVar(value=self.settings.standings_show_logos)
        ttk.Checkbutton(opt_frame, text="Show team logos",
                         variable=self._show_logos_var).pack(anchor="w", **pad)

        self._show_ts_var = tk.BooleanVar(value=self.settings.standings_show_timestamp)
        ttk.Checkbutton(opt_frame, text="Show 'data as of' timestamp",
                         variable=self._show_ts_var).pack(anchor="w", padx=8, pady=2)

        self._show_explainers_var = tk.BooleanVar(
            value=self.settings.standings_show_col_explainers)
        ttk.Checkbutton(opt_frame, text="Show column explainers",
                         variable=self._show_explainers_var).pack(
            anchor="w", padx=8, pady=(0, 4))

        # ---- Background Color ----
        bg_frame = ttk.LabelFrame(parent, text="Background Color")
        bg_frame.pack(fill="x", padx=8, pady=4)

        self._bg_var = tk.StringVar(value=self.settings.standings_bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_var, width=9).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=3, relief="sunken",
                                   background=self.settings.standings_bg_color)
        self._bg_swatch.pack(side="left", padx=3)
        ttk.Button(bg_row, text="Pick…", command=self._pick_bg_color).pack(side="left")
        self._bg_var.trace_add("write", self._on_bg_changed)

        # ---- Fetch & Preview ----
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=8)

        fetch_row = ttk.Frame(parent)
        fetch_row.pack(fill="x", padx=8, pady=2)
        self._fetch_btn = ttk.Button(fetch_row, text="Fetch & Preview",
                                      command=self._fetch_and_preview)
        self._fetch_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._refresh_btn = ttk.Button(fetch_row, text="↺ Refresh",
                                        command=self._force_refresh, width=9)
        self._refresh_btn.pack(side="left")

        self._full_preview_btn = ttk.Button(parent, text="Full Preview…",
                                             command=self._full_preview,
                                             state="disabled")
        self._full_preview_btn.pack(fill="x", padx=8, pady=2)

        self._status_lbl = ttk.Label(parent, text="", wraplength=260,
                                      foreground="#aa2200")
        self._status_lbl.pack(anchor="w", padx=8, pady=2)

        # ---- Export ----
        export_frame = ttk.LabelFrame(parent, text="Export")
        export_frame.pack(fill="x", padx=8, pady=(4, 8))

        self._export_name_var = tk.StringVar(
            value=self.settings.standings_export_filename)
        ttk.Label(export_frame, text="Filename (no extension):").pack(
            anchor="w", padx=8, pady=(4, 0))
        ttk.Entry(export_frame, textvariable=self._export_name_var, width=24).pack(
            fill="x", padx=8, pady=2)

        self._append_ts_var = tk.BooleanVar(
            value=self.settings.standings_append_timestamp)
        ttk.Checkbutton(export_frame, text="Append timestamp to filename",
                         variable=self._append_ts_var).pack(
            anchor="w", padx=8, pady=(0, 4))

        btn_row = ttk.Frame(export_frame)
        btn_row.pack(fill="x", padx=8, pady=(2, 8))
        self._export_png_btn = ttk.Button(btn_row, text="Export PNG",
                                           command=lambda: self._export("PNG"),
                                           state="disabled")
        self._export_png_btn.pack(side="left", padx=(0, 4))
        self._export_jpg_btn = ttk.Button(btn_row, text="Export JPG",
                                           command=lambda: self._export("JPEG"),
                                           state="disabled")
        self._export_jpg_btn.pack(side="left")

    def _build_preview(self, parent: ttk.LabelFrame) -> None:
        self._canvas = tk.Canvas(parent, bg="#CCCCCC", width=THUMB_W, height=THUMB_H)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self._canvas_img_id = None
        self._resize_after_id = None
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._draw_placeholder()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_orientation_label(self) -> None:
        try:
            if self._use_global_size_var.get():
                w = self.settings.card_width_in
                h = self.settings.card_height_in
            else:
                w = self._width_var.get()
                h = self._height_var.get()
        except tk.TclError:
            return
        label = "Landscape" if w >= h else "Portrait"
        self._orient_lbl.config(text=f"Orientation: {label}")

    def _on_size_changed(self, *_) -> None:
        self._update_orientation_label()
        self._update_col_suggestion()

    def _refresh_global_size_label(self) -> None:
        w = self.settings.card_width_in
        h = self.settings.card_height_in
        self._use_global_chk.config(text=f"Use global size ({w:g} \u00d7 {h:g} in)")

    def _on_use_global_size_changed(self) -> None:
        use_global = self._use_global_size_var.get()
        state = "disabled" if use_global else "normal"
        self._w_spin.config(state=state)
        self._h_spin.config(state=state)
        self._update_orientation_label()
        self._update_col_suggestion()

    def _update_col_suggestion(self) -> None:
        try:
            w = self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get()
        except tk.TclError:
            return
        suggested = suggest_column_mode(w)
        mode = self._col_mode_var.get()
        if mode == "auto":
            self._col_suggest_lbl.config(
                text=f"→ Will use {suggested} at this width")
        elif mode == "extended" and w < EXTENDED_MIN_WIDTH_IN:
            self._col_suggest_lbl.config(
                text=f"⚠ Extended may be crowded below {EXTENDED_MIN_WIDTH_IN}\"")
        else:
            self._col_suggest_lbl.config(text="")

    def _pick_bg_color(self) -> None:
        from tkinter import colorchooser
        color = colorchooser.askcolor(
            initialcolor=self._bg_var.get(), title="Background Color")
        if color and color[1]:
            self._bg_var.set(color[1])

    def _on_bg_changed(self, *_) -> None:
        try:
            self._bg_swatch.config(background=self._bg_var.get())
        except tk.TclError:
            pass

    def _on_canvas_resize(self, _event=None) -> None:
        """Debounced handler — redraws thumbnail 150 ms after resize stops."""
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        if self._card_image is not None:
            self._resize_after_id = self.after(150, self._show_thumbnail,
                                                self._card_image)
        else:
            self._resize_after_id = self.after(150, self._draw_placeholder)

    def _draw_placeholder(self) -> None:
        self._canvas.delete("all")
        cw = self._canvas.winfo_reqwidth()
        ch = self._canvas.winfo_reqheight()
        self._canvas.create_text(
            cw // 2, ch // 2,
            text="Click 'Fetch & Preview' to generate the card",
            fill="#666666", font=("Arial", 11))

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_lbl.config(text=msg,
                                 foreground="#aa2200" if error else "#226622")

    # ------------------------------------------------------------------
    # Fetch & render
    # ------------------------------------------------------------------
    def _fetch_and_preview(self, force: bool = False) -> None:
        if self._fetching:
            return
        self._fetching = True
        self._fetch_btn.config(state="disabled")
        self._refresh_btn.config(state="disabled")
        self._set_status("Fetching standings…", error=False)
        self._canvas.delete("all")
        self._canvas.create_text(
            THUMB_W // 2, THUMB_H // 2,
            text="Fetching data…", fill="#555555", font=("Arial", 11))
        threading.Thread(
            target=self._do_fetch, args=(force,), daemon=True).start()

    def _force_refresh(self) -> None:
        self._fetch_and_preview(force=True)

    def _do_fetch(self, force: bool = False) -> None:
        from app.data.mlb_api import fetch_standings_cached
        try:
            block, source = fetch_standings_cached(
                ttl_minutes=self.settings.data_cache_ttl_minutes,
                working_dir=self.settings.working_dir,
                force_refresh=force,
            )
            self.after(0, lambda: self._do_render(block, source))
        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._on_fetch_error(m))

    def _do_render(self, block, source: str = "live") -> None:
        import datetime
        try:
            cfg = self._build_card_config()
            renderer = StandingsCardRenderer(cfg, block,
                                             working_dir=self.settings.working_dir)
            img = renderer.render()
            self._card_image = img
            self._show_thumbnail(img)
            age_sec = (datetime.datetime.now() - block.as_of).total_seconds()
            if source == "live":
                status = f"Live data · fetched just now"
            else:
                mins = int(age_sec // 60)
                secs = int(age_sec % 60)
                age_str = f"{mins}m {secs}s ago" if mins else f"{secs}s ago"
                label = "Memory cache" if source == "memory" else "Disk cache"
                status = f"{label} · fetched {age_str}  (TTL {self.settings.data_cache_ttl_minutes} min)"
            if getattr(renderer, 'last_warning', None):
                self._status_lbl.config(
                    text=status + f"\n\u26a0 {renderer.last_warning}",
                    foreground="#cc6600")
            else:
                self._set_status(status, error=False)
            self._full_preview_btn.config(state="normal")
            self._export_png_btn.config(state="normal")
            self._export_jpg_btn.config(state="normal")
        except Exception as exc:
            self._on_fetch_error(f"Render error: {exc}")
        finally:
            self._fetching = False
            self._fetch_btn.config(state="normal")
            self._refresh_btn.config(state="normal")

    def _on_fetch_error(self, msg: str) -> None:
        self._fetching = False
        self._fetch_btn.config(state="normal")
        self._refresh_btn.config(state="normal")
        self._draw_placeholder()
        self._set_status(f"Error: {msg}", error=True)

    def _build_card_config(self) -> StandingsCardConfig:
        return StandingsCardConfig(
            width_in=self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get(),
            height_in=self.settings.card_height_in if self._use_global_size_var.get() else self._height_var.get(),
            dpi=self.settings.dpi,
            bg_color=self._bg_var.get(),
            scope=self._scope_var.get(),
            column_mode=self._col_mode_var.get(),
            show_logos=self._show_logos_var.get(),
            show_timestamp=self._show_ts_var.get(),
            show_col_explainers=self._show_explainers_var.get(),
            col_explainer_sep=self.settings.col_explainer_sep,
        )

    def _show_thumbnail(self, img: Image.Image) -> None:
        cw = self._canvas.winfo_width() or THUMB_W
        ch = self._canvas.winfo_height() or THUMB_H
        # Maintain aspect ratio within canvas
        ratio = min(cw / img.width, ch / img.height)
        tw = max(1, round(img.width * ratio))
        th = max(1, round(img.height * ratio))
        thumb = img.resize((tw, th), Image.LANCZOS)
        self._thumb_photo = ImageTk.PhotoImage(thumb)
        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, anchor="center",
                                   image=self._thumb_photo)

    # ------------------------------------------------------------------
    # Full preview
    # ------------------------------------------------------------------
    def _full_preview(self) -> None:
        if self._card_image is None:
            return
        win = tk.Toplevel(self)
        win.title("Standings Card — Full Preview")
        img = self._card_image
        # Cap display at 1200px wide for screen fit
        max_w = 1200
        ratio = min(1.0, max_w / img.width)
        dw = round(img.width * ratio)
        dh = round(img.height * ratio)
        display = img.resize((dw, dh), Image.LANCZOS) if ratio < 1.0 else img
        photo = ImageTk.PhotoImage(display)
        lbl = tk.Label(win, image=photo)
        lbl.image = photo  # keep reference
        lbl.pack()
        win.resizable(False, False)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _export(self, fmt: str) -> None:
        if self._card_image is None:
            messagebox.showwarning("Nothing to export",
                                   "Generate a preview first.")
            return
        working_dir = self.settings.working_dir
        if not working_dir or not os.path.isdir(working_dir):
            answer = messagebox.askyesno(
                "Working Directory Not Set",
                "The working directory does not exist.\nChoose a folder now?")
            if answer:
                folder = filedialog.askdirectory(title="Select Output Folder")
                if folder:
                    self.settings.working_dir = folder
                    working_dir = folder
                else:
                    return
            else:
                return
        output_dir = os.path.join(working_dir, "output", "standings")
        os.makedirs(output_dir, exist_ok=True)
        ext = ".png" if fmt == "PNG" else ".jpg"
        raw_name = self._export_name_var.get().strip() or "standings_card"
        # Sanitize: remove characters illegal on Windows/macOS/Linux filesystems
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(". ")
        if not base:
            base = "standings_card"
        if self._append_ts_var.get():
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{base}_{ts}"
        filename = base + ext
        out_path = os.path.join(output_dir, filename)
        try:
            cfg = self._build_card_config()
            export_img = apply_export_margin(
                self._card_image, cfg.bg_color,
                self.settings.export_canvas_margin_pct)
            saved = cfg.export(export_img, out_path, fmt)
            messagebox.showinfo("Exported", f"Saved to:\n{saved}")
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Persist settings
    # ------------------------------------------------------------------
    def apply(self) -> None:
        self.settings.standings_width_in = self._width_var.get()
        self.settings.standings_height_in = self._height_var.get()
        self.settings.standings_use_global_size = self._use_global_size_var.get()
        self._refresh_global_size_label()
        self.settings.standings_scope = self._scope_var.get()
        self.settings.standings_column_mode = self._col_mode_var.get()
        self.settings.standings_show_logos = self._show_logos_var.get()
        self.settings.standings_show_timestamp = self._show_ts_var.get()
        self.settings.standings_bg_color = self._bg_var.get()
        self.settings.standings_export_filename = self._export_name_var.get()
        self.settings.standings_append_timestamp = self._append_ts_var.get()
        self.settings.standings_show_col_explainers = self._show_explainers_var.get()
