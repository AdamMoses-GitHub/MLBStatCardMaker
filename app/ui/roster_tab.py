from __future__ import annotations

import datetime
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser

from PIL import Image, ImageTk

from app.settings import Settings
from app.cards.roster_card import RosterCardConfig, RosterCardRenderer
from app.data.roster_api import (
    fetch_roster,
    TEAM_NAME_OPTIONS,
    TEAM_NAMES,
    ROSTER_TYPE_OPTIONS,
)

THUMB_W = 480
THUMB_H = 320


class RosterTab(ttk.Frame):
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

        self._width_var  = tk.DoubleVar(value=self.settings.roster_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.roster_height_in)

        row = ttk.Frame(size_frame)
        row.pack(anchor="w", **pad)
        ttk.Label(row, text="W (in):").pack(side="left")
        w_spin = ttk.Spinbox(row, from_=2.0, to=24.0, increment=0.5,
                             textvariable=self._width_var, width=5)
        w_spin.pack(side="left", padx=3)
        w_spin.bind("<FocusOut>",    self._on_size_changed)
        w_spin.bind("<<Increment>>", self._on_size_changed)
        w_spin.bind("<<Decrement>>", self._on_size_changed)

        ttk.Label(row, text="H (in):").pack(side="left", padx=(8, 0))
        h_spin = ttk.Spinbox(row, from_=2.0, to=24.0, increment=0.5,
                             textvariable=self._height_var, width=5)
        h_spin.pack(side="left", padx=3)
        h_spin.bind("<FocusOut>",    self._on_size_changed)
        h_spin.bind("<<Increment>>", self._on_size_changed)
        h_spin.bind("<<Decrement>>", self._on_size_changed)

        self._orient_lbl = ttk.Label(size_frame, text="", foreground="#555555")
        self._orient_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        self._update_orientation_label()

        # ---- Team ----
        team_frame = ttk.LabelFrame(parent, text="Team")
        team_frame.pack(fill="x", padx=8, pady=4)

        self._team_var = tk.StringVar(value=self.settings.roster_team)
        ttk.Combobox(team_frame, textvariable=self._team_var,
                     values=TEAM_NAME_OPTIONS, state="readonly", width=26).pack(
            anchor="w", **pad)

        # ---- Roster Type ----
        type_frame = ttk.LabelFrame(parent, text="Roster Type")
        type_frame.pack(fill="x", padx=8, pady=4)

        self._roster_type_var = tk.StringVar(value=self.settings.roster_type)
        for val in ROSTER_TYPE_OPTIONS:
            ttk.Radiobutton(type_frame, text=val, variable=self._roster_type_var,
                            value=val).pack(anchor="w", padx=8, pady=1)

        # ---- Display Options ----
        opt_frame = ttk.LabelFrame(parent, text="Display Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        self._group_var = tk.BooleanVar(value=self.settings.roster_group_by_position)
        ttk.Checkbutton(opt_frame, text="Group by position",
                        variable=self._group_var).pack(
            anchor="w", padx=8, pady=(4, 2))

        self._jersey_var = tk.BooleanVar(value=self.settings.roster_show_jersey_number)
        ttk.Checkbutton(opt_frame, text="Show jersey #",
                        variable=self._jersey_var).pack(
            anchor="w", padx=8, pady=1)

        self._bt_var = tk.BooleanVar(value=self.settings.roster_show_bats_throws)
        ttk.Checkbutton(opt_frame, text="Show Bats/Throws",
                        variable=self._bt_var).pack(
            anchor="w", padx=8, pady=1)

        self._age_var = tk.BooleanVar(value=self.settings.roster_show_age)
        ttk.Checkbutton(opt_frame, text="Show Age",
                        variable=self._age_var).pack(
            anchor="w", padx=8, pady=1)

        self._logos_var = tk.BooleanVar(value=self.settings.roster_show_logos)
        ttk.Checkbutton(opt_frame, text="Show team logo in title",
                        variable=self._logos_var).pack(
            anchor="w", padx=8, pady=1)

        self._ts_var = tk.BooleanVar(value=self.settings.roster_show_timestamp)
        ttk.Checkbutton(opt_frame, text="Show 'data as of' timestamp",
                        variable=self._ts_var).pack(
            anchor="w", padx=8, pady=(1, 4))

        # ---- Background Color ----
        bg_frame = ttk.LabelFrame(parent, text="Background Color")
        bg_frame.pack(fill="x", padx=8, pady=4)

        self._bg_var = tk.StringVar(value=self.settings.roster_bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_var, width=9).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=3, relief="sunken",
                                   background=self.settings.roster_bg_color)
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

        self._export_name_var = tk.StringVar(value=self.settings.roster_export_filename)
        ttk.Label(export_frame, text="Filename (no extension):").pack(
            anchor="w", padx=8, pady=(4, 0))
        ttk.Entry(export_frame, textvariable=self._export_name_var, width=24).pack(
            fill="x", padx=8, pady=2)

        self._append_ts_var = tk.BooleanVar(value=self.settings.roster_append_timestamp)
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
            w = self._width_var.get()
            h = self._height_var.get()
        except tk.TclError:
            return
        label = "Landscape" if w >= h else "Portrait"
        self._orient_lbl.config(text=f"Orientation: {label}")

    def _on_size_changed(self, *_) -> None:
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
        team_name = self._team_var.get()
        self._set_status(f"Fetching {team_name} roster\u2026", error=False)
        self._canvas.delete("all")
        self._canvas.create_text(
            THUMB_W // 2, THUMB_H // 2,
            text="Fetching data\u2026", fill="#555555", font=("Arial", 11))
        threading.Thread(target=self._do_fetch, args=(force,), daemon=True).start()

    def _force_refresh(self) -> None:
        self._fetch_and_preview(force=True)

    def _do_fetch(self, force: bool) -> None:
        team_name = self._team_var.get()
        abbrev    = TEAM_NAMES.get(team_name, team_name)
        try:
            block = fetch_roster(
                team_abbrev=abbrev,
                roster_type=self._roster_type_var.get(),
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
            renderer = RosterCardRenderer(cfg, block,
                                          working_dir=self.settings.working_dir)
            self._card_image = renderer.render()
            self._update_thumbnail()
            n = len(block.entries)
            self._set_status(
                f"Done \u2014 {n} player{'s' if n != 1 else ''} ({block.roster_type})",
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

    def _build_card_config(self) -> RosterCardConfig:
        team_name = self._team_var.get()
        abbrev    = TEAM_NAMES.get(team_name, team_name)
        return RosterCardConfig(
            width_in=self._width_var.get(),
            height_in=self._height_var.get(),
            dpi=self.settings.dpi,
            bg_color=self._bg_var.get(),
            team_abbrev=abbrev,
            roster_type=self._roster_type_var.get(),
            group_by_position=self._group_var.get(),
            show_jersey_number=self._jersey_var.get(),
            show_bats_throws=self._bt_var.get(),
            show_age=self._age_var.get(),
            show_logos=self._logos_var.get(),
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
        win.title("Team Roster \u2014 Full Preview")
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
        output_dir = os.path.join(working_dir, "output", "roster")
        os.makedirs(output_dir, exist_ok=True)
        ext      = ".png" if fmt == "PNG" else ".jpg"
        raw_name = self._export_name_var.get().strip() or "roster_card"
        base     = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(". ")
        if not base:
            base = "roster_card"
        if self._append_ts_var.get():
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{base}_{ts}"
        filename = base + ext
        out_path = os.path.join(output_dir, filename)
        try:
            cfg   = self._build_card_config()
            saved = cfg.export(self._card_image, out_path, fmt)
            messagebox.showinfo("Exported", f"Saved to:\n{saved}")
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Persist settings
    # ------------------------------------------------------------------
    def apply(self) -> None:
        self.settings.roster_team              = self._team_var.get()
        self.settings.roster_type              = self._roster_type_var.get()
        self.settings.roster_group_by_position = self._group_var.get()
        self.settings.roster_show_jersey_number = self._jersey_var.get()
        self.settings.roster_show_bats_throws  = self._bt_var.get()
        self.settings.roster_show_age          = self._age_var.get()
        self.settings.roster_show_logos        = self._logos_var.get()
        self.settings.roster_show_timestamp    = self._ts_var.get()
        self.settings.roster_width_in          = self._width_var.get()
        self.settings.roster_height_in         = self._height_var.get()
        self.settings.roster_bg_color          = self._bg_var.get()
        self.settings.roster_export_filename   = self._export_name_var.get().strip()
        self.settings.roster_append_timestamp  = self._append_ts_var.get()
