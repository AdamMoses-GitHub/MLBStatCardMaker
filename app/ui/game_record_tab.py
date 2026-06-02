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
from app.cards.game_record_card import GameRecordCardConfig, GameRecordCardRenderer
from app.data.game_record_api import fetch_game_record
from app.data.roster_api import TEAM_NAME_OPTIONS, TEAM_NAMES

THUMB_W = 480
THUMB_H = 320


class GameRecordTab(ttk.Frame):
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

        self._width_var  = tk.DoubleVar(value=self.settings.game_record_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.game_record_height_in)

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
            value=self.settings.game_record_use_global_size)
        self._use_global_chk = ttk.Checkbutton(
            size_frame, variable=self._use_global_size_var,
            command=self._on_use_global_size_changed)
        self._use_global_chk.pack(anchor="w", padx=8, pady=(0, 2))

        self._orient_lbl = ttk.Label(size_frame, text="", foreground="#555555")
        self._orient_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        if self.settings.game_record_use_global_size:
            self._w_spin.config(state="disabled")
            self._h_spin.config(state="disabled")
        self._update_orientation_label()
        self._refresh_global_size_label()

        # ---- Team ----
        team_frame = ttk.LabelFrame(parent, text="Team")
        team_frame.pack(fill="x", padx=8, pady=4)

        self._team_var = tk.StringVar(value=self.settings.game_record_team)
        ttk.Combobox(team_frame, textvariable=self._team_var,
                     values=TEAM_NAME_OPTIONS, state="readonly", width=26).pack(
            anchor="w", **pad)

        # ---- Mode ----
        mode_frame = ttk.LabelFrame(parent, text="Display Mode")
        mode_frame.pack(fill="x", padx=8, pady=4)

        self._mode_var = tk.StringVar(value=self.settings.game_record_mode)
        ttk.Radiobutton(mode_frame, text="Games", variable=self._mode_var,
                        value="games", command=self._on_mode_changed).pack(
            anchor="w", padx=8, pady=(4, 1))
        ttk.Radiobutton(mode_frame, text="Series", variable=self._mode_var,
                        value="series", command=self._on_mode_changed).pack(
            anchor="w", padx=8, pady=(1, 2))

        # Series detail option — shown/hidden based on mode
        self._series_detail_frame = ttk.Frame(mode_frame)
        self._series_detail_var = tk.StringVar(
            value=self.settings.game_record_series_detail)
        self._series_scores_chk = ttk.Checkbutton(
            self._series_detail_frame,
            text="Show individual game scores",
            variable=self._series_detail_var,
            onvalue="scores", offvalue="result_only")
        self._series_scores_chk.pack(anchor="w", padx=20, pady=(0, 4))

        # Show or hide the series detail row based on initial mode
        if self.settings.game_record_mode == "series":
            self._series_detail_frame.pack(fill="x")

        # ---- Count (N) ----
        n_frame = ttk.LabelFrame(parent, text="Count (N)")
        n_frame.pack(fill="x", padx=8, pady=4)

        self._n_var = tk.IntVar(value=self.settings.game_record_n)
        n_row = ttk.Frame(n_frame)
        n_row.pack(anchor="w", **pad)
        ttk.Label(n_row, text="Show last N:").pack(side="left")
        n_spin = ttk.Spinbox(n_row, from_=1, to=30, increment=1,
                             textvariable=self._n_var, width=4)
        n_spin.pack(side="left", padx=4)
        n_spin.bind("<FocusOut>",    self._on_n_changed)
        n_spin.bind("<<Increment>>", self._on_n_changed)
        n_spin.bind("<<Decrement>>", self._on_n_changed)

        self._n_warn_lbl = ttk.Label(n_frame, text="", wraplength=250,
                                     foreground="#cc6600")
        self._n_warn_lbl.pack(anchor="w", padx=8, pady=(0, 4))

        # ---- Sort Order ----
        sort_frame = ttk.LabelFrame(parent, text="Date Sort")
        sort_frame.pack(fill="x", padx=8, pady=4)

        self._sort_var = tk.StringVar(value=self.settings.game_record_date_sort)
        sort_row = ttk.Frame(sort_frame)
        sort_row.pack(anchor="w", padx=8, pady=4)
        ttk.Radiobutton(sort_row, text="Newest first", variable=self._sort_var,
                        value="desc").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(sort_row, text="Oldest first", variable=self._sort_var,
                        value="asc").pack(side="left")

        # ---- Display Options ----
        opt_frame = ttk.LabelFrame(parent, text="Display Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        self._logos_var = tk.BooleanVar(value=self.settings.game_record_show_logos)
        ttk.Checkbutton(opt_frame, text="Show opponent logos",
                        variable=self._logos_var).pack(
            anchor="w", padx=8, pady=(4, 1))

        self._summary_var = tk.BooleanVar(value=self.settings.game_record_show_summary)
        ttk.Checkbutton(opt_frame, text="Show summary header",
                        variable=self._summary_var).pack(
            anchor="w", padx=8, pady=1)

        self._ts_var = tk.BooleanVar(value=self.settings.game_record_show_timestamp)
        ttk.Checkbutton(opt_frame, text="Show 'data as of' timestamp",
                        variable=self._ts_var).pack(
            anchor="w", padx=8, pady=(1, 4))

        # ---- Background Color ----
        bg_frame = ttk.LabelFrame(parent, text="Background Color")
        bg_frame.pack(fill="x", padx=8, pady=4)

        self._bg_var = tk.StringVar(value=self.settings.game_record_bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_var, width=9).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=3, relief="sunken",
                                   background=self.settings.game_record_bg_color)
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

        self._export_name_var = tk.StringVar(
            value=self.settings.game_record_export_filename)
        ttk.Label(export_frame, text="Filename (no extension):").pack(
            anchor="w", padx=8, pady=(4, 0))
        ttk.Entry(export_frame, textvariable=self._export_name_var, width=24).pack(
            fill="x", padx=8, pady=2)

        self._append_ts_var = tk.BooleanVar(
            value=self.settings.game_record_append_timestamp)
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
        self._update_row_warning()

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
        self._update_row_warning()

    def _on_mode_changed(self) -> None:
        if self._mode_var.get() == "series":
            self._series_detail_frame.pack(fill="x")
        else:
            self._series_detail_frame.pack_forget()
        self._update_row_warning()

    def _on_n_changed(self, *_) -> None:
        self._update_row_warning()

    def _update_row_warning(self) -> None:
        """Estimate row fit and show an orange hint if N is likely too large."""
        try:
            if self._use_global_size_var.get():
                h_in = self.settings.card_height_in
                w_in = self.settings.card_width_in
            else:
                h_in = self._height_var.get()
                w_in = self._width_var.get()
            n = self._n_var.get()
        except (tk.TclError, ValueError):
            return

        dpi = self.settings.dpi
        H = round(h_in * dpi)
        W = round(w_in * dpi)
        PAD = max(8, round(W * 0.018))
        title_h   = max(36, round(H * 0.10))
        summary_h = max(20, round(H * 0.055))
        hdr_h     = max(16, round(H * 0.055))
        body_h    = H - title_h - summary_h - hdr_h - PAD
        min_row_h = max(12, round(9 * dpi / 72))

        # series+scores: each series = 1 band + ~3 game rows on average
        mode = self._mode_var.get()
        detail = self._series_detail_var.get()
        if mode == "series" and detail == "scores":
            avg_rows_per_series = 1 + 3
            total_rows = n * avg_rows_per_series
        else:
            total_rows = n

        rows_fit = max(1, body_h // min_row_h)
        if total_rows > rows_fit:
            self._n_warn_lbl.config(
                text=f"\u26a0 ~{total_rows} rows needed; ~{rows_fit} fit at current size")
        elif w_in < 4.5:
            self._n_warn_lbl.config(text="\u26a0 Width < 4.5\" — columns may be cramped")
        else:
            self._n_warn_lbl.config(text="")

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
        team_name = self._team_var.get()
        mode = self._mode_var.get()
        self._set_status(f"Fetching {team_name} game record\u2026", error=False)
        self._canvas.delete("all")
        self._canvas.create_text(
            THUMB_W // 2, THUMB_H // 2,
            text="Fetching data\u2026", fill="#555555", font=("Arial", 11))
        threading.Thread(target=self._do_fetch, args=(force,), daemon=True).start()

    def _force_refresh(self) -> None:
        self._fetch_and_preview(force=True)

    def _do_fetch(self, force: bool) -> None:
        team_name = self._team_var.get()
        mode      = self._mode_var.get()
        try:
            n = max(1, min(30, self._n_var.get()))
        except (tk.TclError, ValueError):
            n = 10
        try:
            block = fetch_game_record(
                team_name=team_name,
                mode=mode,
                n=n,
                date_sort=self._sort_var.get(),
                ttl_minutes=self.settings.data_cache_ttl_minutes,
                working_dir=self.settings.working_dir,
                force_refresh=force,
            )
            self.after(0, lambda: self._do_render(block))
        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._on_fetch_error(m))

    def _do_render(self, block) -> None:
        try:
            cfg = self._build_card_config()
            renderer = GameRecordCardRenderer(cfg, block,
                                              working_dir=self.settings.working_dir)
            self._card_image = renderer.render()
            self._update_thumbnail()
            n = len(block.entries)
            label = "series" if block.mode == "series" else "game"
            status = f"Done \u2014 {n} {label}{'s' if n != 1 else ''} shown"
            if renderer.last_warning:
                status += f" \u2014 {renderer.last_warning}"
            self._set_status(status, error=bool(renderer.last_warning))
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

    def _build_card_config(self) -> GameRecordCardConfig:
        team_name  = self._team_var.get()
        team_abbrev = TEAM_NAMES.get(team_name, team_name[:3].upper())
        return GameRecordCardConfig(
            width_in=self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get(),
            height_in=self.settings.card_height_in if self._use_global_size_var.get() else self._height_var.get(),
            dpi=self.settings.dpi,
            bg_color=self._bg_var.get(),
            team_abbrev=team_abbrev,
            team_name=team_name,
            mode=self._mode_var.get(),
            series_detail=self._series_detail_var.get(),
            show_logos=self._logos_var.get(),
            show_summary=self._summary_var.get(),
            show_timestamp=self._ts_var.get(),
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
        win.title("Game Record \u2014 Full Preview")
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
        output_dir = os.path.join(working_dir, "output", "game_record")
        os.makedirs(output_dir, exist_ok=True)
        ext      = ".png" if fmt == "PNG" else ".jpg"
        raw_name = self._export_name_var.get().strip() or "game_record_card"
        base     = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(". ")
        if not base:
            base = "game_record_card"
        if self._append_ts_var.get():
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
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
        self.settings.game_record_team             = self._team_var.get()
        self.settings.game_record_mode             = self._mode_var.get()
        self.settings.game_record_series_detail    = self._series_detail_var.get()
        try:
            self.settings.game_record_n = max(1, min(30, self._n_var.get()))
        except (tk.TclError, ValueError):
            pass
        self.settings.game_record_show_logos       = self._logos_var.get()
        self.settings.game_record_show_summary     = self._summary_var.get()
        self.settings.game_record_show_timestamp   = self._ts_var.get()
        self.settings.game_record_width_in         = self._width_var.get()
        self.settings.game_record_height_in        = self._height_var.get()
        self.settings.game_record_use_global_size  = self._use_global_size_var.get()
        self._refresh_global_size_label()
        self.settings.game_record_bg_color         = self._bg_var.get()
        self.settings.game_record_export_filename  = self._export_name_var.get().strip()
        self.settings.game_record_append_timestamp = self._append_ts_var.get()
        self.settings.game_record_date_sort        = self._sort_var.get()
