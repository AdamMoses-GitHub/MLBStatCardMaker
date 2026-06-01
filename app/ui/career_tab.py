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
from app.cards.career_card import CareerCardConfig, CareerCardRenderer
from app.data.career_api import fetch_career, search_players

THUMB_W = 480
THUMB_H = 320
_CURRENT_YEAR = datetime.date.today().year


class CareerTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, settings: Settings, **kwargs):
        super().__init__(parent, **kwargs)
        self.settings = settings
        self._card_image: Image.Image | None = None
        self._thumb_photo: ImageTk.PhotoImage | None = None
        self._fetching    = False
        self._searching   = False
        # Maps display text → (player_id, full_name, team_abbrev)
        self._player_options: dict[str, tuple[int, str, str]] = {}
        # Selected player info
        self._selected_id: int = self.settings.career_player_id
        self._selected_name: str = self.settings.career_player_name
        self._selected_team: str = self.settings.career_current_team_abbrev
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

        self._width_var  = tk.DoubleVar(value=self.settings.career_width_in)
        self._height_var = tk.DoubleVar(value=self.settings.career_height_in)

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
            value=self.settings.career_use_global_size)
        ttk.Checkbutton(size_frame, text="Use global size",
                        variable=self._use_global_size_var,
                        command=self._on_use_global_size_changed).pack(
            anchor="w", padx=8, pady=(0, 2))

        self._orient_lbl = ttk.Label(size_frame, text="", foreground="#555555")
        self._orient_lbl.pack(anchor="w", padx=8, pady=(0, 4))
        if self.settings.career_use_global_size:
            self._w_spin.config(state="disabled")
            self._h_spin.config(state="disabled")
        self._update_orientation_label()

        # ---- Player Search ----
        search_frame = ttk.LabelFrame(parent, text="Player")
        search_frame.pack(fill="x", padx=8, pady=4)

        # Recent players quick-select
        recent_row = ttk.Frame(search_frame)
        recent_row.pack(fill="x", padx=8, pady=(4, 2))
        ttk.Label(recent_row, text="Recent:").pack(side="left")
        self._recent_var = tk.StringVar()
        self._recent_combo = ttk.Combobox(recent_row, textvariable=self._recent_var,
                                          state="readonly", width=22)
        self._recent_combo.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._recent_combo.bind("<<ComboboxSelected>>", self._on_recent_selected)
        self._refresh_recent_combo()

        search_row = ttk.Frame(search_frame)
        search_row.pack(fill="x", padx=8, pady=(2, 2))
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(search_row, textvariable=self._search_var,
                                       width=18)
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._search_entry.bind("<Return>", lambda _: self._search_player())
        self._search_btn = ttk.Button(search_row, text="Search",
                                      command=self._search_player, width=8)
        self._search_btn.pack(side="left")

        # Pre-populate the search entry if we already have a saved player
        if self._selected_name:
            self._search_var.set(self._selected_name)

        self._player_combo = ttk.Combobox(search_frame, state="readonly", width=26)
        self._player_combo.pack(fill="x", padx=8, pady=(2, 4))
        self._player_combo.bind("<<ComboboxSelected>>", self._on_player_selected)

        # If we have a saved player, populate the combo immediately
        if self._selected_name and self._selected_id:
            display = (f"{self._selected_name} ({self._selected_team})"
                       if self._selected_team else self._selected_name)
            self._player_options[display] = (
                self._selected_id, self._selected_name, self._selected_team)
            self._player_combo["values"] = [display]
            self._player_combo.set(display)

        self._search_status = ttk.Label(search_frame, text="", foreground="#555555",
                                        wraplength=260)
        self._search_status.pack(anchor="w", padx=8, pady=(0, 4))

        # ---- Stat Type ----
        type_frame = ttk.LabelFrame(parent, text="Stat Type")
        type_frame.pack(fill="x", padx=8, pady=4)

        self._stat_type_var = tk.StringVar(value=self.settings.career_stat_type)
        for val in ("Batting", "Pitching"):
            ttk.Radiobutton(type_frame, text=val, variable=self._stat_type_var,
                            value=val).pack(anchor="w", padx=8, pady=1)

        # ---- Year Range ----
        yr_frame = ttk.LabelFrame(parent, text="Year Range (0 = full career)")
        yr_frame.pack(fill="x", padx=8, pady=4)

        yr_row = ttk.Frame(yr_frame)
        yr_row.pack(anchor="w", **pad)
        ttk.Label(yr_row, text="From:").pack(side="left")
        self._yr_start_var = tk.IntVar(value=self.settings.career_year_start)
        ttk.Spinbox(yr_row, from_=0, to=_CURRENT_YEAR, textvariable=self._yr_start_var,
                    width=6).pack(side="left", padx=4)
        ttk.Label(yr_row, text="To:").pack(side="left", padx=(8, 0))
        self._yr_end_var = tk.IntVar(value=self.settings.career_year_end)
        ttk.Spinbox(yr_row, from_=0, to=_CURRENT_YEAR + 1,
                    textvariable=self._yr_end_var, width=6).pack(side="left", padx=4)

        # ---- Display Options ----
        opt_frame = ttk.LabelFrame(parent, text="Display Options")
        opt_frame.pack(fill="x", padx=8, pady=4)

        self._show_logos_var = tk.BooleanVar(value=self.settings.career_show_logos)
        ttk.Checkbutton(opt_frame, text="Show team logos",
                        variable=self._show_logos_var).pack(
            anchor="w", padx=8, pady=(4, 2))

        self._highlight_var = tk.BooleanVar(value=self.settings.career_highlight_current)
        ttk.Checkbutton(opt_frame, text="Highlight current season",
                        variable=self._highlight_var).pack(
            anchor="w", padx=8, pady=(1, 2))

        self._show_ts_var = tk.BooleanVar(value=self.settings.career_show_timestamp)
        ttk.Checkbutton(opt_frame, text="Show 'data as of' timestamp",
                        variable=self._show_ts_var).pack(
            anchor="w", padx=8, pady=(0, 2))

        self._show_explainers_var = tk.BooleanVar(
            value=self.settings.career_show_col_explainers)
        ttk.Checkbutton(opt_frame, text="Show column explainers",
                        variable=self._show_explainers_var).pack(
            anchor="w", padx=8, pady=(0, 4))

        # Year sort order
        sort_row = ttk.Frame(opt_frame)
        sort_row.pack(anchor="w", padx=8, pady=(0, 4))
        ttk.Label(sort_row, text="Year order:").pack(side="left")
        self._year_sort_var = tk.StringVar(value=self.settings.career_year_sort)
        for val in ("Ascending", "Descending"):
            ttk.Radiobutton(sort_row, text=val, variable=self._year_sort_var,
                            value=val).pack(side="left", padx=(4, 0))

        # ---- Background Color ----
        bg_frame = ttk.LabelFrame(parent, text="Background Color")
        bg_frame.pack(fill="x", padx=8, pady=4)

        self._bg_var = tk.StringVar(value=self.settings.career_bg_color)
        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(anchor="w", **pad)
        ttk.Entry(bg_row, textvariable=self._bg_var, width=9).pack(side="left")
        self._bg_swatch = tk.Label(bg_row, width=3, relief="sunken",
                                   background=self.settings.career_bg_color)
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
            value=self.settings.career_export_filename)
        ttk.Label(export_frame, text="Filename (no extension):").pack(
            anchor="w", padx=8, pady=(4, 0))
        ttk.Entry(export_frame, textvariable=self._export_name_var, width=24).pack(
            fill="x", padx=8, pady=2)

        self._append_ts_var = tk.BooleanVar(
            value=self.settings.career_append_timestamp)
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
            text="Search for a player, then click 'Fetch & Preview'",
            fill="#666666", font=("Arial", 11))

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_lbl.config(text=msg,
                                foreground="#aa2200" if error else "#226622")

    def _on_player_selected(self, _event=None) -> None:
        display = self._player_combo.get()
        if display in self._player_options:
            pid, name, team = self._player_options[display]
            self._selected_id   = pid
            self._selected_name = name
            self._selected_team = team

    # ------------------------------------------------------------------
    # Recent players
    # ------------------------------------------------------------------
    def _recent_display(self, rec: dict) -> str:
        team = rec.get("team", "")
        name = rec.get("name", "")
        return f"{name} ({team})" if team else name

    def _refresh_recent_combo(self) -> None:
        recents = self.settings.career_recent_players or []
        values  = [self._recent_display(r) for r in recents]
        self._recent_combo["values"] = values
        if values:
            self._recent_combo.set(values[0])
        else:
            self._recent_combo.set("")

    def _on_recent_selected(self, _event=None) -> None:
        recents = self.settings.career_recent_players or []
        idx     = self._recent_combo.current()
        if idx < 0 or idx >= len(recents):
            return
        rec = recents[idx]
        self._selected_id   = rec.get("id",   0)
        self._selected_name = rec.get("name", "")
        self._selected_team = rec.get("team", "")
        # Populate search entry and results combo too
        self._search_var.set(self._selected_name)
        display = self._recent_display(rec)
        self._player_options[display] = (
            self._selected_id, self._selected_name, self._selected_team)
        self._player_combo["values"] = [display]
        self._player_combo.set(display)
        self._search_status.config(text="", foreground="#555555")

    def _add_to_recent(self, pid: int, name: str, team: str) -> None:
        if not pid or not name:
            return
        recents = [r for r in (self.settings.career_recent_players or [])
                   if r.get("id") != pid]
        recents.insert(0, {"id": pid, "name": name, "team": team})
        recents = recents[:20]
        self.settings.career_recent_players = recents
        self._refresh_recent_combo()

    # ------------------------------------------------------------------
    # Player search
    # ------------------------------------------------------------------
    def _search_player(self) -> None:
        if self._searching:
            return
        query = self._search_var.get().strip()
        if not query:
            return
        self._searching = True
        self._search_btn.config(state="disabled")
        self._search_status.config(text=f"Searching for \u201c{query}\u201d\u2026",
                                   foreground="#555555")
        self._player_combo.set("")
        self._player_combo["values"] = []
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query: str) -> None:
        try:
            results = search_players(query)
            self.after(0, lambda r=results: self._on_search_results(r))
        except Exception as exc:
            msg = str(exc)
            self.after(0, lambda m=msg: self._on_search_error(m))

    def _on_search_results(self, results: list[tuple[int, str, str]]) -> None:
        self._searching = False
        self._search_btn.config(state="normal")
        if not results:
            self._search_status.config(text="No players found.", foreground="#aa2200")
            return
        self._player_options.clear()
        displays: list[str] = []
        for pid, name, team in results:
            display = f"{name} ({team})" if team else name
            self._player_options[display] = (pid, name, team)
            displays.append(display)
        self._player_combo["values"] = displays
        self._player_combo.set(displays[0])
        self._on_player_selected()
        self._search_status.config(
            text=f"{len(results)} player{'s' if len(results) != 1 else ''} found.",
            foreground="#226622")

    def _on_search_error(self, msg: str) -> None:
        self._searching = False
        self._search_btn.config(state="normal")
        self._search_status.config(text=f"Search error: {msg}", foreground="#aa2200")

    # ------------------------------------------------------------------
    # Fetch & render
    # ------------------------------------------------------------------
    def _fetch_and_preview(self, force: bool = False) -> None:
        if self._fetching:
            return
        if not self._selected_id:
            self._set_status(
                "No player selected. Use the Search box to find a player.",
                error=True)
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
        self._set_status(
            f"Fetching {stat_type.lower()} career stats for {self._selected_name}\u2026",
            error=False)
        self._canvas.delete("all")
        self._canvas.create_text(
            THUMB_W // 2, THUMB_H // 2,
            text="Fetching data\u2026", fill="#555555", font=("Arial", 11))
        threading.Thread(target=self._do_fetch, args=(force,), daemon=True).start()

    def _force_refresh(self) -> None:
        self._fetch_and_preview(force=True)

    def _do_fetch(self, force: bool) -> None:
        try:
            block = fetch_career(
                player_id=self._selected_id,
                player_name=self._selected_name,
                stat_type=self._stat_type_var.get(),
                year_start=self._yr_start_var.get(),
                year_end=self._yr_end_var.get(),
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
            cfg = self._build_card_config(block)
            renderer = CareerCardRenderer(cfg, block,
                                          working_dir=self.settings.working_dir)
            self._card_image = renderer.render()
            self._update_thumbnail()
            n = len(block.entries)
            self._set_status(
                f"Done \u2014 {block.player_name}  \u00b7  {n} season{'s' if n != 1 else ''}",
                error=False)
            self._full_preview_btn.config(state="normal")
            self._export_png_btn.config(state="normal")
            self._export_jpg_btn.config(state="normal")
            # Add to recent players list
            self._add_to_recent(self._selected_id, self._selected_name,
                                self._selected_team)
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

    def _build_card_config(self, block=None) -> CareerCardConfig:
        stat_type = self._stat_type_var.get()
        return CareerCardConfig(
            width_in=self.settings.card_width_in if self._use_global_size_var.get() else self._width_var.get(),
            height_in=self.settings.card_height_in if self._use_global_size_var.get() else self._height_var.get(),
            dpi=self.settings.dpi,
            bg_color=self._bg_var.get(),
            stat_type=stat_type,
            show_logos=self._show_logos_var.get(),
            highlight_current=self._highlight_var.get(),
            show_timestamp=self._show_ts_var.get(),
            show_col_explainers=self._show_explainers_var.get(),
            col_explainer_sep=self.settings.col_explainer_sep,
            year_sort=self._year_sort_var.get(),
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
        win.title("Player Career Card \u2014 Full Preview")
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
        output_dir = os.path.join(working_dir, "output", "career")
        os.makedirs(output_dir, exist_ok=True)
        raw_name = self._export_name_var.get().strip() or "career_card"
        base     = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(". ")
        if not base:
            base = "career_card"
        if self._append_ts_var.get():
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{base}_{ts}"
        ext      = ".png" if fmt == "PNG" else ".jpg"
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
        self.settings.career_stat_type           = self._stat_type_var.get()
        self.settings.career_player_id           = self._selected_id
        self.settings.career_player_name         = self._selected_name
        self.settings.career_current_team_abbrev = self._selected_team
        self.settings.career_show_logos          = self._show_logos_var.get()
        self.settings.career_highlight_current   = self._highlight_var.get()
        self.settings.career_show_timestamp      = self._show_ts_var.get()
        self.settings.career_show_col_explainers = self._show_explainers_var.get()
        self.settings.career_year_sort           = self._year_sort_var.get()
        self.settings.career_width_in            = self._width_var.get()
        self.settings.career_height_in           = self._height_var.get()
        self.settings.career_use_global_size     = self._use_global_size_var.get()
        self.settings.career_bg_color            = self._bg_var.get()
        self.settings.career_export_filename     = self._export_name_var.get().strip()
        self.settings.career_append_timestamp    = self._append_ts_var.get()
        try:
            self.settings.career_year_start = int(self._yr_start_var.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.settings.career_year_end = int(self._yr_end_var.get())
        except (tk.TclError, ValueError):
            pass
