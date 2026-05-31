from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

from app.settings import Settings
from app.ui.settings_tab import SettingsTab
from app.ui.standings_tab import StandingsTab
from app.ui.batter_tab import BatterTab
from app.ui.pitcher_tab import PitcherTab
from app.ui.history_tab import HistoryTab
from app.ui.roster_tab import RosterTab
from app.ui.matchup_tab import MatchupTab
from app.ui.triple_crown_tab import TripleCrownTab
from app.ui.career_tab import CareerTab


class MainWindow(tk.Tk):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.title("MLB Stat Card Maker")
        self.minsize(900, 600)
        self._build()
        if self.settings.window_geometry:
            try:
                self.geometry(self.settings.window_geometry)
            except tk.TclError:
                pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self._standings_tab = StandingsTab(self.notebook, self.settings)
        self._settings_tab = SettingsTab(self.notebook, self.settings)
        self._batter_tab = BatterTab(self.notebook, self.settings)
        self._pitcher_tab = PitcherTab(self.notebook, self.settings)
        self._history_tab = HistoryTab(self.notebook, self.settings)
        self._roster_tab  = RosterTab(self.notebook, self.settings)
        self._matchup_tab      = MatchupTab(self.notebook, self.settings)
        self._triple_crown_tab = TripleCrownTab(self.notebook, self.settings)
        self._career_tab       = CareerTab(self.notebook, self.settings)

        self.notebook.add(self._standings_tab,   text="  Standings  ")
        self.notebook.add(self._batter_tab,      text="  Top Batters  ")
        self.notebook.add(self._pitcher_tab,     text="  Top Pitchers  ")
        self.notebook.add(self._triple_crown_tab, text="  Triple Crown  ")
        self.notebook.add(self._history_tab,     text="  Season Leaders  ")
        self.notebook.add(self._roster_tab,      text="  Team Roster  ")
        self.notebook.add(self._matchup_tab,     text="  Matchup  ")
        self.notebook.add(self._career_tab,      text="  Player Career  ")
        self.notebook.add(self._settings_tab,    text="  Settings  ")

        # --- Persistent bottom bar ---
        bar = ttk.Frame(self, relief="groove")
        bar.pack(fill="x", side="bottom", padx=0, pady=0)

        ttk.Separator(bar, orient="horizontal").pack(fill="x")

        btn_frame = ttk.Frame(bar)
        btn_frame.pack(fill="x", padx=10, pady=6)

        ttk.Button(
            btn_frame,
            text="Open Output Directory",
            command=self._open_output_dir,
        ).pack(side="left")

        ttk.Button(
            btn_frame,
            text="Quit",
            command=self._on_close,
        ).pack(side="right")

    def _open_output_dir(self) -> None:
        path = os.path.join(self.settings.working_dir, "output")
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _on_close(self) -> None:
        # Persist all tab settings before quitting
        self._settings_tab.apply()
        self._standings_tab.apply()
        self._batter_tab.apply()
        self._pitcher_tab.apply()
        self._history_tab.apply()
        self._roster_tab.apply()
        self._matchup_tab.apply()
        self._triple_crown_tab.apply()
        self._career_tab.apply()
        self.settings.window_geometry = self.geometry()
        try:
            self.settings.save(self.settings.working_dir)
        except Exception as exc:
            logger.error("Failed to save settings: %s", exc)
        self.destroy()
