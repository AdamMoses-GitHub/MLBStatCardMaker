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
from app.cards.triple_crown_card import TripleCrownCardConfig, TripleCrownCardRenderer
from app.data.triple_crown_api import fetch_triple_crown
from app.data.batters_api import BATTER_SCOPE_OPTIONS, SORT_STAT_LABELS as BATTER_STAT_LABELS
from app.data.pitchers_api import PITCHER_TYPE_OPTIONS, SORT_STAT_LABELS as PITCHER_STAT_LABELS

THUMB_W = 480
THUMB_H = 320
_CURRENT_YEAR = datetime.date.today().year


class TripleCrownTab(ttk.Frame):
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

        self._width_var  = tk.DoubleVar(value=self.settings.triple_crown_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.triple_crown_height_in)

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
            value=self.settings.triple_crown_use_global_size)
        self._use_global_chk = ttk.Checkbutton(
            size_frame, variable=self._use_global_size_var,
            command=self._on_use_global_size_changed)
        self._use_global_chk.pack(anchor="w", padx=8, pady=(0, 2))

        self._orient_lbl = ttk.Label(size_frame, text="", foreground="#555555")
        self._orient_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        if self.settings.triple_crown_use_global_size:
            self._w_spin.config(state="disabled")
            self._h_spin.config(state="disabled")
        self._update_orientation_label()
        self._refresh_global_size_label()

        # ---- Stat Type ----
        type_frame = ttk.LabelFrame(parent, text="Stat Type")
        type_frame.pack(fill="x", padx=8, pady=4)

        self._stat_type_var = tk.StringVar(value=self.settings.triple_crown_stat_type)
        for val in ("Batting", "Pitching"):
            ttk.Radiobutton(type_frame, text=val, variable=self._stat_type_var,
                            value=val, command=self._on_stat_type_changed).pack(
                anchor="w", padx=8, pady=1)

        # ---- Scope ----
        scope_frame = ttk.LabelFrame(parent, text="Scope")
        scope_frame.pack(fill="x", padx=8, pady=4)

        self._scope_var = tk.StringVar(value=self.settings.triple_crown_scope)
        ttk.Combobox(scope_frame, textvariable=self._scope_var,
                     values=BATTER_SCOPE_OPTIONS, state="readonly", width=20).pack(
            anchor="w", **pad)

        # ---- Query Options ----
        query_frame = ttk.LabelFrame(parent, text="Query Options")
        query_frame.pack(fill="x", padx=8, pady=4)

        season_row = ttk.Frame(query_frame)
        season_row.pack(anchor="w", **pad)
        ttk.Label(season_row, text="Season:").pack(side="left")
        _season = self.settings.triple_crown_season or _CURRENT_YEAR
        self._season_var = tk.IntVar(value=_season)
        ttk.Spinbox(season_row, from_=1900, to=_CURRENT_YEAR + 1,
                    textvariable=self._season_var, width=6).pack(side="left", padx=4)

        topn_row = ttk.Frame(query_frame)
        topn_row.pack(anchor="w", **pad)
        ttk.Label(topn_row, text="Top N:").pack(side="left")
        self._topn_var = tk.IntVar(value=self.settings.triple_crown_top_n)
        ttk.Spinbox(topn_row, from_=3, to=25, textvariable=self._topn_var,
                    width=5).pack(side="left", padx=4)

        # Batting-specific controls
        self._batting_frame = ttk.Frame(query_frame)
        minpa_row = ttk.Frame(self._batting_frame)
        minpa_row.pack(anchor="w", padx=8, pady=(0, 4))
        ttk.Label(minpa_row, text="Min PA:").pack(side="left")
        self._minpa_var = tk.IntVar(value=self.settings.triple_crown_min_pa)
        ttk.Spinbox(minpa_row, from_=0, to=700, textvariable=self._minpa_var,
                    width=5).pack(side="left", padx=4)

        # Batting stat selectors (3 panels)
        _b_saved = self.settings.triple_crown_batting_stats or []
        _b_fallbacks = ["AVG", "HR", "RBI"]
        _b_defaults = [
            lbl if lbl in BATTER_STAT_LABELS else _b_fallbacks[i]
            for i, lbl in enumerate((_b_saved + _b_fallbacks)[:3])
        ]
        ttk.Label(self._batting_frame, text="Panel stats:").pack(
            anchor="w", padx=8, pady=(2, 0))
        self._batting_stat_vars: list[tk.StringVar] = []
        for i, default in enumerate(_b_defaults):
            v = tk.StringVar(value=default)
            self._batting_stat_vars.append(v)
            row = ttk.Frame(self._batting_frame)
            row.pack(anchor="w", padx=8, pady=1)
            ttk.Label(row, text=f"  Panel {i+1}:", width=9).pack(side="left")
            ttk.Combobox(row, textvariable=v, values=BATTER_STAT_LABELS,
                         state="readonly", width=7).pack(side="left")

        # Pitching-specific controls
        self._pitching_frame = ttk.Frame(query_frame)

        pt_row = ttk.Frame(self._pitching_frame)
        pt_row.pack(anchor="w", padx=8, pady=(2, 1))
        ttk.Label(pt_row, text="Type:").pack(side="left")
        self._pitcher_type_var = tk.StringVar(
            value=self.settings.triple_crown_pitcher_type)
        for val in PITCHER_TYPE_OPTIONS:
            ttk.Radiobutton(pt_row, text=val, variable=self._pitcher_type_var,
                            value=val).pack(side="left", padx=2)

        minip_row = ttk.Frame(self._pitching_frame)
        minip_row.pack(anchor="w", padx=8, pady=1)
        ttk.Label(minip_row, text="Min IP:").pack(side="left")
        self._minip_var = tk.DoubleVar(value=self.settings.triple_crown_min_ip)
        ttk.Spinbox(minip_row, from_=0, to=300, increment=5.0,
                    textvariable=self._minip_var, width=6).pack(side="left", padx=4)

        ming_row = ttk.Frame(self._pitching_frame)
        ming_row.pack(anchor="w", padx=8, pady=(1, 4))
        ttk.Label(ming_row, text="Min G:").pack(side="left")
        self._ming_var = tk.IntVar(value=self.settings.triple_crown_min_g)
        ttk.Spinbox(ming_row, from_=0, to=162, textvariable=self._ming_var,
                    width=5).pack(side="left", padx=4)

        # Pitching stat selectors (3 panels)
        _p_saved = self.settings.triple_crown_pitching_stats or []
        _p_fallbacks = ["W", "SO", "ERA"]
        _p_defaults = [
            lbl if lbl in PITCHER_STAT_LABELS else _p_fallbacks[i]
            for i, lbl in enumerate((_p_saved + _p_fallbacks)[:3])
        ]
        ttk.Label(self._pitching_frame, text="Panel stats:").pack(
            anchor="w", padx=8, pady=(2, 0))
        self._pitching_stat_vars: list[tk.StringVar] = []
        for i, default in enumerate(_p_defaults):
            v = tk.StringVar(value=default)
            self._pitching_stat_vars.append(v)
            row = ttk.Frame(self._pitching_frame)
            row.pack(anchor="w", padx=8, pady=1)
            ttk.Label(row, text=f"  Panel {i+1}:", width=9).pack(side="left")
            ttk.Combobox(row, textvariable=v, values=PITCHER_STAT_LABELS,
                         state="readonly", width=7).pack(side="left")

        # ---- Display Options ----
        opt_frame = ttk.LabelFrame(parent, text="Display Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        self._show_logos_var = tk.BooleanVar(value=self.settings.triple_crown_show_logos)
        ttk.Checkbutton(opt_frame, text="Show team logos",
                        variable=self._show_logos_var).pack(
            anchor="w", padx=8, pady=(4, 2))

        self._show_badges_var = tk.BooleanVar(
            value=self.settings.triple_crown_show_rank_badges)
        ttk.Checkbutton(opt_frame, text="Show rank badges (gold / silver / copper)",
                        variable=self._show_badges_var).pack(
            anchor="w", padx=8, pady=(1, 2))

        self._show_ts_var = tk.BooleanVar(
            value=self.settings.triple_crown_show_timestamp)
        ttk.Checkbutton(opt_frame, text="Show 'data as of' timestamp",
                        variable=self._show_ts_var).pack(
            anchor="w", padx=8, pady=(0, 4))

        # ---- Background Color ----
        bg_frame = ttk.LabelFrame(parent, text="Background Color")
        bg_frame.pack(fill="x", padx=8, pady=4)

        self._bg_var = tk.StringVar(value=self.settings.triple_crown_bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_var, width=9).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=3, relief="sunken",
                                   background=self.settings.triple_crown_bg_color)
        self._bg_swatch.pack(side="left", padx=3)
        ttk.Button(bg_row, text="Pick\u2026", command=self._pick_bg_color).pack(
            side="left")
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

        self._export_name_var = tk.StringVar(
            value=self.settings.triple_crown_export_filename)
        ttk.Label(export_frame, text="Filename (no extension):").pack(
            anchor="w", padx=8, pady=(4, 0))
        ttk.Entry(export_frame, textvariable=self._export_name_var, width=24).pack(
            fill="x", padx=8, pady=2)

        self._append_ts_var = tk.BooleanVar(
            value=self.settings.triple_crown_append_timestamp)
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

        # Show/hide batting vs pitching controls
        self._on_stat_type_changed()

    def _build_preview(self, parent: ttk.LabelFrame) -> None:
        self._canvas = tk.Canvas(parent, bg="#CCCCCC", width=THUMB_W, height=THUMB_H)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self._resize_after_id = None
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._draw_placeholder()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _on_stat_type_changed(self) -> None:
        if self._stat_type_var.get() == "Batting":
            self._batting_frame.pack(fill="x")
            self._pitching_frame.pack_forget()
        else:
            self._batting_frame.pack_forget()
            self._pitching_frame.pack(fill="x")

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
        stat_type = self._stat_type_var.get()
        self._set_status(f"Fetching {stat_type.lower()} stats\u2026", error=False)
        self._canvas.delete("all")
        self._canvas.create_text(
            THUMB_W // 2, THUMB_H // 2,
            text="Fetching data\u2026", fill="#555555", font=("Arial", 11))
        threading.Thread(target=self._do_fetch, args=(force,), daemon=True).start()

    def _force_refresh(self) -> None:
        self._fetch_and_preview(force=True)

    def _do_fetch(self, force: bool) -> None:
        try:
            block = fetch_triple_crown(
                scope=self._scope_var.get(),
                stat_type=self._stat_type_var.get(),
                top_n=self._topn_var.get(),
                min_pa=self._minpa_var.get(),
                min_ip=self._minip_var.get(),
                min_g=self._ming_var.get(),
                pitcher_type=self._pitcher_type_var.get(),
                season=self._season_var.get(),
                ttl_minutes=self.settings.data_cache_ttl_minutes,
                working_dir=self.settings.working_dir,
                force_refresh=force,
                batting_stats=[v.get() for v in self._batting_stat_vars],
                pitching_stats=[v.get() for v in self._pitching_stat_vars],
            )
            self.after(0, lambda: self._do_render(block))
        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._on_fetch_error(m))

    def _do_render(self, block) -> None:
        try:
            cfg = self._build_card_config()
            renderer = TripleCrownCardRenderer(cfg, block,
                                               working_dir=self.settings.working_dir)
            self._card_image = renderer.render()
            self._update_thumbnail()
            labels = " / ".join(c.stat_label for c in block.columns)
            n = len(block.columns[0].entries) if block.columns else 0
            self._set_status(
                f"Done \u2014 {labels}  \u00b7  top {n} each",
                error=False)
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

    def _build_card_config(self) -> TripleCrownCardConfig:
        return TripleCrownCardConfig(
            width_in=self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get(),
            height_in=self.settings.card_height_in if self._use_global_size_var.get() else self._height_var.get(),
            dpi=self.settings.dpi,
            bg_color=self._bg_var.get(),
            scope=self._scope_var.get(),
            stat_type=self._stat_type_var.get(),
            top_n=self._topn_var.get(),
            show_logos=self._show_logos_var.get(),
            show_rank_badges=self._show_badges_var.get(),
            show_timestamp=self._show_ts_var.get(),
        )

    def _update_thumbnail(self) -> None:
        if self._card_image is None:
            return
        img = self._card_image
        cw  = self._canvas.winfo_width()  or THUMB_W
        ch  = self._canvas.winfo_height() or THUMB_H
        ratio = min(cw / img.width, ch / img.height)
        tw = max(1, round(img.width  * ratio))
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
        win.title("Triple Crown Card \u2014 Full Preview")
        img = self._card_image
        max_w = 1200
        ratio = min(1.0, max_w / img.width)
        dw = round(img.width  * ratio)
        dh = round(img.height * ratio)
        display = img.resize((dw, dh), Image.LANCZOS) if ratio < 1.0 else img
        photo = ImageTk.PhotoImage(display)
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
        output_dir = os.path.join(working_dir, "output", "triple_crown")
        os.makedirs(output_dir, exist_ok=True)
        ext      = ".png" if fmt == "PNG" else ".jpg"
        raw_name = self._export_name_var.get().strip() or "triple_crown_card"
        base     = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(". ")
        if not base:
            base = "triple_crown_card"
        if self._append_ts_var.get():
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{base}_{ts}"
        out_path = os.path.join(output_dir, base + ext)
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
        self.settings.triple_crown_scope        = self._scope_var.get()
        self.settings.triple_crown_stat_type    = self._stat_type_var.get()
        self.settings.triple_crown_pitcher_type = self._pitcher_type_var.get()
        self.settings.triple_crown_show_logos   = self._show_logos_var.get()
        self.settings.triple_crown_show_rank_badges = self._show_badges_var.get()
        self.settings.triple_crown_show_timestamp = self._show_ts_var.get()
        self.settings.triple_crown_batting_stats  = [v.get() for v in self._batting_stat_vars]
        self.settings.triple_crown_pitching_stats = [v.get() for v in self._pitching_stat_vars]
        self.settings.triple_crown_width_in     = self._width_var.get()
        self.settings.triple_crown_height_in    = self._height_var.get()
        self.settings.triple_crown_use_global_size = self._use_global_size_var.get()
        self._refresh_global_size_label()
        self.settings.triple_crown_bg_color     = self._bg_var.get()
        self.settings.triple_crown_export_filename = self._export_name_var.get().strip()
        self.settings.triple_crown_append_timestamp = self._append_ts_var.get()
        try:
            self.settings.triple_crown_season = int(self._season_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.triple_crown_top_n = int(self._topn_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.triple_crown_min_pa = int(self._minpa_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.triple_crown_min_ip = float(self._minip_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.triple_crown_min_g = int(self._ming_var.get())
        except (tk.TclError, ValueError):
            pass
