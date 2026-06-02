from __future__ import annotations

import datetime
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser

from PIL import Image, ImageTk

from app.settings import Settings
from app.utils.image_utils import apply_export_margin
from app.cards.pitchers_card import (
    PitchersCardConfig, PitchersCardRenderer,
    suggest_column_mode, EXTENDED_MIN_WIDTH_IN, STANDARD_MIN_WIDTH_IN,
)
from app.data.pitchers_api import (
    PITCHER_SCOPE_OPTIONS, PITCHER_TYPE_OPTIONS, SORT_STAT_LABELS,
    fetch_pitchers_cached, filter_pitchers, sort_and_trim,
)

THUMB_W = 480
THUMB_H = 320


class PitcherTab(ttk.Frame):
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
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        controls = ttk.Frame(paned, width=290)
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

        self._width_var  = tk.DoubleVar(value=self.settings.pitchers_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.pitchers_height_in)

        row = ttk.Frame(size_frame)
        row.pack(anchor="w", **pad)
        ttk.Label(row, text="W (in):").pack(side="left")
        self._w_spin = ttk.Spinbox(row, from_=2.0, to=24.0, increment=0.5,
                             textvariable=self._width_var, width=5)
        self._w_spin.pack(side="left", padx=3)
        self._w_spin.bind("<FocusOut>",    self._on_size_changed)
        self._w_spin.bind("<<Increment>>", self._on_size_changed)
        self._w_spin.bind("<<Decrement>>", self._on_size_changed)

        ttk.Label(row, text="H (in):").pack(side="left", padx=(8, 0))
        self._h_spin = ttk.Spinbox(row, from_=2.0, to=24.0, increment=0.5,
                             textvariable=self._height_var, width=5)
        self._h_spin.pack(side="left", padx=3)
        self._h_spin.bind("<FocusOut>",    self._on_size_changed)
        self._h_spin.bind("<<Increment>>", self._on_size_changed)
        self._h_spin.bind("<<Decrement>>", self._on_size_changed)

        self._use_global_size_var = tk.BooleanVar(
            value=self.settings.pitchers_use_global_size)
        self._use_global_chk = ttk.Checkbutton(
            size_frame, variable=self._use_global_size_var,
            command=self._on_use_global_size_changed)
        self._use_global_chk.pack(anchor="w", padx=8, pady=(0, 2))

        self._orient_lbl = ttk.Label(size_frame, text="", foreground="#555555")
        self._orient_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        if self.settings.pitchers_use_global_size:
            self._w_spin.config(state="disabled")
            self._h_spin.config(state="disabled")
        self._update_orientation_label()
        self._refresh_global_size_label()

        # ---- Scope ----
        scope_frame = ttk.LabelFrame(parent, text="Scope")
        scope_frame.pack(fill="x", padx=8, pady=4)

        self._scope_var = tk.StringVar(value=self.settings.pitchers_scope)
        ttk.Combobox(scope_frame, textvariable=self._scope_var,
                     values=PITCHER_SCOPE_OPTIONS, state="readonly", width=20).pack(
            anchor="w", **pad)

        # ---- Pitcher Type ----
        type_frame = ttk.LabelFrame(parent, text="Pitcher Type")
        type_frame.pack(fill="x", padx=8, pady=4)

        self._type_var = tk.StringVar(value=self.settings.pitchers_pitcher_type)
        for val in PITCHER_TYPE_OPTIONS:
            ttk.Radiobutton(type_frame, text=val, variable=self._type_var,
                            value=val, command=self._on_type_changed).pack(
                anchor="w", padx=8, pady=1)

        # ---- Query Options ----
        query_frame = ttk.LabelFrame(parent, text="Query Options")
        query_frame.pack(fill="x", padx=8, pady=4)

        sort_row = ttk.Frame(query_frame)
        sort_row.pack(anchor="w", **pad)
        ttk.Label(sort_row, text="Sort by:").pack(side="left")
        self._sort_var = tk.StringVar(value=self.settings.pitchers_sort_stat)
        ttk.Combobox(sort_row, textvariable=self._sort_var,
                     values=SORT_STAT_LABELS, state="readonly", width=7).pack(
            side="left", padx=4)

        topn_row = ttk.Frame(query_frame)
        topn_row.pack(anchor="w", **pad)
        ttk.Label(topn_row, text="Top N:").pack(side="left")
        self._topn_var = tk.IntVar(value=self.settings.pitchers_top_n)
        ttk.Spinbox(topn_row, from_=1, to=50, textvariable=self._topn_var,
                    width=5).pack(side="left", padx=4)

        # Min IP (shown for All / Starters)
        self._minip_row = ttk.Frame(query_frame)
        self._minip_row.pack(anchor="w", padx=8, pady=(0, 0))
        ttk.Label(self._minip_row, text="Min IP:").pack(side="left")
        self._minip_var = tk.DoubleVar(value=self.settings.pitchers_min_ip)
        ttk.Spinbox(self._minip_row, from_=0.0, to=300.0, increment=5.0,
                    textvariable=self._minip_var, width=6).pack(side="left", padx=4)

        # Min G (shown for Relievers)
        self._ming_row = ttk.Frame(query_frame)
        # packed/unpacked dynamically by _on_type_changed
        ttk.Label(self._ming_row, text="Min G:").pack(side="left")
        self._ming_var = tk.IntVar(value=self.settings.pitchers_min_g)
        ttk.Spinbox(self._ming_row, from_=0, to=162, textvariable=self._ming_var,
                    width=5).pack(side="left", padx=4)

        # Spacer to keep frame height consistent
        self._query_spacer = ttk.Label(query_frame, text="")
        self._query_spacer.pack(pady=(0, 2))

        self._on_type_changed()   # set initial qualifier visibility

        # ---- Columns ----
        col_frame = ttk.LabelFrame(parent, text="Columns")
        col_frame.pack(fill="x", padx=8, pady=4)

        self._col_mode_var = tk.StringVar(value=self.settings.pitchers_column_mode)
        for val, label in [
                ("auto",     "Auto (suggested)"),
                ("reduced",  "Reduced  (ERA W L SO WHIP)"),
                ("standard", "Standard  (ERA W L IP SO BB WHIP)"),
                ("extended", "Extended  (+SV HLD HR)"),
        ]:
            ttk.Radiobutton(col_frame, text=label, variable=self._col_mode_var,
                            value=val, command=self._update_col_suggestion).pack(
                anchor="w", padx=8, pady=1)

        self._col_suggest_lbl = ttk.Label(col_frame, text="", foreground="#2255aa")
        self._col_suggest_lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self._update_col_suggestion()

        # ---- Display Options ----
        opt_frame = ttk.LabelFrame(parent, text="Display Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        self._show_ts_var = tk.BooleanVar(value=self.settings.pitchers_show_timestamp)
        ttk.Checkbutton(opt_frame, text="Show 'data as of' timestamp",
                        variable=self._show_ts_var).pack(
            anchor="w", padx=8, pady=(4, 2))

        self._simple_title_var = tk.BooleanVar(value=self.settings.pitchers_simple_title)
        ttk.Checkbutton(opt_frame, text="Simple title ('Top Pitchers')",
                        variable=self._simple_title_var).pack(
            anchor="w", padx=8, pady=2)

        self._show_badges_var = tk.BooleanVar(value=self.settings.pitchers_show_rank_badges)
        ttk.Checkbutton(opt_frame, text="Show rank badges (gold / silver / copper)",
                        variable=self._show_badges_var).pack(
            anchor="w", padx=8, pady=2)

        self._show_jersey_var = tk.BooleanVar(value=self.settings.pitchers_show_jersey_number)
        ttk.Checkbutton(opt_frame, text="Show jersey number inline",
                        variable=self._show_jersey_var).pack(
            anchor="w", padx=8, pady=2)

        self._show_logos_var = tk.BooleanVar(value=self.settings.pitchers_show_logos)
        ttk.Checkbutton(opt_frame, text="Show team logos",
                        variable=self._show_logos_var).pack(
            anchor="w", padx=8, pady=2)

        self._show_explainers_var = tk.BooleanVar(
            value=self.settings.pitchers_show_col_explainers)
        ttk.Checkbutton(opt_frame, text="Show column explainers",
                        variable=self._show_explainers_var).pack(
            anchor="w", padx=8, pady=(0, 4))

        # ---- Background Color ----
        bg_frame = ttk.LabelFrame(parent, text="Background Color")
        bg_frame.pack(fill="x", padx=8, pady=4)

        self._bg_var = tk.StringVar(value=self.settings.pitchers_bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_var, width=9).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=3, relief="sunken",
                                   background=self.settings.pitchers_bg_color)
        self._bg_swatch.pack(side="left", padx=3)
        ttk.Button(bg_row, text="Pick\u2026", command=self._pick_bg_color).pack(side="left")
        self._bg_var.trace_add("write", self._on_bg_changed)

        # ---- Fetch & Preview ----
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=8)

        fetch_row = ttk.Frame(parent)
        fetch_row.pack(fill="x", padx=8, pady=2)
        self._fetch_btn = ttk.Button(fetch_row, text="Fetch & Preview",
                                     command=self._fetch_and_preview)
        self._fetch_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._refresh_btn = ttk.Button(fetch_row, text="\u21ba Refresh",
                                       command=self._force_refresh, width=9)
        self._refresh_btn.pack(side="left")

        self._full_preview_btn = ttk.Button(parent, text="Full Preview\u2026",
                                            command=self._full_preview,
                                            state="disabled")
        self._full_preview_btn.pack(fill="x", padx=8, pady=2)

        self._status_lbl = ttk.Label(parent, text="", wraplength=270,
                                     foreground="#aa2200")
        self._status_lbl.pack(anchor="w", padx=8, pady=2)

        # ---- Export ----
        export_frame = ttk.LabelFrame(parent, text="Export")
        export_frame.pack(fill="x", padx=8, pady=(4, 8))

        self._export_name_var = tk.StringVar(value=self.settings.pitchers_export_filename)
        ttk.Label(export_frame, text="Filename (no extension):").pack(
            anchor="w", padx=8, pady=(4, 0))
        ttk.Entry(export_frame, textvariable=self._export_name_var, width=24).pack(
            fill="x", padx=8, pady=2)

        self._append_ts_var = tk.BooleanVar(value=self.settings.pitchers_append_timestamp)
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

    def _on_type_changed(self, *_) -> None:
        """Swap Min IP / Min G qualifier row based on selected pitcher type."""
        ptype = self._type_var.get()
        if ptype == "Relievers":
            self._minip_row.pack_forget()
            self._ming_row.pack(anchor="w", padx=8, pady=(0, 0),
                                before=self._query_spacer)
        else:
            self._ming_row.pack_forget()
            self._minip_row.pack(anchor="w", padx=8, pady=(0, 0),
                                 before=self._query_spacer)

    def _update_col_suggestion(self) -> None:
        try:
            w = self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get()
        except tk.TclError:
            return
        suggested = suggest_column_mode(w)
        mode = self._col_mode_var.get()
        if mode == "auto":
            self._col_suggest_lbl.config(text=f"\u2192 Will use {suggested} at this width")
        elif mode == "extended" and w < EXTENDED_MIN_WIDTH_IN:
            self._col_suggest_lbl.config(
                text=f"\u26a0 Extended may be crowded below {EXTENDED_MIN_WIDTH_IN}\"")
        elif mode == "standard" and w < STANDARD_MIN_WIDTH_IN:
            self._col_suggest_lbl.config(
                text=f"\u26a0 Standard may be crowded below {STANDARD_MIN_WIDTH_IN}\"")
        else:
            self._col_suggest_lbl.config(text="")

    def _pick_bg_color(self) -> None:
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
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        if self._card_image is not None:
            self._resize_after_id = self.after(150, self._update_thumbnail)
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
        color = self._bg_var.get().strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", color):
            self._set_status(
                f"Invalid background color \u201c{color}\u201d \u2014 use #RGB or #RRGGBB",
                error=True)
            return
        self._fetching = True
        self._fetch_btn.config(state="disabled")
        self._refresh_btn.config(state="disabled")
        self._set_status("Fetching pitching stats\u2026", error=False)
        self._canvas.delete("all")
        self._canvas.create_text(
            THUMB_W // 2, THUMB_H // 2,
            text="Fetching data\u2026", fill="#555555", font=("Arial", 11))
        threading.Thread(target=self._do_fetch, args=(force,), daemon=True).start()

    def _force_refresh(self) -> None:
        self._fetch_and_preview(force=True)

    def _do_fetch(self, force: bool = False) -> None:
        try:
            block, source = fetch_pitchers_cached(
                ttl_minutes=self.settings.data_cache_ttl_minutes,
                working_dir=self.settings.working_dir,
                force_refresh=force,
            )
            self.after(0, lambda: self._do_render(block, source))
        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._on_fetch_error(m))

    def _do_render(self, block, source: str = "live") -> None:
        try:
            cfg     = self._build_card_config()
            entries = filter_pitchers(block, cfg.scope, cfg.pitcher_type)
            trimmed = sort_and_trim(
                entries, cfg.sort_stat, cfg.top_n,
                cfg.min_ip, cfg.min_g, cfg.pitcher_type,
            )

            if not trimmed:
                qualifier = (
                    f"\u2265{cfg.min_g} G"
                    if cfg.pitcher_type == "Relievers"
                    else f"\u2265{cfg.min_ip} IP"
                )
                self._on_fetch_error(
                    f"No pitchers found for scope '{cfg.scope}' "
                    f"({cfg.pitcher_type}) with {qualifier}.")
                return

            renderer = PitchersCardRenderer(cfg, trimmed, block,
                                            working_dir=self.settings.working_dir)
            self._card_image = renderer.render()
            self._update_thumbnail()

            age_sec = (datetime.datetime.now() - block.as_of).total_seconds()
            if source == "live":
                status = "Live data \u00b7 fetched just now"
            else:
                mins    = int(age_sec // 60)
                secs    = int(age_sec % 60)
                age_str = f"{mins}m {secs}s ago" if mins else f"{secs}s ago"
                label   = "Memory cache" if source == "memory" else "Disk cache"
                status  = (f"{label} \u00b7 fetched {age_str}  "
                           f"(TTL {self.settings.data_cache_ttl_minutes} min)")
            if getattr(renderer, "last_warning", None):
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

    def _build_card_config(self) -> PitchersCardConfig:
        try:
            top_n = int(self._topn_var.get())
        except (tk.TclError, ValueError):
            top_n = 10
        try:
            min_ip = float(self._minip_var.get())
        except (tk.TclError, ValueError):
            min_ip = 30.0
        try:
            min_g = int(self._ming_var.get())
        except (tk.TclError, ValueError):
            min_g = 10
        return PitchersCardConfig(
            width_in=self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get(),
            height_in=self.settings.card_height_in if self._use_global_size_var.get() else self._height_var.get(),
            dpi=self.settings.dpi,
            bg_color=self._bg_var.get(),
            scope=self._scope_var.get(),
            pitcher_type=self._type_var.get(),
            column_mode=self._col_mode_var.get(),
            sort_stat=self._sort_var.get(),
            top_n=top_n,
            min_ip=min_ip,
            min_g=min_g,
            show_timestamp=self._show_ts_var.get(),
            simple_title=self._simple_title_var.get(),
            show_rank_badges=self._show_badges_var.get(),
            show_jersey_number=self._show_jersey_var.get(),
            show_logos=self._show_logos_var.get(),
            show_col_explainers=self._show_explainers_var.get(),
            col_explainer_sep=self.settings.col_explainer_sep,
        )

    def _update_thumbnail(self) -> None:
        if self._card_image is None:
            return
        img   = self._card_image
        cw    = self._canvas.winfo_width()  or THUMB_W
        ch    = self._canvas.winfo_height() or THUMB_H
        ratio = min(cw / img.width, ch / img.height)
        tw    = max(1, round(img.width  * ratio))
        th    = max(1, round(img.height * ratio))
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
        win.title("Pitchers Card \u2014 Full Preview")
        img   = self._card_image
        max_w = 1200
        ratio = min(1.0, max_w / img.width)
        dw    = round(img.width  * ratio)
        dh    = round(img.height * ratio)
        display = img.resize((dw, dh), Image.LANCZOS) if ratio < 1.0 else img
        photo   = ImageTk.PhotoImage(display)
        lbl = tk.Label(win, image=photo)
        lbl.image = photo
        lbl.pack()
        win.resizable(False, False)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _export(self, fmt: str) -> None:
        if self._card_image is None:
            messagebox.showwarning("Nothing to export", "Generate a preview first.")
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
        output_dir = os.path.join(working_dir, "output", "pitchers")
        os.makedirs(output_dir, exist_ok=True)
        ext      = ".png" if fmt == "PNG" else ".jpg"
        raw_name = self._export_name_var.get().strip() or "pitchers_card"
        base     = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(". ")
        if not base:
            base = "pitchers_card"
        if self._append_ts_var.get():
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{base}_{ts}"
        filename = base + ext
        out_path = os.path.join(output_dir, filename)
        try:
            cfg   = self._build_card_config()
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
        self.settings.pitchers_scope          = self._scope_var.get()
        self.settings.pitchers_pitcher_type   = self._type_var.get()
        self.settings.pitchers_column_mode    = self._col_mode_var.get()
        self.settings.pitchers_sort_stat      = self._sort_var.get()
        try:
            self.settings.pitchers_top_n      = int(self._topn_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.pitchers_min_ip     = float(self._minip_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.pitchers_min_g      = int(self._ming_var.get())
        except (tk.TclError, ValueError):
            pass
        self.settings.pitchers_show_timestamp      = self._show_ts_var.get()
        self.settings.pitchers_simple_title        = self._simple_title_var.get()
        self.settings.pitchers_show_rank_badges    = self._show_badges_var.get()
        self.settings.pitchers_show_jersey_number  = self._show_jersey_var.get()
        self.settings.pitchers_show_logos          = self._show_logos_var.get()
        self.settings.pitchers_width_in            = self._width_var.get()
        self.settings.pitchers_height_in           = self._height_var.get()
        self.settings.pitchers_use_global_size     = self._use_global_size_var.get()
        self._refresh_global_size_label()
        self.settings.pitchers_bg_color            = self._bg_var.get()
        self.settings.pitchers_export_filename     = self._export_name_var.get().strip()
        self.settings.pitchers_append_timestamp    = self._append_ts_var.get()
        self.settings.pitchers_show_col_explainers = self._show_explainers_var.get()
